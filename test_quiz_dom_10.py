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
        
        script = "var n=new D2L.NavInfo();n.action='Custom';n.actionParam='mark,26949777,346460';Nav.Go(n, false, false);return false;"
        
        iife_script = f"(() => {{ {script} }})();"
        print("Evaluating Nav.Go script with IIFE...")
        with page.expect_navigation():
            page.evaluate(iife_script)
            
        page.wait_for_load_state("networkidle")
        
        artifact_dir = Path("/Users/udsy/.gemini/antigravity/brain/0ddfab44-497f-4005-8c9f-b350e83cd084")
        if artifact_dir.exists():
            print("Saving screenshot to artifact dir...")
            page.screenshot(path=str(artifact_dir / "quiz_attempt_timeout_view.png"), full_page=True)
        
        html = page.content()
        with open("quiz_attempt_content.html", "w") as f:
            f.write(html)
            
        print("Looking for iframes...")
        for i, frame in enumerate(page.frames):
            print(f"Frame {i}: url={frame.url}, name={frame.name}")
        
        print("Done.")
        browser.close()

if __name__ == "__main__":
    test()
