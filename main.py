#!/usr/bin/env python3
"""
Brightspace Grading Automation

Connect → pick course → pick assignment → download → grade → upload
"""

import sys
import json
import traceback
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from brightspace.models import BrightspaceCourse, BrightspaceAssignment, BrightspaceQuiz
from logger import logger
from config import (
    ensure_base_dirs, get_credentials, get_anthropic_key,
    CLASSES_DIR, BRIGHTSPACE_URL,
)
from ui import (
    console, clear, info, success, error, warning, dim,
    header, status_dot, newline, pick, confirm, prompt, pause,
)


# ---------------------------------------------------------------------------
# Browser
# ---------------------------------------------------------------------------

_browser = None


def get_browser():
    global _browser
    if _browser is None:
        from brightspace.browser import BrightspaceBrowser
        _browser = BrightspaceBrowser()
    return _browser


def disconnect():
    global _browser
    if _browser:
        _browser.close()
        _browser = None


# ---------------------------------------------------------------------------
# Connect
# ---------------------------------------------------------------------------

def connect() -> bool:
    browser = get_browser()
    if browser.is_running and browser.is_logged_in():
        return True

    creds = get_credentials()
    if not creds:
        error("Set PURDUE_USERNAME and PURDUE_PASSWORD in .env")
        return False

    from brightspace.auth import login, handle_duo, save_session

    dim("Launching browser...")
    page = browser.launch(headless=True)

    page.goto(f"{BRIGHTSPACE_URL}/d2l/home")
    page.wait_for_load_state("networkidle")

    if browser.is_logged_in():
        success("Session restored")
        return True

    if not login(page):
        return False
    if not handle_duo(page):
        return False

    save_session(page)
    success("Connected")
    return True


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_courses(page) -> list[BrightspaceCourse]:
    from brightspace.courses import get_courses
    dim("Scanning courses...")
    page.goto(f"{BRIGHTSPACE_URL}/d2l/home")
    page.wait_for_load_state("networkidle")
    return get_courses(page)


def discover_assignments(page, course_href: str) -> list[BrightspaceAssignment]:
    from brightspace.assignments import get_assignments_data
    dim("Scanning assignments...")
    try:
        return get_assignments_data(page, course_href)
    except Exception as e:
        logger.error(f"Failed to scan assignments:\n{traceback.format_exc()}")
        warning(f"Failed to scan assignments: {e}")
        return []

def discover_quizzes(page, course_href: str) -> list[BrightspaceQuiz]:
    from brightspace.quizzes import get_quizzes_data
    dim("Scanning quizzes...")
    try:
        return get_quizzes_data(page, course_href)
    except Exception as e:
        logger.error(f"Failed to scan quizzes:\n{traceback.format_exc()}")
        warning(f"Failed to scan quizzes: {e}")
        return []

# ---------------------------------------------------------------------------
# Local dirs (auto)
# ---------------------------------------------------------------------------

def ensure_local_dirs(course_name: str, assignment_name: str) -> Path:
    ensure_base_dirs()
    safe = lambda s: "".join(c if c.isalnum() or c in "-_ " else "" for c in s).strip().replace(" ", "-")
    path = CLASSES_DIR / safe(course_name) / safe(assignment_name)
    for d in ("assignment", "submissions", "grading", "grading/audit"):
        (path / d).mkdir(parents=True, exist_ok=True)
    cfg = path / "config.json"
    if not cfg.exists():
        cfg.write_text(json.dumps({
            "name": assignment_name,
            "created_at": datetime.now().isoformat(),
            "grading_model": "claude-sonnet-4-5-20250929",
        }, indent=2))
    return path


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def do_download(page, bs_assignment, assignment_path):
    from brightspace.assignments import get_submission_links
    from brightspace.downloader import download_submissions

    student_links = get_submission_links(page, bs_assignment)
    if not student_links:
        warning("No students found")
        return

    info(f"{len(student_links)} students")
    subs = assignment_path / "submissions"
    download_submissions(page, student_links, subs)

    for sd in subs.iterdir():
        if sd.is_dir() and not (sd / "metadata.json").exists():
            (sd / "metadata.json").write_text(json.dumps({
                "username": sd.name,
                "imported_at": datetime.now().isoformat(),
                "source": "brightspace",
                "attempt": 1,
            }, indent=2))

    get_browser().save_session()


def do_grade(assignment_path):
    rubric_file = assignment_path / "assignment" / "rubric.json"
    if not rubric_file.exists():
        error("No rubric at assignment/rubric.json")
        dim("Drop a rubric.json in the assignment/ folder and try again.")
        return

    subs = assignment_path / "submissions"
    students = [d for d in subs.iterdir() if d.is_dir()] if subs.exists() else []
    if not students:
        error("No submissions")
        return

    if not get_anthropic_key():
        error("Set ANTHROPIC_API_KEY in .env")
        return

    rubric = json.loads(rubric_file.read_text())
    config = json.loads((assignment_path / "config.json").read_text()) if (assignment_path / "config.json").exists() else {}

    newline()
    info(f"{len(students)} students · {len(rubric.get('criteria', []))} criteria · {rubric.get('total_points', '?')} pts")
    info(f"Model: {config.get('grading_model', 'claude-sonnet-4-5-20250929')}")

    # Resume check
    state_file = assignment_path / "grading" / "run-state.json"
    if state_file.exists():
        state = json.loads(state_file.read_text())
        done = len(state.get("completed", []))
        if done > 0 and not state.get("finished"):
            dim(f"Resuming — {done} already graded")

    newline()
    if not confirm(f"Grade {len(students)} students?"):
        return

    from grading.runner import GradingRunner
    runner = GradingRunner(assignment_path)
    result = runner.run(resume=True)

    # Show summary
    newline()
    if result.get("graded", 0) > 0:
        show_stats(assignment_path)


def do_upload(page, bs_assignment: BrightspaceAssignment, assignment_path):
    from brightspace.uploader import upload_grades

    grades_csv = assignment_path / "grading" / "grades.csv"
    if not grades_csv.exists():
        error("No grades.csv — grade first")
        return

    upload_grades(page, bs_assignment.href, grades_csv)
    get_browser().save_session()


def show_stats(assignment_path):
    grades_csv = assignment_path / "grading" / "grades.csv"
    if not grades_csv.exists():
        dim("No grades yet")
        return

    import pandas as pd
    df = pd.read_csv(grades_csv)

    if "percentage" in df.columns:
        info(
            f"Mean: {df['percentage'].mean():.1f}%  "
            f"Median: {df['percentage'].median():.1f}%  "
            f"Low: {df['percentage'].min():.1f}%  "
            f"High: {df['percentage'].max():.1f}%"
        )

    # Show per-student scores
    newline()
    for _, row in df.iterrows():
        pct = row.get("percentage", 0)
        name = row.get("username", "?")
        color = "green" if pct >= 70 else "yellow" if pct >= 50 else "red"
        console.print(f"  [{color}]{pct:5.1f}%[/{color}]  {name}")

    newline()
    info(f"{len(df)} students · grades.csv")

    flags_file = assignment_path / "grading" / "flags.json"
    if flags_file.exists():
        flags = json.loads(flags_file.read_text())
        if flags:
            warning(f"{len(flags)} flagged — see grading/flags.json")


# ---------------------------------------------------------------------------
# Pipeline steps for Quizzes
# ---------------------------------------------------------------------------

def do_download_quizzes(page, bs_quiz, quiz_path, org_unit):
    from brightspace.quizzes import get_quiz_submission_links, download_quiz_attempts
    
    student_links = get_quiz_submission_links(page, bs_quiz, org_unit)
    if not student_links:
        warning("No attempts found")
        return

    info(f"{len(student_links)} attempts")
    subs = quiz_path / "submissions"
    download_quiz_attempts(page, student_links, subs)

    for sd in subs.iterdir():
        if sd.is_dir() and not (sd / "metadata.json").exists():
            (sd / "metadata.json").write_text(json.dumps({
                "username": sd.name,
                "imported_at": datetime.now().isoformat(),
                "source": "brightspace",
                "attempt": 1, # Quiz attempts might vary, keeping simple
            }, indent=2))

    get_browser().save_session()

def do_upload_quizzes(page, bs_quiz, quiz_path, org_unit):
    from brightspace.quizzes import get_quiz_submission_links
    from brightspace.uploader import upload_quiz_grades

    grades_csv = quiz_path / "grading" / "grades.csv"
    if not grades_csv.exists():
        error("No grades.csv — grade first")
        return

    # To upload we need the attempt links again to navigate
    student_links = get_quiz_submission_links(page, bs_quiz, org_unit)
    if not student_links:
        warning("No attempts found to upload to")
        return

    upload_quiz_grades(page, student_links, grades_csv)
    get_browser().save_session()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    clear()
    console.print("\n  [bold]Brightspace Grading[/bold]\n")

    creds = get_credentials()
    api_key = get_anthropic_key()
    status_dot("Credentials", bool(creds))
    status_dot("API key", bool(api_key))

    if not creds:
        newline()
        error("Configure .env first")
        return

    newline()
    if not connect():
        return

    page = get_browser().page

    while True:
        # Pick course
        courses = discover_courses(page)
        if not courses:
            error("No courses found")
            return

        names = [c.name.split(",")[0].strip() for c in courses]
        idx = pick(names, "Course")
        if idx is None:
            break

        course = courses[idx]

        url = BRIGHTSPACE_URL + course.href
        dim(f"Navigating to {url}...")
        page.goto(url)
        page.wait_for_load_state("networkidle")
        
        org_unit = url.split("ou=")[-1] if "ou=" in url else url.split("/home/")[1].split("?")[0]

        # Pick evaluation type
        eval_options = ["Assignments", "Quizzes", "Discussions (Coming Soon)"]
        eval_idx = pick(eval_options, "Evaluation Type")
        if eval_idx is None:
            continue
            
        if eval_idx == 2:
            warning(f"Grading for {eval_options[eval_idx]} is not yet implemented.")
            pause()
            continue

        if eval_idx == 0:
            # Pick assignment
            assignments = discover_assignments(page, course.href)
            if not assignments:
                warning("No assignments")
                pause()
                continue
    
            a_labels = []
            for a in assignments:
                parts = [a.name]
                if getattr(a, "completed", None) and a.completed != "-":
                    parts.append(f"[dim]{a.completed} submitted[/dim]")
                if getattr(a, "due_date", None):
                    parts.append(f"[dim]{a.due_date}[/dim]")
                a_labels.append("  ".join(parts))
    
            a_idx = pick(a_labels, "Assignment")
            if a_idx is None:
                continue
    
            bs_item = assignments[a_idx]
            is_quiz = False
            
        elif eval_idx == 1:
            # Pick quiz
            quizzes = discover_quizzes(page, course.href)
            if not quizzes:
                warning("No quizzes")
                pause()
                continue
                
            q_labels = []
            for q in quizzes:
                subs = ""
                if getattr(q, "completed", None) and q.completed != "-":
                    subs = f"{q.completed} submissions"
                q_labels.append((q.name, subs))
            q_idx = pick(q_labels, "Quiz")
            if q_idx is None:
                continue
                
            bs_item = quizzes[q_idx]
            is_quiz = True

        eval_path = ensure_local_dirs(
            course.name.split(",")[0].strip(),
            bs_item.name,
        )

        # Pipeline loop
        while True:
            subs_dir = eval_path / "submissions"
            n_subs_local = len([d for d in subs_dir.iterdir() if d.is_dir()]) if subs_dir.exists() else 0
            has_grades = (eval_path / "grading" / "grades.csv").exists()
            has_rubric = (eval_path / "assignment" / "rubric.json").exists()

            # For Quizzes, it's called "completed", for Assignments it isn't tracked identically but we can label it
            bs_count = getattr(bs_item, "completed", None)
            if bs_count is None or bs_count == "-":
                bs_submit_text = "Unknown online submissions"
                has_online = False
            else:
                bs_submit_text = f"{bs_count} online submissions"
                has_online = True

            newline()
            header(bs_item.name)
            status_dot(bs_submit_text, has_online)
            status_dot(f"{n_subs_local} downloaded", n_subs_local > 0)
            status_dot("Rubric", has_rubric)
            status_dot("Graded", has_grades)

            newline()
            dim("[d]ownload  [g]rade  [u]pload  [v]iew  [b]ack")
            raw = prompt()

            if raw in ("d", "download"):
                if is_quiz:
                    do_download_quizzes(page, bs_item, eval_path, org_unit)
                else:
                    do_download(page, bs_item, eval_path)
            elif raw in ("g", "grade"):
                do_grade(eval_path)
            elif raw in ("u", "upload"):
                if is_quiz:
                     do_upload_quizzes(page, bs_item, eval_path, org_unit)
                else:
                     do_upload(page, bs_item, eval_path)
            elif raw in ("v", "view"):
                show_stats(eval_path)
                pause()
            elif raw in ("b", "back", "q"):
                break

    disconnect()
    console.print("\n  [dim]Done.[/dim]\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        disconnect()
        console.print("\n")
        sys.exit(0)
