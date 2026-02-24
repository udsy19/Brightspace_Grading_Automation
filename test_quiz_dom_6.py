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

        url = "https://purdue.brightspace.com/d2l/lms/quizzing/admin/mark/quiz_mark_attempt.d2l?ou=1368903&qi=1246273&attempt=1&d2l_user=346460"
        print("Testing synthetic URL:", url)
        response = page.goto(url)
        page.wait_for_load_state("networkidle")
        
        print(f"Status: {response.status}")
        print(f"Final URL: {page.url}")
        
        # Test if we see "d2l-htmlblock" or "Attempt" text
        html = page.content()
        if "Attempt" in html:
            print("Found Attempt text in payload, it probably loaded correctly!")
        
        browser.close()

if __name__ == "__main__":
    test()
