from playwright.sync_api import sync_playwright
import os

def run():
    session_file = ".sessions/auth_session_uvijayan.json"
    if not os.path.exists(session_file):
        print("No session file found.")
        return
        
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=session_file)
        page = context.new_page()
        page.goto("https://purdue.brightspace.com/d2l/lms/dropbox/dropbox.d2l?ou=1368903")
        page.wait_for_load_state("networkidle")
        print(page.content())
        browser.close()

if __name__ == "__main__":
    run()
