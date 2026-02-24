"""Brightspace login + Duo 2FA handling — ported directly from src/auth.py"""

import re
import time
from pathlib import Path
from playwright.sync_api import Page, TimeoutError

from config import BRIGHTSPACE_URL, get_credentials, get_session_path, SESSION_DIR
from ui import console, info, success, error, warning, duo_code_display


def login(page: Page) -> bool:
    """
    Logs in to Purdue Brightspace.
    Exact implementation from src/auth.py.
    """
    creds = get_credentials()
    if not creds:
        error("No credentials found. Set PURDUE_USERNAME and PURDUE_PASSWORD in .env")
        return False

    username = creds["username"]
    password = creds["password"]

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
        pass  # Ignore

    # Step 2: Login Form
    console.log("Waiting for login fields...")
    try:
        page.wait_for_selector("input[name='j_username'], input[id='username']", timeout=10000)

        page.fill("input[name='j_username'], input[id='username']", username)
        page.fill("input[name='j_password'], input[id='password']", password)
        page.click("button[type='submit'], input[type='submit']")
        return True
    except TimeoutError:
        if "d2l/home" in page.url:
            console.log("[green]Already logged in.[/green]")
            return True
        else:
            console.log(f"[red]Stuck on page: {page.title()}[/red]")
            error("Login fields not found and not logged in.")
            return False


def handle_duo(page: Page) -> bool:
    """
    Handles the Duo 2FA screen.
    Exact implementation from src/auth.py.
    """
    console.rule("[bold yellow]Duo Authentication[/bold yellow]")
    console.log("Waiting for Duo screen...")

    try:
        try:
            # Use .first to avoid strict mode violation if multiple elements match
            other_options_btn = page.locator(".other-options-link").or_(page.locator("text='Other options'")).first
            other_options_btn.wait_for(state="visible", timeout=15000)

            console.log("Duo screen detected.")
            console.log("Clicking 'Other options'...")
            other_options_btn.click()

            # Step 2: Select "Duo Push"
            console.log("Selecting 'Duo Push'...")
            duo_push_option = page.locator("text='Duo Push'")
            duo_push_option.wait_for(state="visible", timeout=10000)
            duo_push_option.first.click()

        except TimeoutError:
            console.log("[yellow]Duo interaction elements not found. Checking if waiting for code or already done.[/yellow]")
            if "d2l/home" in page.url:
                return True

        console.log("Waiting for verification code...")
        page.wait_for_selector("text=Verify it's you", timeout=10000)

        time.sleep(1)
        content_text = page.inner_text("body")

        code_match = re.search(r'Verify it.*?(\d{3})\b', content_text, re.DOTALL | re.IGNORECASE)

        if code_match:
            code = code_match.group(1)
            duo_code_display(code)
        else:
            potential_codes = re.findall(r'\b\d{3}\b', content_text)
            if potential_codes:
                duo_code_display(potential_codes[0])
            else:
                console.print("[red]Could not extract code automatically.[/red]")
                console.print(content_text[:500])

        console.log("Waiting for authentication approval...")
        page.wait_for_url("**/d2l/home/**", timeout=60000)
        console.print("[bold green]Authentication successful![/bold green]")
        return True

    except Exception as e:
        if "d2l/home" in page.url:
            console.print("[green]Skipped Duo (already authenticated).[/green]")
            return True
        else:
            error(f"Duo authentication failed: {e}")
            return False


def save_session(page: Page, path: str = None):
    """
    Saves the current browser context state (cookies, local storage) to a file.
    """
    if path is None:
        creds = get_credentials()
        username = creds.get("username", "unknown") if creds else "unknown"
        session_path = get_session_path(username)
        path = str(session_path)

    try:
        page.context.storage_state(path=path)
        console.log(f"[dim]Session saved to {path}[/dim]")
    except Exception as e:
        console.log(f"[red]Failed to save session: {e}[/red]")


def load_session(username: str) -> Path | None:
    """Return session file path if it exists."""
    path = get_session_path(username)
    return path if path.exists() else None
