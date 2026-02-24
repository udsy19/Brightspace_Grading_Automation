from playwright.sync_api import sync_playwright
import time
import json
from pathlib import Path

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        session_file = Path(".sessions/auth_session_uvijayan.json")
        if session_file.exists():
            print("Loaded session file!")
            session_data = json.loads(session_file.read_text())
            cookies = session_data.get("cookies", session_data) # handle both formats
            context.add_cookies(cookies)

        url = "https://purdue.brightspace.com/d2l/lms/quizzing/admin/mark/quiz_mark_users.d2l?ou=1368903&qi=1246273"
        print(f"Loading {url}")
        page.goto(url)
        page.wait_for_load_state("networkidle")
        time.sleep(5)
        
        # Take a screenshot to see what's actually rendering
        page.screenshot(path="quiz_grading_screenshot.png", full_page=True)
        print("Saved quiz_grading_screenshot.png")
        
        html = page.content()
        Path("quiz_grading_body.html").write_text(html, encoding="utf-8")
        
        browser.close()

if __name__ == "__main__":
    test()
