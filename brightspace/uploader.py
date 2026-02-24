"""Upload grades back to Brightspace"""

import csv
import time
from pathlib import Path
from playwright.sync_api import Page

from config import BRIGHTSPACE_URL
from ui import console, info, success, warning, error, make_progress


def upload_grades(
    page: Page,
    assignment_href: str,
    grades_csv: Path,
    score_column: str = "final_score",
    feedback_column: str = "feedback",
) -> dict:
    """
    Upload grades from CSV to Brightspace assignment.

    Navigates to each student's evaluation page and enters the score + feedback.
    Returns summary dict.
    """
    if not grades_csv.exists():
        error(f"Grades file not found: {grades_csv}")
        return {"uploaded": 0, "failed": 0}

    # Load grades
    rows = []
    with open(grades_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get(score_column):
                rows.append(row)

    if not rows:
        warning("No grades to upload")
        return {"uploaded": 0, "failed": 0}

    # Navigate to assignment
    full_url = assignment_href
    if not full_url.startswith("http"):
        full_url = BRIGHTSPACE_URL + full_url

    page.goto(full_url)
    page.wait_for_load_state("networkidle")

    # Try to set page size to 200
    try:
        selector = page.locator("select[title*='page'], select[aria-label*='page']")
        if selector.count() > 0:
            selector.first.select_option(value="200")
            page.wait_for_load_state("networkidle")
    except Exception:
        pass

    uploaded = 0
    failed = 0

    progress = make_progress("Uploading grades")

    with progress:
        task = progress.add_task(
            "Uploading", total=len(rows), status="starting..."
        )

        for row in rows:
            username = row.get("username", "")
            score = row.get(score_column, "")
            feedback = row.get(feedback_column, "")

            try:
                # Find student in the table
                student_row = page.locator(f"tr:has-text('{username}')").first
                if student_row.count() == 0:
                    failed += 1
                    progress.update(
                        task, advance=1, status=f"[yellow]not found: {username}[/yellow]"
                    )
                    continue

                # Click evaluate/grade link
                eval_link = student_row.locator("a:has-text('Evaluate'), a:has-text('Grade')").first
                if eval_link.count() == 0:
                    # Try clicking the student name
                    eval_link = student_row.locator("a").first

                eval_link.click()
                page.wait_for_load_state("networkidle")

                # Fill score
                score_input = page.locator(
                    "input[id*='score'], input[aria-label*='Score'], "
                    "input[aria-label*='Grade'], d2l-input-number"
                ).first
                if score_input.count() > 0:
                    score_input.fill(str(score))

                # Fill feedback
                if feedback:
                    feedback_area = page.locator(
                        "textarea, [contenteditable='true'], "
                        "d2l-htmleditor iframe"
                    ).first
                    if feedback_area.count() > 0:
                        try:
                            feedback_area.fill(feedback)
                        except Exception:
                            # For rich text editors, try evaluate
                            pass

                # Save
                save_btn = page.locator(
                    "button:has-text('Save'), button:has-text('Publish')"
                ).first
                if save_btn.count() > 0:
                    save_btn.click()
                    page.wait_for_load_state("networkidle")
                    uploaded += 1
                    progress.update(
                        task, advance=1, status=f"[green]{username}[/green]"
                    )
                else:
                    failed += 1
                    progress.update(
                        task, advance=1, status=f"[red]no save: {username}[/red]"
                    )

                # Go back to assignment list
                page.go_back()
                page.wait_for_load_state("networkidle")

            except Exception as e:
                failed += 1
                progress.update(
                    task, advance=1, status=f"[red]error: {username}[/red]"
                )
                # Try to get back to the assignment page
                try:
                    page.goto(full_url)
                    page.wait_for_load_state("networkidle")
                except Exception:
                    pass

    summary = {"uploaded": uploaded, "failed": failed, "total": len(rows)}

    if uploaded > 0:
        success(f"Uploaded {uploaded}/{len(rows)} grades")
    if failed > 0:
        warning(f"{failed} grades failed to upload")
    return summary


def upload_quiz_grades(
    page: Page,
    attempt_links: list[tuple[str, str]],
    grades_csv: Path,
    score_column: str = "final_score",
    feedback_column: str = "feedback",
) -> dict:
    """
    Upload grades for quizzes back into Brightspace.
    """
    if not grades_csv.exists():
        error(f"Grades file not found: {grades_csv}")
        return {"uploaded": 0, "failed": 0}

    # Load grades into memory
    student_grades = {}
    with open(grades_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
             username = row.get("username", "")
             if username:
                  student_grades[username] = row

    if not student_grades:
        warning("No grades to upload")
        return {"uploaded": 0, "failed": 0}

    uploaded = 0
    failed = 0

    progress = make_progress("Uploading quiz grades")

    with progress:
        task = progress.add_task(
            "Uploading", total=len(attempt_links), status="starting..."
        )

        for attempt_name, href in attempt_links:
            # Clean attempt name to match our folder name ("username")
            # e.g., "Angel Guadarrama - attempt 1" -> "Angel_Guadarrama_-_attempt_1"
            # We just need to find the student in the CSV. Let's do a loose match.
            safe_name = "".join(
                c if c.isalnum() or c in "-_" else "_" for c in attempt_name
            ).strip("_")

            # Find matching grade dict
            # The CSV username might just be "Angel Guadarrama"
            row = None
            for csv_user, data in student_grades.items():
                safe_csv_user = "".join(
                    c if c.isalnum() or c in "-_" else "_" for c in csv_user
                ).strip("_")
                
                if safe_csv_user in safe_name or safe_name in safe_csv_user:
                    row = data
                    break
            
            if not row:
                failed += 1
                progress.update(
                    task, advance=1, status=f"[yellow]no grade: {safe_name}[/yellow]"
                )
                continue

            score = row.get(score_column, "")
            feedback = row.get(feedback_column, "")

            full_url = href if href.startswith("http") else BRIGHTSPACE_URL + href
            
            try:
                page.goto(full_url)
                page.wait_for_load_state("networkidle")

                # Fill Attempt Grade box
                # Depending on Brightspace view, it might be input with label 'Attempt Grade'
                score_input = page.locator("input[aria-label*='Attempt Grade'], input[title*='Attempt Grade'], input[id*='score']").first
                if score_input.count() > 0:
                     score_input.fill(str(score))
                     
                # Fill Feedback
                if feedback:
                     # Switch to iframe if rich text editor
                     iframe = page.locator("iframe.tox-edit-area__iframe").first
                     if iframe.count() > 0:
                          frame = iframe.content_frame
                          body = frame.locator("body")
                          body.fill(feedback)
                     else:
                          # fallback to standard text area
                          feedback_area = page.locator("textarea[title*='Feedback'], textarea[aria-label*='Feedback']").first
                          if feedback_area.count() > 0:
                               feedback_area.fill(feedback)

                # Click Update
                update_btn = page.get_by_text("Update").first
                if not update_btn.is_visible():
                     update_btn = page.locator("button:has-text('Publish')").first
                     
                if update_btn.is_visible():
                     update_btn.click()
                     # Give it time to save
                     page.wait_for_timeout(1000)
                     uploaded += 1
                     progress.update(
                          task, advance=1, status=f"[green]{attempt_name}[/green]"
                     )
                else:
                     failed += 1
                     progress.update(
                          task, advance=1, status=f"[red]no update btn: {attempt_name}[/red]"
                     )

            except Exception as e:
                failed += 1
                progress.update(
                    task, advance=1, status=f"[red]error: {attempt_name}[/red]"
                )

    summary = {"uploaded": uploaded, "failed": failed, "total": len(attempt_links)}

    if uploaded > 0:
        success(f"Uploaded {uploaded}/{len(attempt_links)} quiz grades")
    if failed > 0:
        warning(f"{failed} quiz grades failed to upload")

    return summary
