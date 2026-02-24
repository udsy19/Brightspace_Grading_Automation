import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from brightspace.browser import BrightspaceBrowser
from brightspace.auth import login, handle_duo
from brightspace.courses import get_courses
from brightspace.assignments import get_assignments_data, get_submission_links
from config import BRIGHTSPACE_URL
from ui import console, header, info, success, error

def verify():
    header("Verification Script")
    
    browser = BrightspaceBrowser()
    page = browser.launch(headless=True)
    
    try:
        # 1. Login / Restore
        page.goto(f"{BRIGHTSPACE_URL}/d2l/home")
        if not browser.is_logged_in():
            info("Logging in...")
            if not login(page):
                error("Login failed")
                return
            if not handle_duo(page):
                error("Duo failed")
                return
        else:
            success("Session restored")
            
        # 2. Courses
        info("Scanning courses...")
        courses = get_courses(page)
        if not courses:
            error("No courses found")
            return
        success(f"Found {len(courses)} courses: {[c['name'] for c in courses]}")
        
        # 3. Enter First Course
        target = courses[0]
        info(f"Navigating to course: {target['name']}")
        page.goto(BRIGHTSPACE_URL + target['href'])
        page.wait_for_load_state("networkidle")
        
        # 4. Assignments
        info("Scanning assignments...")
        assignments = get_assignments_data(page)
        if not assignments:
            error("No assignments found")
            return
        success(f"Found {len(assignments)} assignments")
        
        # 5. Enter First Assignment
        target_asm = assignments[0]
        info(f"Checking submissions for: {target_asm['name']}")
        
        # We use the logic from downloader/assignments to find students
        # Note: get_submission_links navigates inside
        links = get_submission_links(page, target_asm)
        success(f"Found {len(links)} student submissions")
        
        console.print("\n[bold green]VERIFICATION SUCCESSFUL[/bold green]")
        
    except Exception as e:
        console.print_exception()
    finally:
        browser.close()

if __name__ == "__main__":
    verify()
