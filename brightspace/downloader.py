"""Download student submissions from Brightspace with progress tracking"""

import time
import functools
from pathlib import Path
from playwright.sync_api import Page

from config import BRIGHTSPACE_URL
from ui import console, info, success, warning, error, make_download_progress


def _retry(max_retries=3, delay=2):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt < max_retries:
                        time.sleep(delay)
            raise last_exc
        return wrapper
    return decorator


@_retry()
def _safe_goto(page: Page, url: str):
    page.goto(url)
    page.wait_for_load_state("networkidle")


def download_submissions(
    page: Page,
    student_links: list[tuple[str, str]],
    submissions_dir: Path,
) -> dict:
    """
    Download files for each student into submissions_dir/<username>/.

    Returns summary dict with counts.
    """
    submissions_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0
    no_submission = 0
    failed = 0

    progress = make_download_progress()

    with progress:
        task = progress.add_task(
            "Downloading submissions",
            total=len(student_links),
            status="starting...",
        )

        for student_name, href in student_links:
            # Sanitize username for folder
            safe_name = "".join(
                c if c.isalnum() or c in "-_" else "_" for c in student_name
            ).strip("_")

            student_dir = submissions_dir / safe_name

            # Resume: skip if already has files
            if student_dir.exists() and any(student_dir.iterdir()):
                skipped += 1
                progress.update(
                    task, advance=1, status=f"[dim]skipped {safe_name}[/dim]"
                )
                continue

            student_dir.mkdir(exist_ok=True)

            # Navigate to student's submission page
            full_url = href if href.startswith("http") else BRIGHTSPACE_URL + href
            try:
                _safe_goto(page, full_url)
            except Exception:
                failed += 1
                progress.update(
                    task, advance=1, status=f"[red]failed {safe_name}[/red]"
                )
                continue

            content = page.content()
            if "No submissions" in content or "No files" in content:
                no_submission += 1
                progress.update(
                    task, advance=1, status=f"[dim]no files {safe_name}[/dim]"
                )
                continue

            # Try to download
            try:
                download_btn = page.get_by_text("Download All Files").first
                if not download_btn.is_visible():
                    download_btn = page.locator("button:has-text('Download')").first

                if download_btn.is_visible():
                    with page.expect_download(timeout=15000) as dl_info:
                        download_btn.click()
                    dl = dl_info.value
                    dl.save_as(student_dir / dl.suggested_filename)
                    downloaded += 1
                    progress.update(
                        task, advance=1, status=f"[green]{safe_name}[/green]"
                    )
                else:
                    # No download button — try to grab inline text
                    _save_inline_submission(page, student_dir)
                    downloaded += 1
                    progress.update(
                        task, advance=1, status=f"[green]{safe_name} (text)[/green]"
                    )
            except Exception as e:
                # Try inline text as fallback
                try:
                    _save_inline_submission(page, student_dir)
                    downloaded += 1
                    progress.update(
                        task, advance=1, status=f"[green]{safe_name} (text)[/green]"
                    )
                except Exception:
                    failed += 1
                    progress.update(
                        task, advance=1, status=f"[red]error {safe_name}[/red]"
                    )

    console.print()
    summary = {
        "downloaded": downloaded,
        "skipped": skipped,
        "no_submission": no_submission,
        "failed": failed,
        "total": len(student_links),
    }

    success(
        f"Download complete: {downloaded} new, {skipped} skipped, "
        f"{no_submission} empty, {failed} failed"
    )
    return summary


def _save_inline_submission(page: Page, student_dir: Path):
    """Save inline text submissions (e.g., text box answers) as submission.txt."""
    # Look for submission text in common containers
    selectors = [
        ".d2l-htmlblock-untrusted",
        ".d2l-htmlblock",
        ".d2l-textblock",
        "[class*='submission'] .d2l-htmlblock",
    ]

    for sel in selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            text = loc.first.inner_text().strip()
            if text and len(text) > 20:
                (student_dir / "submission.txt").write_text(text, encoding="utf-8")
                return

    raise ValueError("No downloadable or inline submission found")
