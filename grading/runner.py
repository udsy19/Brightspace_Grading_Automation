"""
Grading orchestrator with calibration, prompt caching, and crash recovery.

Flow:
1. Build system prompt once (rubric + reference + instructions)
2. Calibration: grade 2-3 sample students, show results for user review
3. User approves calibration → examples are baked into system prompt
4. Batch grade remaining students (system prompt cached after first call)
5. Validate scores, export CSV
"""

import json
import random
import hashlib
from pathlib import Path
from datetime import datetime
from anthropic import Anthropic

from rich.table import Table

from ui import console, info, success, warning, error, make_grading_progress, confirm
from config import get_anthropic_key
from grading.anonymizer import Anonymizer
from grading.grader import grade_student, build_system_prompt, GradeResult
from grading.validator import validate_grades, flag_outliers, save_flags
from grading.exporter import export_grades_csv


class GradingRunner:
    """
    Orchestrates the full grading pipeline:
    - FERPA anonymization
    - Calibration phase
    - Cached batch grading
    - Validation + CSV export
    """

    def __init__(self, assignment_path: Path):
        self.assignment_path = assignment_path
        self.submissions_dir = assignment_path / "submissions"
        self.grading_dir = assignment_path / "grading"
        self.audit_dir = self.grading_dir / "audit"
        self.state_file = self.grading_dir / "run-state.json"
        self.anonymizer = Anonymizer()

        config_file = assignment_path / "config.json"
        self.config = json.loads(config_file.read_text()) if config_file.exists() else {}

    def run(
        self,
        model: str | None = None,
        resume: bool = True,
        students: list[str] | None = None,
        skip_calibration: bool = False,
    ) -> dict:
        """
        Grade all submissions.

        model: override AI model
        resume: skip already-graded students
        students: grade only these usernames
        skip_calibration: jump straight to batch grading
        """
        self.grading_dir.mkdir(exist_ok=True)
        self.audit_dir.mkdir(exist_ok=True)

        model = model or self.config.get("grading_model", "claude-sonnet-4-5-20250929")

        # Load rubric
        rubric = self._load_rubric()
        if not rubric:
            error("No rubric found. Configure rubric first.")
            return {"graded": 0, "failed": 0}

        rubric_hash = hashlib.sha256(
            json.dumps(rubric, sort_keys=True).encode()
        ).hexdigest()[:12]

        # Load reference material
        reference_text = self._load_reference()

        # Init API client (reused for all students)
        api_key = get_anthropic_key()
        if not api_key:
            error("ANTHROPIC_API_KEY not set in .env")
            return {"graded": 0, "failed": 0}
        client = Anthropic(api_key=api_key)

        # Get student list
        all_students = self._get_students()
        if students:
            all_students = [s for s in all_students if s in students]
        if not all_students:
            warning("No student submissions found")
            return {"graded": 0, "failed": 0}

        # Load run state for crash recovery
        state = self._load_state() if resume else {}
        completed = set(state.get("completed", []))

        to_grade = [s for s in all_students if s not in completed]
        if not to_grade:
            info("All students already graded")
            return {"graded": len(completed), "failed": 0, "skipped": 0}

        info(f"Model: {model}  |  Rubric: {rubric_hash}  |  Students: {len(to_grade)}")

        # ---------------------------------------------------------------
        # Phase 1: Calibration
        # ---------------------------------------------------------------
        calibration_examples = []

        if not skip_calibration and len(to_grade) > 3:
            calibration_examples = self._calibration_phase(
                to_grade, rubric, reference_text, model, client
            )
            if calibration_examples is None:
                # User cancelled
                return {"graded": 0, "failed": 0}

            # Remove calibrated students from to_grade list
            calibrated_ids = {ex["username"] for ex in calibration_examples}
            completed.update(calibrated_ids)
            to_grade = [s for s in to_grade if s not in calibrated_ids]

        # ---------------------------------------------------------------
        # Phase 2: Build cached system prompt
        # ---------------------------------------------------------------
        # Calibration examples get baked into the prompt as scoring reference
        system_prompt = build_system_prompt(
            rubric=rubric,
            reference_text=reference_text,
            calibration_examples=[
                {
                    "student_id": ex.get("anon_id", "?"),
                    "criteria": ex.get("criteria", []),
                    "percentage": ex.get("percentage", 0),
                }
                for ex in calibration_examples
            ] if calibration_examples else None,
        )

        if not to_grade:
            info("All students graded (calibration covered everyone)")
            return {"graded": len(completed), "failed": 0, "skipped": 0}

        # ---------------------------------------------------------------
        # Phase 3: Batch grading with progress
        # ---------------------------------------------------------------
        console.print()
        info(f"Grading {len(to_grade)} remaining students (prompt cached after first)...")
        console.print()

        results = []
        # Include calibration results
        for ex in calibration_examples:
            results.append(ex)

        graded = 0
        failed = 0
        failed_list = list(state.get("failed", []))
        cache_hits = 0

        progress = make_grading_progress()

        with progress:
            task = progress.add_task(
                "Grading", total=len(to_grade), status="starting..."
            )

            for username in to_grade:
                anon_id = self.anonymizer.anonymize(username)
                submission_text = self._load_submission(username)

                if not submission_text:
                    failed += 1
                    failed_list.append(username)
                    progress.update(task, advance=1, status=f"[dim]empty: {username}[/dim]")
                    self._save_state(list(completed), failed_list, all_students)
                    continue

                clean_text = self.anonymizer.strip_pii(submission_text)
                progress.update(task, status=f"[bold]{username}[/bold]")

                try:
                    result = grade_student(
                        student_id=anon_id,
                        submission_text=clean_text,
                        system_prompt=system_prompt,
                        model=model,
                        client=client,
                        audit_dir=self.audit_dir,
                    )

                    self._save_student_result(username, result)

                    if result.cached:
                        cache_hits += 1

                    results.append({
                        "username": username,
                        "anon_id": anon_id,
                        "raw_total": result.raw_total,
                        "max_total": result.max_total,
                        "percentage": result.percentage,
                        "criteria": [
                            {"name": c.name, "score": c.score, "max_points": c.max_points, "level": c.level}
                            for c in result.criteria
                        ],
                        "feedback": result.feedback,
                    })

                    completed.add(username)
                    graded += 1
                    progress.update(
                        task, advance=1,
                        status=f"[green]{username}: {result.percentage:.0f}%[/green]"
                        + (" [dim](cached)[/dim]" if result.cached else ""),
                    )

                except Exception as e:
                    failed += 1
                    failed_list.append(username)
                    progress.update(task, advance=1, status=f"[red]error: {username}[/red]")
                    console.print(f"    [red]Error grading {username}: {e}[/red]")

                self._save_state(list(completed), failed_list, all_students)

        # ---------------------------------------------------------------
        # Phase 4: Validate + Export
        # ---------------------------------------------------------------
        all_flags = validate_grades(results, rubric) + flag_outliers(results)
        if all_flags:
            save_flags(all_flags, self.grading_dir / "flags.json")

        if results:
            self._apply_late_policy(results)
            csv_path = export_grades_csv(results, rubric, self.grading_dir / "grades.csv")
            success(f"Grades exported: {csv_path.name}")

        self.anonymizer.save_mapping(self.grading_dir / "anon_mapping.json")
        self._save_state(list(completed), failed_list, all_students, finished=True)

        total_graded = graded + len(calibration_examples)
        console.print()
        success(
            f"Complete: {total_graded} graded, {failed} failed, "
            f"{len(all_students) - len(to_grade) - len(calibration_examples)} skipped"
        )
        if cache_hits > 0:
            info(f"Prompt cache hits: {cache_hits}/{graded} ({cache_hits/max(graded,1)*100:.0f}%)")
        if all_flags:
            warning(f"{len(all_flags)} flags — review grading/flags.json")

        return {
            "graded": total_graded,
            "failed": failed,
            "skipped": len(all_students) - len(to_grade) - len(calibration_examples),
            "total": len(all_students),
            "flags": len(all_flags),
            "cache_hits": cache_hits,
        }

    # -------------------------------------------------------------------
    # Calibration phase
    # -------------------------------------------------------------------

    def _calibration_phase(
        self,
        to_grade: list[str],
        rubric: dict,
        reference_text: str,
        model: str,
        client: Anthropic,
    ) -> list[dict] | None:
        """
        Grade 2-3 sample students, show results, get user approval.
        Returns list of result dicts, or None if user cancels.
        """
        console.print()
        console.rule("[bold magenta]Calibration Phase[/bold magenta]")
        console.print()
        info("Grading 3 sample students to calibrate scoring...")
        info("Review the results before grading everyone.")
        console.print()

        # Pick samples — try to get varied submissions (short, medium, long)
        samples = self._pick_calibration_samples(to_grade, n=min(3, len(to_grade)))

        # Build system prompt WITHOUT calibration examples (this is the calibration run)
        system_prompt = build_system_prompt(
            rubric=rubric,
            reference_text=reference_text,
        )

        calibration_results = []

        for i, username in enumerate(samples, 1):
            anon_id = self.anonymizer.anonymize(username)
            submission_text = self._load_submission(username)

            if not submission_text:
                warning(f"Sample {i}: {username} has no submission, skipping")
                continue

            clean_text = self.anonymizer.strip_pii(submission_text)
            info(f"Grading sample {i}/3: {username}...")

            try:
                result = grade_student(
                    student_id=anon_id,
                    submission_text=clean_text,
                    system_prompt=system_prompt,
                    model=model,
                    client=client,
                    audit_dir=self.audit_dir,
                )

                self._save_student_result(username, result)

                calibration_results.append({
                    "username": username,
                    "anon_id": anon_id,
                    "raw_total": result.raw_total,
                    "max_total": result.max_total,
                    "percentage": result.percentage,
                    "criteria": [
                        {"name": c.name, "score": c.score, "max_points": c.max_points, "level": c.level}
                        for c in result.criteria
                    ],
                    "feedback": result.feedback,
                })

                success(f"  {username}: {result.percentage:.0f}%")

            except Exception as e:
                error(f"  Failed to grade {username}: {e}")

        if not calibration_results:
            error("All calibration samples failed")
            return None

        # Show calibration results
        self._show_calibration_results(calibration_results, rubric)

        # Get user approval
        console.print()
        choice = console.input(
            "    [bold]Accept calibration?[/bold]  "
            "[dim]\\[y] Accept  \\[n] Cancel  \\[r] Re-grade samples[/dim]\n    > "
        ).strip().lower()

        if choice == "n":
            return None
        elif choice == "r":
            # Re-run calibration with new samples
            return self._calibration_phase(to_grade, rubric, reference_text, model, client)

        return calibration_results

    def _pick_calibration_samples(self, students: list[str], n: int = 3) -> list[str]:
        """Pick diverse samples — try to get short, medium, long submissions."""
        if len(students) <= n:
            return students

        # Measure submission lengths
        lengths = {}
        for s in students:
            text = self._load_submission(s)
            lengths[s] = len(text) if text else 0

        # Sort by length, pick from start, middle, end
        sorted_students = sorted(lengths.keys(), key=lambda s: lengths[s])
        non_empty = [s for s in sorted_students if lengths[s] > 0]

        if len(non_empty) <= n:
            return non_empty

        step = len(non_empty) // n
        samples = []
        for i in range(n):
            idx = min(i * step, len(non_empty) - 1)
            samples.append(non_empty[idx])

        return samples

    def _show_calibration_results(self, results: list[dict], rubric: dict):
        """Display calibration results in a rich table."""
        console.print()
        console.rule("[bold]Calibration Results[/bold]")
        console.print()

        criteria_names = [c["name"] for c in rubric.get("criteria", [])]

        # Summary table
        table = Table(box=None, padding=(0, 2), show_edge=False)
        table.add_column("Student", style="white", min_width=12)
        for name in criteria_names:
            table.add_column(name[:15], justify="center", min_width=8)
        table.add_column("Total", justify="right", style="bold")

        for r in results:
            row = [r["username"]]
            criteria_map = {c["name"]: c for c in r.get("criteria", [])}
            for name in criteria_names:
                c = criteria_map.get(name, {})
                level = c.get("level", "?")
                score = c.get("score", 0)
                max_pts = c.get("max_points", 0)
                if level == "PASS":
                    cell = f"[green]{score}/{max_pts}[/green]"
                elif level == "PARTIAL":
                    cell = f"[yellow]{score}/{max_pts}[/yellow]"
                else:
                    cell = f"[red]{score}/{max_pts}[/red]"
                row.append(cell)
            row.append(f"{r['percentage']:.0f}%")
            table.add_row(*row)

        console.print(table)

        # Show feedback for each
        console.print()
        for r in results:
            console.print(f"    [bold]{r['username']}[/bold] ({r['percentage']:.0f}%)")
            if r.get("feedback"):
                console.print(f"    [dim]{r['feedback'][:200]}[/dim]")
            console.print()

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _load_rubric(self) -> dict | None:
        rubric_file = self.assignment_path / "assignment" / "rubric.json"
        if not rubric_file.exists():
            return None
        try:
            return json.loads(rubric_file.read_text())
        except Exception:
            return None

    def _load_reference(self) -> str:
        assignment_dir = self.assignment_path / "assignment"
        if not assignment_dir.exists():
            return ""
        parts = []
        for f in sorted(assignment_dir.iterdir()):
            if f.is_file() and f.name != "rubric.json" and f.suffix in (".txt", ".md"):
                try:
                    parts.append(f.read_text(encoding="utf-8"))
                except Exception:
                    pass
        return "\n\n".join(parts)

    def _get_students(self) -> list[str]:
        if not self.submissions_dir.exists():
            return []
        return sorted(
            d.name for d in self.submissions_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    def _load_submission(self, username: str) -> str:
        student_dir = self.submissions_dir / username
        if not student_dir.exists():
            return ""

        parts = []

        for name in ("submission.json", "transcript.txt", "submission.txt"):
            f = student_dir / name
            if not f.exists():
                continue
            try:
                if name.endswith(".json"):
                    data = json.loads(f.read_text())
                    if isinstance(data, dict):
                        for k, v in data.items():
                            parts.append(f"[{k}]\n{v}")
                    elif isinstance(data, str):
                        parts.append(data)
                else:
                    parts.append(f.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Other text/code files
        known = {"submission.json", "transcript.txt", "submission.txt", "metadata.json"}
        for f in sorted(student_dir.iterdir()):
            if f.is_file() and f.name not in known:
                if f.suffix in (".txt", ".md", ".py", ".java", ".c", ".cpp", ".js", ".html", ".css"):
                    try:
                        parts.append(f"[{f.name}]\n{f.read_text(encoding='utf-8')}")
                    except Exception:
                        pass

        return "\n\n".join(parts)

    def _save_student_result(self, username: str, result: GradeResult):
        result_file = self.grading_dir / f"{username}.json"
        data = {
            "username": username,
            "raw_total": result.raw_total,
            "max_total": result.max_total,
            "percentage": result.percentage,
            "feedback": result.feedback,
            "graded_at": result.graded_at,
            "model": result.model_used,
            "cached": result.cached,
            "criteria": [
                {
                    "name": c.name,
                    "score": c.score,
                    "max_points": c.max_points,
                    "level": c.level,
                    "evidence": c.evidence,
                    "reasoning": c.reasoning,
                }
                for c in result.criteria
            ],
        }
        result_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def _apply_late_policy(self, results: list[dict]):
        deadline = self.config.get("deadline")
        late_policy = self.config.get("late_policy", "zero")

        if not deadline or late_policy != "zero":
            for r in results:
                r.setdefault("final_score", r["percentage"])
                r.setdefault("late", False)
            return

        deadline_dt = datetime.fromisoformat(deadline)

        for r in results:
            username = r["username"]
            meta_file = self.submissions_dir / username / "metadata.json"

            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text())
                    sub_time = meta.get("submitted_at")
                    attempt = meta.get("attempt", 1)

                    if sub_time:
                        sub_dt = datetime.fromisoformat(sub_time)
                        if sub_dt > deadline_dt and attempt == 1:
                            r["final_score"] = 0
                            r["late"] = True
                            continue
                except Exception:
                    pass

            r.setdefault("final_score", r["percentage"])
            r.setdefault("late", False)

    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                return {}
        return {}

    def _save_state(self, completed: list, failed: list, total_list: list, finished: bool = False):
        state = {
            "completed": completed,
            "failed": failed,
            "total": len(total_list),
            "updated_at": datetime.now().isoformat(),
            "finished": finished,
        }
        self.state_file.write_text(json.dumps(state, indent=2))
