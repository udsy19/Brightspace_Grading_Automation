from playwright.sync_api import sync_playwright
from config import load_config
from auth import login, handle_duo
from courses import select_course
from assignments import list_assignments, process_assignment
from grading import process_grading_workflow
from auth import login, handle_duo, save_session
from rich.console import Console
import time
import os
import sys

console = Console()

def main():
    # Load configuration
    config = load_config()
    username = config["username"]
    
    console.rule("[bold blue]Brightspace Automation v1.0[/bold blue]")
    
    with sync_playwright() as p:
        # Launch browser in headless mode as requested for the robust CLI experience.
        browser = p.chromium.launch(headless=True, slow_mo=100)
        
        # User-Specific Session Path
        auth_file = f"auth_session_{username}.json"
        
        context = None
        
        # 1. Try Loading Session
        if os.path.exists(auth_file):
            console.log(f"[dim]Found session file: {auth_file}[/dim]")
            try:
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    storage_state=auth_file
                )
                
                # Validate Session
                page = context.new_page()
                console.log("Validating session...")
                page.goto("https://purdue.brightspace.com/d2l/home")
                
                if "d2l/login" in page.url:
                    console.print("[yellow]Saved session has expired or is invalid.[/yellow]")
                    page.close()
                    context.close()
                    context = None
                    # Delete invalid file
                    os.remove(auth_file)
                    console.log("[dim]Deleted invalid session file.[/dim]")
                else:
                    console.print("[green]Session valid! Skipping login.[/green]")
                    
            except Exception as e:
                console.print(f"[red]Error loading session: {e}[/red]")
                if context: context.close()
                context = None
        
        # 2. Create Fresh Context if needed
        if not context:
            console.log("Starting fresh session...")
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            # Login Flow
            try:
                with console.status("[bold green]Authenticating...[/bold green]", spinner="dots"):
                    login(page, username, config["password"])
                
                # Duo Handling
                if "d2l/home" not in page.url:
                    handle_duo(page)
                else:
                    console.print("[green]Redirected to home directly.[/green]")
                
                # Save session for next time
                save_session(page, auth_file)
                console.print("[bold green]Login flow complete.[/bold green]")
                
            except Exception as e:
                console.print(f"[red]Login failed: {e}[/red]")
                return

        # Ensure page is ready (if we loaded from session, pages might be different)
        if len(context.pages) > 0:
            page = context.pages[0]
        else:
            page = context.new_page()
            
        console.print(f"[dim]Current Page: {page.title()} ({page.url})[/dim]")

        # 3. Course Selection
        selected_course = select_course(page)
        if not selected_course:
            return

        # 4. Assignments List & Selection
        selected_assignment = list_assignments(page)
        
        if selected_assignment:
            # 5. Process Assignment (Download)
            process_assignment(page, selected_assignment, selected_course['name'])
            
            # 6. Grading Workflow
            from grading import process_grading_workflow
            process_grading_workflow()
            
        else:
            # Fallback if no assignment selected but user wants to grade
            console.print("[yellow]No assignment selected.[/yellow]")
            from grading import process_grading_workflow
            process_grading_workflow()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold red]Operation cancelled by user (Ctrl+C). Exiting gracefully...[/bold red]")
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
    except Exception as e:
        console.print_exception(show_locals=True)
