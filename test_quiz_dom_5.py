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
        page.goto(url)
        
        try:
            page.wait_for_selector(".d2l-table tbody tr", timeout=10000)
            rows = page.locator(".d2l-table tbody tr")
            for i in range(min(10, rows.count())):
                row = rows.nth(i)
                links = row.locator("a")
                for j in range(links.count()):
                    lnk = links.nth(j)
                    if "attempt" in lnk.inner_text().lower():
                        print("Clicking attempt link...")
                        lnk.click()
                        page.wait_for_load_state("networkidle")
                        print("Navigated to:", page.url)
                        return
        except Exception as e:
            pass
            
        browser.close()

if __name__ == "__main__":
    test()
