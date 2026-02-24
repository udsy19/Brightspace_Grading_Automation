import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from brightspace.browser import BrightspaceBrowser
from playwright.sync_api import sync_playwright
from main import connect, get_browser

if __name__ == "__main__":
    if connect():
        page = get_browser().page
        page.goto("https://purdue.brightspace.com/d2l/lms/quizzing/admin/quizzes_manage.d2l?ou=1368903")
        page.wait_for_load_state("networkidle")
        try:
            table_html = page.locator(".d2l-table").first.inner_html()
            with open("quizzes_manage_table.html", "w") as f:
                f.write(table_html)
            print("Dumped quizzes_manage_table.html")
        except Exception as e:
            print("Error dumping table:", e)
        get_browser().close()

