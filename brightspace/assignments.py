"""Assignment listing and student submissions — ported directly from src/assignments.py"""

import time
import functools
from pathlib import Path
from playwright.sync_api import Page, TimeoutError
from rich.table import Table
from rich.prompt import Prompt
from tenacity import retry, wait_exponential, stop_after_attempt

from brightspace.models import BrightspaceAssignment
from logger import logger
from config import BRIGHTSPACE_URL
from ui import console, info, warning, error, pick


def retry_interaction(max_retries=3, delay=2, exceptions=(Exception,)):
    """
    Decorator to retry a function call upon failure.
    Exact implementation from src/utils.py.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        console.log(f"[yellow]Action failed: {e}. Retrying ({attempt+1}/{max_retries}) in {delay}s...[/yellow]")
                        time.sleep(delay)
                    else:
                        console.log(f"[red]Action failed after {max_retries} retries.[/red]")
            raise last_exception
        return wrapper
    return decorator


@retry_interaction()
def safe_goto(page: Page, url: str):
    """Safely navigate to a URL with retries."""
    page.goto(url)
    page.wait_for_load_state("networkidle")


@retry_interaction()
def safe_click(locator):
    """Safely click a locator with retries."""
    locator.click()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def get_assignments_data(page: Page, course_href: str) -> list[BrightspaceAssignment]:
    """
    Non-interactive: scrape assignment table and return list of BrightspaceAssignment objects.
    No user prompts. Used by the automatic pipeline.
    """
    logger.debug(f"Navigating to Assignments page via direct URL using href: {course_href}")
    try:
        org_unit = course_href.split("/home/")[1].split("?")[0]
        new_url = f"https://purdue.brightspace.com/d2l/lms/dropbox/dropbox.d2l?ou={org_unit}"
        logger.debug(f"Going directly to: {new_url}")
        page.goto(new_url)
    except IndexError:
        logger.error(f"Failed to parse org_unit from course_href: {course_href}")
        raise ValueError(f"Failed to parse org_unit from course_href: {course_href}")

    page.wait_for_load_state("networkidle")
    logger.debug("Page loaded")

    assignments = []
    try:
        page.wait_for_selector(".d2l-table tbody tr", timeout=5000)
        rows = page.locator(".d2l-table tbody tr")
        count = rows.count()
        logger.debug(f"Found {count} assignment rows")
    except TimeoutError:
        logger.debug("Timeout waiting for assignment table. Assuming no assignments.")
        return []

        for i in range(count):
            row = rows.nth(i)
            link = row.locator("a[href*='folder']").first

            if link.count() > 0:
                name = link.inner_text().strip()
                href = link.get_attribute("href")
                cells = row.locator("td")

                def get_cell_text(idx):
                    if cells.count() > idx:
                        return cells.nth(idx).inner_text().strip()
                    return "-"

                full_text_col1 = get_cell_text(1)
                due_date = ""
                if "Due on" in full_text_col1:
                    parts = full_text_col1.split("Due on")
                    if len(parts) > 1:
                        due_date = "Due on " + parts[1].strip()

                try:
                    assignments.append(BrightspaceAssignment(
                        name=name,
                        href=href,
                        due_date=due_date,
                        completed=get_cell_text(3)
                    ))
                except Exception as e:
                    logger.error(f"Failed to parse BrightspaceAssignment: {e} - Row: {name}")
    except Exception as e:
        logger.warning(f"Error scraping assignments table: {e}")
        raise

    logger.debug(f"Returning {len(assignments)} assignments")
    return assignments


def list_assignments(page: Page) -> dict | None:
    """
    Navigates to the Assignments (Dropbox) page, lists them, and prompts user to select one.
    Returns the selected assignment object or None.

    Exact logic from src/assignments.py.
    """
    console.rule("[bold magenta]Assignments Browser[/bold magenta]")

    # 1. Navigate to Assignments
    console.log("Looking for 'Assignments' link...")
    try:
        # Try direct link first.
        assignments_link = page.get_by_text("Assignments", exact=True).first
        if not assignments_link.is_visible():
            # Check for "Course Tools" dropdown
            course_tools = page.get_by_text("Course Tools").first
            if course_tools.is_visible():
                console.log("Opening 'Course Tools' menu...")
                course_tools.click()
                assignments_link = page.get_by_text("Assignments", exact=True).first

        if assignments_link.is_visible():
            console.log("Navigating to Assignments page...")
            assignments_link.click()
        else:
            # Fallback URL construction
            url = page.url
            if "/home/" in url:
                org_unit = url.split("/home/")[1].split("?")[0]
                new_url = f"https://purdue.brightspace.com/d2l/lms/dropbox/dropbox.d2l?ou={org_unit}"
                console.log(f"Constructing direct URL: {new_url}")
                safe_goto(page, new_url)
            else:
                console.print("[red]Could not find Assignments link.[/red]")
                return None

        page.wait_for_load_state("networkidle")

    except Exception as e:
        console.print(f"[red]Error navigating to assignments: {e}[/red]")
        return None

    # 2. Extract Assignments
    console.log("Scanning assignments...")

    # Check for empty state first
    if page.locator("d2l-empty-state-simple").is_visible() or "There are no assignments" in page.content():
        console.print("[yellow]This course has no assignments available.[/yellow]")
        return None

    assignments = []

    try:
        # Wait for the main table
        page.wait_for_selector(".d2l-table tbody tr", timeout=5000)
        rows = page.locator(".d2l-table tbody tr")
        count = rows.count()
        console.log(f"Found {count} rows in assignment table.")

        for i in range(count):
            row = rows.nth(i)
            # Find link with assignment name
            link = row.locator("a[href*='folder']").first

            if link.count() > 0:
                name = link.inner_text().strip()
                href = link.get_attribute("href")

                # Cells: 0=checkbox, 1=Assignment Name/Due Date, 2=New Submissions, 3=Completed, 4=Evaluated, 5=Feedback
                cells = row.locator("td")

                def get_cell_text(idx):
                    if cells.count() > idx:
                        return cells.nth(idx).inner_text().strip()
                    return "-"

                # Parse Due Date from Col 1 if present
                full_text_col1 = get_cell_text(1)
                due_date = ""
                if "Due on" in full_text_col1:
                    parts = full_text_col1.split("Due on")
                    if len(parts) > 1:
                        due_date = "Due on " + parts[1].strip()

                new_subs = get_cell_text(2)
                completed = get_cell_text(3)
                evaluated = get_cell_text(4)
                feedback = get_cell_text(5)

                assignments.append({
                    "name": name,
                    "href": href,
                    "due_date": due_date,
                    "new_subs": new_subs,
                    "completed": completed,
                    "evaluated": evaluated,
                    "feedback": feedback
                })

    except Exception as e:
        console.log(f"[yellow]Error scraping table: {e}[/yellow]")

    if not assignments:
        console.print("[yellow]No assignments found.[/yellow]")
        return None

    # 3. Display
    table = Table(title=f"Assignments for {page.title()}")
    table.add_column("Idx", justify="right", style="cyan")
    table.add_column("Assignment", style="magenta")
    table.add_column("Due Date", style="dim")
    table.add_column("New Subs", justify="center")
    table.add_column("Completed", justify="center")

    for idx, asm in enumerate(assignments):
        table.add_row(
            str(idx + 1),
            asm['name'],
            asm['due_date'],
            asm['new_subs'],
            asm['completed']
        )

    console.print(table)

    # 4. Prompt for selection using our pick UI
    names = [a['name'] for a in assignments]
    idx = pick(names, "Select an assignment")
    if idx is None:
        return None
    return assignments[idx]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def get_submission_links(page: Page, assignment: BrightspaceAssignment | dict) -> list[tuple[str, str]]:
    """
    Navigate into an assignment and return list of (student_name, href) tuples.
    Exact logic from src/assignments.py process_assignment().
    """
    href = assignment.href if isinstance(assignment, BrightspaceAssignment) else assignment['href']
    full_url = "https://purdue.brightspace.com" + href
    console.log(f"Navigating to assignment: {full_url}")
    safe_goto(page, full_url)

    # Setup Page Size to 200 (max usually) to see all students
    try:
        page_size_selector = page.locator("select[title*='page'], select[aria-label*='page']")
        if page_size_selector.count() > 0:
            console.log("Setting page size to 200...")
            page_size_selector.first.select_option(value="200")
            page.wait_for_load_state("networkidle")
    except Exception:
        pass

    # List Students
    console.log("Scanning student list...")
    student_links = []

    try:
        page.wait_for_selector(".d2l-table tbody tr", timeout=5000)
        rows = page.locator(".d2l-table tbody tr")
        count = rows.count()
        console.log(f"Found {count} students.")

        for i in range(count):
            row = rows.nth(i)
            # Look for student name link
            name_link = row.locator("th a, td a").first

            if name_link.count() > 0:
                s_name = name_link.inner_text().strip()
                s_href = name_link.get_attribute("href")

                if s_href and ("user" in s_href or "history" in s_href):
                    student_links.append((s_name, s_href))

        if not student_links:
            logger.warning("No students found in list.")
            console.print("[yellow]No students found in list.[/yellow]")

    except Exception as e:
        logger.error(f"Error scanning students: {e}")
        console.print(f"[red]Error scanning students: {e}[/red]")

    return student_links


def process_assignment(page: Page, assignment: dict, course_name: str, save_base: Path = None):
    """
    Navigates to the assignment, lists students, and downloads files.
    Exact implementation from src/assignments.py.
    """
    if not assignment:
        return

    console.rule(f"[bold blue]Processing: {assignment['name']}[/bold blue]")

    student_links = get_submission_links(page, assignment)
    if not student_links:
        return

    from pathlib import Path as P

    for s_name, s_href in student_links:
        console.print(f"Processing student: [cyan]{s_name}[/cyan]")

        # Clean names
        safe_course = "".join(c for c in course_name if c.isalnum() or c in (' ', '_')).strip()
        safe_assign = "".join(c for c in assignment['name'] if c.isalnum() or c in (' ', '_')).strip()
        safe_student = "".join(c for c in s_name if c.isalnum() or c in (' ', '_')).strip()

        if save_base:
            save_dir = save_base / safe_student
        else:
            save_dir = P(f"downloads/{safe_course}/{safe_assign}/{safe_student}")

        # Resume Capability: Skip if already done
        if save_dir.exists() and any(save_dir.iterdir()):
            console.print(f"[dim]Skipping {s_name} (already downloaded)[/dim]")
            continue

        save_dir.mkdir(parents=True, exist_ok=True)

        # Go to student page
        s_url = "https://purdue.brightspace.com" + s_href
        safe_goto(page, s_url)

        # Find Download Button
        if "No submissions" in page.content() or "No files" in page.content():
            console.print(f"  [dim]No submissions for {s_name}[/dim]")
        else:
            # Attempt Download
            try:
                download_btn = page.get_by_text("Download All Files").first
                if not download_btn.is_visible():
                    download_btn = page.locator("button:has_text('Download')").first

                if download_btn.is_visible():
                    console.print("  Found download button, clicking...")
                    with page.expect_download(timeout=10000) as download_info:
                        safe_click(download_btn)

                    download = download_info.value
                    fname = download.suggested_filename
                    download.save_as(save_dir / fname)
                    console.print(f"  [green]Downloaded: {fname}[/green]")
                else:
                    console.print("  [yellow]No bulk download found.[/yellow]")

            except Exception as e:
                console.print(f"  [red]Error downloading: {e}[/red]")
