from playwright.sync_api import Page
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from utils import retry_interaction

console = Console()

@retry_interaction()
def safe_goto(page: Page, url: str):
    """Safely navigate to a URL with retries."""
    page.goto(url)
    page.wait_for_load_state("networkidle")

@retry_interaction()
def safe_click(locator):
    """Safely click a locator with retries."""
    locator.click()

def list_assignments(page: Page):
    """
    Navigates to the Assignments (Dropbox) page, lists them, and prompts user to select one.
    Returns the selected assignment object or None.
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
    
    # 4. Prompt for selection
    while True:
        choice = Prompt.ask("Select an assignment by index (or 'q' to quit)", choices=[str(i+1) for i in range(len(assignments))] + ['q'])
        if choice.lower() == 'q':
            return None
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(assignments):
                return assignments[idx]
            else:
                console.print("[red]Invalid index.[/red]")
                
    return None

def process_assignment(page: Page, assignment: dict, course_name: str):
    """
    Navigates to the assignment, lists students, and downloads files.
    """
    if not assignment:
        return

    console.rule(f"[bold blue]Processing: {assignment['name']}[/bold blue]")
    
    # 1. Navigate
    full_url = "https://purdue.brightspace.com" + assignment['href']
    console.log(f"Navigating to assignment: {full_url}")
    safe_goto(page, full_url)
    
    # 2. Setup Page Size to 200 (max usually) to see all students
    try:
        page_size_selector = page.locator("select[title*='page'], select[aria-label*='page']")
        if page_size_selector.count() > 0:
            console.log("Setting page size to 200...")
            page_size_selector.first.select_option(value="200")
            page.wait_for_load_state("networkidle")
    except Exception:
        pass

    # 3. List Students
    console.log("Scanning student list...")
    
    try:
        page.wait_for_selector(".d2l-table tbody tr", timeout=5000)
        rows = page.locator(".d2l-table tbody tr")
        count = rows.count()
        console.log(f"Found {count} students.")
        
        student_links = []
        for i in range(count):
            row = rows.nth(i)
            # Look for student name link
            # Usually the first 'a' tag in the row that isn't a checkbox or icon
            name_link = row.locator("th a, td a").first
            
            if name_link.count() > 0:
                s_name = name_link.inner_text().strip()
                s_href = name_link.get_attribute("href")
                
                if s_href and ("user" in s_href or "history" in s_href): 
                    student_links.append((s_name, s_href))
        
        if not student_links:
            console.print("[yellow]No students found in list.[/yellow]")
            return

        import os
        from pathlib import Path
        
        # 4. Iterate and Download
        for s_name, s_href in student_links:
            console.print(f"Processing student: [cyan]{s_name}[/cyan]")
            
            # Clean names
            safe_course = "".join(c for c in course_name if c.isalnum() or c in (' ', '_')).strip()
            safe_assign = "".join(c for c in assignment['name'] if c.isalnum() or c in (' ', '_')).strip()
            safe_student = "".join(c for c in s_name if c.isalnum() or c in (' ', '_')).strip()
            
            save_dir = Path(f"downloads/{safe_course}/{safe_assign}/{safe_student}")
            
            # Resume Capability: Skip if already done
            if save_dir.exists() and any(save_dir.iterdir()):
                console.print(f"[dim]Skipping {s_name} (already downloaded)[/dim]")
                continue
                
            save_dir.mkdir(parents=True, exist_ok=True)
            
            # Go to student page
            s_url = "https://purdue.brightspace.com" + s_href
            safe_goto(page, s_url)
            
            # 5. Find Download Button
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
            
            # Return to list is implicit by navigating to next student text
            # But wait, navigating to student page changes context.
            # We must go back to the assignment page OR navigate directly to next student.
            # Navigation directly to next student is what we do (s_url).
            # But if next iteration relies on `rows` locator? 
            # `student_links` list has URLs, so we don't need the table anymore. Good.

    except Exception as e:
        console.print_exception()
