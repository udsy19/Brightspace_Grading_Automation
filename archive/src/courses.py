from playwright.sync_api import Page
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

console = Console()

def get_courses(page: Page):
    """
    Extracts course information from the Brightspace homepage.
    Returns a list of dictionaries: {'name': str, 'href': str}
    """
    console.log("[bold blue]Scanning for courses...[/bold blue]")
    
    # Wait for the enrollment cards to be present.
    # d2l-enrollment-card is the custom element.
    try:
        page.wait_for_selector("d2l-enrollment-card", timeout=15000)
    except Exception:
        console.print("[yellow]Warning: No enrollment cards found immediately. waiting a bit longer...[/yellow]")
        page.wait_for_timeout(2000)

    # We use evaluate to traverse Shadow DOMs recursively to find enrollment cards
    courses = page.evaluate("""() => {
        const results = [];
        
        function findCardsRecursively(root, depth=0) {
            if (depth > 10) return; // Safety break
            
            // Check current level
            const cards = root.querySelectorAll('d2l-enrollment-card');
            cards.forEach(card => {
                if (card.shadowRoot) {
                    const innerCard = card.shadowRoot.querySelector('d2l-card');
                    if (innerCard) {
                        const text = innerCard.getAttribute('text') || innerCard.innerText;
                        const href = innerCard.getAttribute('href');
                        if (text && href) {
                            results.push({ name: text, href: href });
                        }
                    }
                }
            });
            
            // Go deeper into custom elements (children with shadowRoots)
            // accessing all elements is expensive, so we target d2l- specific or just iterate all
            // Iterating all children is safer.
            const candidates = root.querySelectorAll('*');
            candidates.forEach(el => {
                if (el.shadowRoot) {
                    findCardsRecursively(el.shadowRoot, depth + 1);
                }
            });
        }
        
        const myCourses = document.querySelector('d2l-my-courses');
        if (myCourses && myCourses.shadowRoot) {
            findCardsRecursively(myCourses.shadowRoot);
        }
        
        return results;
    }""")
    
    if not courses:
        console.print("[bold red]Debug: No courses found (recursive search). Dumping homepage content...[/bold red]")
        with open("homepage_debug_recursive.html", "w", encoding="utf-8") as f:
            f.write(page.content())
            
    return courses
    
    return courses

def select_course(page: Page, auto_select_keyword: str = None):
    """
    Displays a list of courses and prompts the user to select one.
    Navigates to the selected course.
    """
    courses = get_courses(page)
    
    if not courses:
        console.print("[bold red]No courses found![/bold red]")
        return
    
    # Display courses using Rich Table
    table = Table(title="Available Courses")
    table.add_column("Index", justify="right", style="cyan", no_wrap=True)
    table.add_column("Course Name", style="magenta")
    table.add_column("Link", style="green")

    for idx, course in enumerate(courses):
        name = course['name'].split(',')[0]
        table.add_row(str(idx + 1), name, course['href'])
    
    console.print(table)
    
    selected_course = None
    
    # Auto-selection logic
    if auto_select_keyword:
        console.print(f"[yellow]Auto-selecting course matching: '{auto_select_keyword}'[/yellow]")
        for course in courses:
            if auto_select_keyword.lower() in course['name'].lower():
                selected_course = course
                console.print(f"[bold green]Auto-selected: {course['name']}[/bold green]")
                break
        if not selected_course:
            console.print(f"[red]No course found matching '{auto_select_keyword}'. Falling back to prompt.[/red]")
            
    if not selected_course:
        # Prompt user
        while True:
            choice = Prompt.ask("Select a course by index", choices=[str(i+1) for i in range(len(courses))])
            if choice.isdigit() and 1 <= int(choice) <= len(courses):
                selected_course = courses[int(choice) - 1]
                break
            else:
                console.print("[red]Invalid selection. Please try again.[/red]")
            
    # Navigate
    full_url = "https://purdue.brightspace.com" + selected_course['href']
    console.print(f"[bold green]Navigating to: {selected_course['name'].split(',')[0]}[/bold green]")
    page.goto(full_url)
    
    # Wait for course page load
    page.wait_for_load_state("networkidle")
    console.print(f"[bold]Arrived at: {page.title()}[/bold]")
    
    return selected_course
