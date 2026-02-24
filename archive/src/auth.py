from rich.console import Console
import time
from playwright.sync_api import Page, TimeoutError
import re

console = Console()

def login(page: Page, username, password):
    """
    Logs in to Purdue Brightspace.
    """
    console.log("Navigating to login page...")
    page.goto("https://purdue.brightspace.com/d2l/login")

    # Step 1: Check for Campus Selection (Purdue West Lafayette)
    try:
        campus_selector = "a[title='Purdue West Lafayette Login']"
        if page.is_visible(campus_selector, timeout=5000):
            console.log("Found Campus Selection page. Clicking 'Purdue West Lafayette / Indianapolis'...")
            page.click(campus_selector)
            page.wait_for_load_state("networkidle")
    except Exception:
        pass # Ignore

    # Step 2: Login Form
    console.log("Waiting for login fields...")
    try:
        page.wait_for_selector("input[name='j_username'], input[id='username']", timeout=10000)
        
        page.fill("input[name='j_username'], input[id='username']", username)
        page.fill("input[name='j_password'], input[id='password']", password)
        page.click("button[type='submit'], input[type='submit']")
    except TimeoutError:
        if "d2l/home" in page.url:
            console.log("[green]Already logged in.[/green]")
            return
        else:
            console.log(f"[red]Stuck on page: {page.title()}[/red]")
            raise Exception("Login fields not found and not logged in.")

def handle_duo(page: Page):
    """
    Handles the Duo 2FA screen.
    """
    console.rule("[bold yellow]Duo Authentication[/bold yellow]")
    console.log("Waiting for Duo screen...")
    
    try:
        try:
            other_options_btn = page.locator(".other-options-link").or_(page.locator("text='Other options'"))
            other_options_btn.wait_for(state="visible", timeout=15000)
            
            console.log("Duo screen detected.")
            console.log("Clicking 'Other options'...")
            other_options_btn.first.click()
            
            # Step 2: Select "Duo Push"
            console.log("Selecting 'Duo Push'...")
            duo_push_option = page.locator("text='Duo Push'")
            duo_push_option.wait_for(state="visible", timeout=10000)
            duo_push_option.first.click()
            
        except TimeoutError:
            console.log("[yellow]Duo interaction elements not found. Checking if waiting for code or already done.[/yellow]")
            if "d2l/home" in page.url:
                return

        console.log("Waiting for verification code...")
        page.wait_for_selector("text=Verify it's you", timeout=10000)
        
        time.sleep(1) 
        content_text = page.inner_text("body")
        
        code_match = re.search(r'Verify it.*?(\d{3})\b', content_text, re.DOTALL | re.IGNORECASE)
        
        console.print()
        console.print("[bold red]" + "="*40 + "[/bold red]")
        console.print("[bold white on red] DUO AUTHENTICATION REQUIRED [/bold white on red]", justify="center")
        
        if code_match:
             code = code_match.group(1)
             console.print(f"[bold yellow]VERIFICATION CODE: {code}[/bold yellow]", justify="center")
             console.print("[dim]Please match this code in your Duo Mobile app.[/dim]", justify="center")
        else:
            potential_codes = re.findall(r'\b\d{3}\b', content_text)
            if potential_codes:
                console.print(f"POTENTIAL CODES: {', '.join(potential_codes)}")
            else:
                console.print("[red]Could not extract code automatically.[/red]")
                console.print(page.inner_text("body")[:500])

        console.print("[bold red]" + "="*40 + "[/bold red]")
        console.print()
        
        console.log("Waiting for authentication approval...")
        page.wait_for_url("**/d2l/home/**", timeout=60000)
        console.print("[bold green]Authentication successful![/bold green]")
        
    except Exception as e:
        if "d2l/home" in page.url:
            console.print("[green]Skipped Duo (already authenticated).[/green]")
        else:
            raise e


def save_session(page: Page, path: str = "auth.json"):
    """
    Saves the current browser context state (cookies, local storage) to a file.
    """
    try:
        page.context.storage_state(path=path)
        console.log(f"[dim]Session saved to {path}[/dim]")
    except Exception as e:
        console.log(f"[red]Failed to save session: {e}[/red]")
