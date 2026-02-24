"""Configuration: paths, credentials, constants"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

CLASSES_DIR = BASE_DIR / "classes"
SESSION_DIR = BASE_DIR / ".sessions"

SEMESTERS = ["Fall", "Spring", "Summer", "Winter"]

BRIGHTSPACE_URL = "https://purdue.brightspace.com"

GITIGNORE_TEMPLATE = """# FERPA Protection - Never commit student data
roster.csv
*/submissions/
*/grading/audit/
*.bak

# System
.DS_Store
__pycache__/
.sessions/
"""


def ensure_base_dirs():
    CLASSES_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def get_credentials() -> dict:
    """Load Purdue credentials from environment."""
    username = os.getenv("PURDUE_USERNAME")
    password = os.getenv("PURDUE_PASSWORD")
    if not username or not password:
        return {}
    return {"username": username, "password": password}


def get_anthropic_key() -> str | None:
    """Load Anthropic API key from environment."""
    return os.getenv("ANTHROPIC_API_KEY")


def get_session_path(username: str) -> Path:
    """Get the session file path for a given username."""
    return SESSION_DIR / f"auth_session_{username}.json"
