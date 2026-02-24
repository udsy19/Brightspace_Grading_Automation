from playwright.sync_api import sync_playwright
import json
from pathlib import Path

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        session_file = Path(".sessions/auth_session_uvijayan.json")
        if session_file.exists():
            session_data = json.loads(session_file.read_text())
            cookies = session_data.get("cookies", session_data)
            context.add_cookies(cookies)

        url = "https://purdue.brightspace.com/d2l/lms/quizzing/admin/mark/quiz_mark_users.d2l?ou=1368903&qi=1246273"
        print("Loading homepage")
        page.goto(url)
        page.wait_for_selector(".d2l-table tbody tr", timeout=10000)
        
        script = "var n=new D2L.NavInfo();n.action='Custom';n.actionParam='mark,26949777,346460';Nav.Go(n, false, false);"
        print("Evaluating Nav.Go script:")
        with page.expect_navigation():
            page.evaluate(script)
        page.wait_for_load_state("networkidle")
        
        print(f"Final URL: {page.url}")
        
        print("Going back...")
        page.go_back()
        page.wait_for_selector(".d2l-table tbody tr", timeout=10000)
        
        print(f"Back URL: {page.url}")
        
        browser.close()

if __name__ == "__main__":
    test()
