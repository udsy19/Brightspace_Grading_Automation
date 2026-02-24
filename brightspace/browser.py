"""Browser lifecycle management with session persistence"""

import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from config import SESSION_DIR, BRIGHTSPACE_URL, get_credentials, get_session_path
from ui import console, info, success, error, warning


class BrightspaceBrowser:
    """Manages a Playwright browser instance for Brightspace."""

    def __init__(self):
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._username: str = ""

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not launched. Call launch() first.")
        return self._page

    @property
    def is_running(self) -> bool:
        return self._page is not None

    def launch(self, headless: bool = False) -> Page:
        """Launch browser, optionally restoring a saved session."""
        creds = get_credentials()
        self._username = creds.get("username", "unknown")
        session_path = get_session_path(self._username)

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

        if session_path.exists():
            try:
                self._context = self._browser.new_context(
                    storage_state=str(session_path),
                    viewport={"width": 1280, "height": 900},
                )
                self._page = self._context.new_page()
                info("Restored saved session")
                return self._page
            except Exception:
                warning("Saved session invalid, starting fresh")

        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 900},
        )
        self._page = self._context.new_page()
        return self._page

    def save_session(self):
        """Persist cookies and localStorage for next launch."""
        if self._context is None:
            return
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        path = get_session_path(self._username)
        try:
            self._context.storage_state(path=str(path))
            info(f"Session saved to {path.name}")
        except Exception as e:
            warning(f"Could not save session: {e}")

    def is_logged_in(self) -> bool:
        """Check if current page is inside Brightspace."""
        try:
            return "d2l/home" in self._page.url
        except Exception:
            return False

    def go_home(self):
        """Navigate to Brightspace homepage."""
        self.page.goto(f"{BRIGHTSPACE_URL}/d2l/home")
        self.page.wait_for_load_state("networkidle")

    def close(self):
        """Shut down browser."""
        try:
            self.save_session()
        except Exception:
            pass
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
