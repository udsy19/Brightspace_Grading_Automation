"""Quiz listing and attempt scraping"""

import time
from pathlib import Path
from playwright.sync_api import Page, TimeoutError
from rich.table import Table
from tenacity import retry, wait_exponential, stop_after_attempt

from brightspace.models import BrightspaceQuiz
from logger import logger
from config import BRIGHTSPACE_URL
from ui import console, warning, pick
from brightspace.assignments import retry_interaction, safe_goto, safe_click


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def get_quizzes_data(page: Page, course_href: str) -> list[BrightspaceQuiz]:
    """
    Non-interactive: scrape quiz table and return list of BrightspaceQuiz Pydantic models.
    Always routes to the instructor's Manage Quizzes page to see attempt numbers.
    """
    try:
        org_unit = course_href.split("/home/")[1].split("?")[0]
        manage_url = f"{BRIGHTSPACE_URL}/d2l/lms/quizzing/admin/quizzes_manage.d2l?ou={org_unit}"
        logger.debug(f"Going directly to quizzes manage url: {manage_url}")
        page.goto(manage_url)
        page.wait_for_load_state("networkidle")
        return _scrape_quiz_table(page)
    except IndexError:
        logger.error(f"Failed to extract org_unit from course_href: {course_href}")
        raise ValueError(f"Could not extract org_unit from course_href to find Quizzes: {course_href}")


def _scrape_quiz_table(page: Page) -> list[BrightspaceQuiz]:
    quizzes = []
    try:
        page.wait_for_selector(".d2l-table tbody tr", timeout=5000)
    except TimeoutError:
        logger.debug("Timeout waiting for quiz table. Assuming no quizzes.")
        return []

    try:
        page.wait_for_selector(".d2l-table tbody tr", timeout=5000)
        rows = page.locator(".d2l-table tbody tr")
        count = rows.count()

        for i in range(count):
            row = rows.nth(i)
            # Find the link that has the quiz name
            link = row.locator("th a, td a[title*='Quiz'], td a.d2l-link").first
            
            if link.count() > 0:
                name = link.inner_text().strip()
                href = link.get_attribute("href")
                
                completed = "-"
                
                # Check for "Published" column e.g., "M/N" by finding a label with a slash
                # In Manage Quizzes, it's typically in td.d2l-table-cell-last
                label_with_slash = row.locator("td.d2l-table-cell-last label, label:has-text('/')")
                if label_with_slash.count() > 0:
                     text = label_with_slash.first.inner_text().strip()
                     if "/" in text:
                          parts = text.split("/")
                          if len(parts) == 2:
                               completed = parts[1].strip()
                
                # Check if it's an evaluation-capable link, usually contains 'qi='
                if "qi=" in href:
                    qi = href.split("qi=")[1].split("&")[0]
                    try:
                        quizzes.append(BrightspaceQuiz(
                            name=name,
                            href=href,
                            qi=qi,
                            completed=completed
                        ))
                    except Exception as e:
                         logger.error(f"Failed to parse BrightspaceQuiz: {e}")
                # if the link is just a view link, check row attributes
                elif "quiz_manage" in href or "quiz_action" in href:
                    qi_locator = row.locator("input[name*='qi'], a[href*='qi=']")
                    if qi_locator.count() > 0:
                         qi_href = qi_locator.first.get_attribute('href')
                         if qi_href and "qi=" in qi_href:
                             qi = qi_href.split("qi=")[1].split("&")[0]
                             try:
                                 quizzes.append(BrightspaceQuiz(
                                     name=name,
                                     href=href,
                                     qi=qi,
                                     completed=completed
                                 ))
                             except Exception as e:
                                 logger.error(f"Failed to parse BrightspaceQuiz: {e}")
    except Exception as e:
        logger.warning(f"Error scraping quiz list: {e}")
        console.log(f"[yellow]Error scraping quiz list: {e}[/yellow]")

    return quizzes


def get_quiz_submission_links(page: Page, quiz: dict, org_unit: str) -> list[tuple[str, str]]:
    """
    Navigate into a quiz's grading page and return list of (student_name, attempt_href) tuples.
    """
    # Construct the grading URL manually
    grading_url = f"https://purdue.brightspace.com/d2l/lms/quizzing/admin/mark/quiz_mark_users.d2l?ou={org_unit}&qi={quiz.qi}"
    console.log(f"Navigating to quiz grading: {grading_url}")
    safe_goto(page, grading_url)

    # Setup Page Size to 200
    try:
        page_size_selector = page.locator("select[title*='page'], select[aria-label*='page']")
        if page_size_selector.count() > 0:
            console.log("Setting page size to 200...")
            page_size_selector.first.select_option(value="200")
            page.wait_for_load_state("networkidle")
    except Exception:
        pass

    console.log("Scanning student attempts...")
    student_links = []

    try:
        page.wait_for_selector(".d2l-table tbody tr", timeout=5000)
        rows = page.locator("tr")
        count = rows.count()

        current_student = "Unknown"

        for i in range(count):
            row = rows.nth(i)
            text = row.inner_text()
            
            # This logic depends strongly on the DOM structure shown in the screenshots.
            # Row 1 might be student name, Row 2 might be the attempt link.
            # We look for links with text like "attempt 1"
            
            # 1. Identify if this row contains a student name
            # Often learner names have a specific class or are plain text in the first column
            learner_cell = row.locator("th, td").first
            if learner_cell.count() > 0:
                cell_text = learner_cell.inner_text().strip()
                if cell_text and "attempt" not in cell_text.lower() and "overall grade" not in cell_text.lower():
                    # It might be a picture/checkbox cell + name. Check for name.
                    name_locator = row.locator("label, .d2l-textblock")
                    if name_locator.count() > 0:
                        potential_name = name_locator.first.inner_text().strip()
                        if potential_name:
                            current_student = potential_name

            # 2. Identify if this row contains an attempt link
            attempt_link = row.locator("a:has-text('attempt')").first
            if attempt_link.count() > 0:
                a_name = attempt_link.inner_text().strip()
                a_href = attempt_link.get_attribute("href")
                
                # Brightspace quiz attempts often use JavaScript routing (e.g. Nav.Go)
                if a_href and a_href.startswith("javascript"):
                    a_action = attempt_link.get_attribute("onclick")
                    if a_action and "Nav.Go" in a_action:
                        a_href = a_action
                
                if a_href:
                    # If we somehow missed the student name, grab it from the row text if possible
                    if current_student == "Unknown" and cell_text:
                        current_student = cell_text.split('\n')[0].strip()

                    student_links.append((f"{current_student} - {a_name}", a_href))

        if not student_links:
            console.print("[yellow]No quiz attempts found in list.[/yellow]")

    except Exception as e:
        console.print(f"[red]Error scanning attempts: {e}[/red]")

    return student_links


def download_quiz_attempts(
    page: Page,
    student_links: list[tuple[str, str]],
    submissions_dir: Path,
) -> dict:
    submissions_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0
    failed = 0

    from ui import make_download_progress
    progress = make_download_progress()

    with progress:
        task = progress.add_task(
            "Downloading quiz attempts",
            total=len(student_links),
            status="starting...",
        )

        for student_attempt, href in student_links:
            # Sanitize username for folder
            safe_name = "".join(
                c if c.isalnum() or c in "-_" else "_" for c in student_attempt
            ).strip("_")

            student_dir = submissions_dir / safe_name
            
            # Resume capability
            if student_dir.exists() and (student_dir / "submission.txt").exists():
                skipped += 1
                progress.update(
                    task, advance=1, status=f"[dim]skipped {safe_name}[/dim]"
                )
                continue

            student_dir.mkdir(exist_ok=True)
            
            # Use evaluate if it's a script, otherwise safe_goto
            try:
                if href.startswith("var ") or "Nav.Go" in href:
                    iife_script = f"(() => {{ {href} }})();"
                    with page.expect_navigation():
                        page.evaluate(iife_script)
                else:
                    full_url = href if href.startswith("http") else BRIGHTSPACE_URL + href
                    safe_goto(page, full_url)
                
                # Wait for questions to load, but don't crash if they simply don't exist
                try:
                    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
                    page.wait_for_selector("div.d2l-textblock", timeout=10000)
                except PlaywrightTimeoutError:
                    pass
                
                # Scrape questions and answers
                # The DOM shown matches multiple questions typically wrapped in something like:
                # Question 1
                # <div class="d2l-htmlblock"> prompt </div>
                # <div class="d2l-htmlblock"> answer </div>
                
                # We extract all text blocks to capture everything linearly, which is good enough for AI
                text_blocks = page.locator(".d2l-htmlblock, .d2l-textblock")
                blocks_count = text_blocks.count()
                
                extracted_content = []
                for idx in range(blocks_count):
                    text = text_blocks.nth(idx).inner_text().strip()
                    if text:
                        extracted_content.append(text)
                
                if extracted_content:
                    # Remove exact duplicates that might happen from nested blocks
                    unique_content = []
                    for content in extracted_content:
                        if not unique_content or content not in unique_content[-1]:
                           unique_content.append(content)
                           
                    final_text = "\n\n".join(unique_content)
                else:
                    final_text = "No written submission content found."
                    
                (student_dir / "submission.txt").write_text(final_text, encoding="utf-8")
                downloaded += 1
                progress.update(
                    task, advance=1, status=f"[green]{safe_name}[/green]"
                )
                else:
                    failed += 1
                    progress.update(
                        task, advance=1, status=f"[red]empty {safe_name}[/red]"
                    )
                    
                # If we used the SPA router to get here, back out to the table for the next student
                if href.startswith("var ") or "Nav.Go" in href:
                    page.go_back()
                    page.wait_for_selector(".d2l-table tbody tr", timeout=10000)
                    
            except Exception as e:
                logger.error(f"Failed to download {student_attempt}: {e}")
                traceback.print_exc() if "logger" not in globals() else None
                failed += 1
                progress.update(
                    task, advance=1, status=f"[red]failed {safe_name}[/red]"
                )
                # Ensure we reset state even on failure if we had already navigated
                if href.startswith("var ") or "Nav.Go" in href:
                    try:
                        page.go_back()
                    except Exception:
                        pass

    console.print()
    summary = {
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        "total": len(student_links),
    }

    from ui import success
    success(
        f"Quiz download complete: {downloaded} scraped, {skipped} skipped, {failed} failed"
    )
    return summary

