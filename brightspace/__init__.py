"""Brightspace LMS browser automation module"""

from .browser import BrightspaceBrowser
from .auth import login, handle_duo, save_session, load_session
from .courses import get_courses
from .assignments import (
    get_submission_links, safe_goto, safe_click, retry_interaction,
)
from .downloader import download_submissions
from .uploader import upload_grades
