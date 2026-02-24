from playwright.sync_api import sync_playwright
import time
import json
from pathlib import Path

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        session_file = Path("auth_session_uvijayan.json")
        if session_file.exists():
            cookies = json.loads(session_file.read_text())
            context.add_cookies(cookies)

        url = "https://purdue.brightspace.com/d2l/lms/quizzing/admin/mark/quiz_mark_users.d2l?ou=1368903&qi=1246273"
        print(f"Loading {url}")
        page.goto(url)
        page.wait_for_load_state("networkidle")
        time.sleep(5)
        
        # Wait for any d2l element to ensure DOM is populated
        try:
            page.wait_for_selector(".d2l-page-main, iframe", timeout=10000)
        except Exception as e:
            print("Timeout waiting for generic d2l selector")

        html = page.content()
        Path("quiz_grading_body.html").write_text(html, encoding="utf-8")
        print(f"Wrote quiz_grading_body.html ({len(html)} bytes)")

        browser.close()

if __name__ == "__main__":
    test()
