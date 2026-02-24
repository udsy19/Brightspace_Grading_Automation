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

        url = "https://purdue.brightspace.com/d2l/home/1368903"
        print("Loading homepage")
        page.goto(url)
        page.wait_for_load_state("networkidle")
        
        script = "var n=new D2L.NavInfo();n.action='Custom';n.actionParam='mark,26949777,346460';Nav.Go(n, false, false);"
        print("Evaluating Nav.Go script:")
        print(script)
        page.evaluate(script)
        page.wait_for_load_state("networkidle")
        
        print(f"Final URL: {page.url}")
        html = page.content()
        if "Attempt" in html:
            print("Found Attempt text in payload!")
        else:
            print("Could not find Attempt text.")
            
        browser.close()

if __name__ == "__main__":
    test()
