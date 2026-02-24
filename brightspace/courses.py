"""Course discovery — ported directly from src/courses.py"""

from playwright.sync_api import Page
from rich.table import Table
from tenacity import retry, wait_exponential, stop_after_attempt
from brightspace.models import BrightspaceCourse
from logger import logger

from config import BRIGHTSPACE_URL
from ui import console, info, warning, pick


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def get_courses(page: Page) -> list[BrightspaceCourse]:
    """
    Extracts course information from the Brightspace API.
    Returns a list of BrightspaceCourse Pydantic models.
    """
    console.log("[bold blue]Fetching courses from Brightspace API...[/bold blue]")

    # Fetch all enrollments via API to ensure we get past semesters too.
    api_items = page.evaluate("""async () => {
        let allItems = [];
        let url = '/d2l/api/lp/1.40/enrollments/myenrollments/';
        while (url) {
            const res = await fetch(url);
            if (!res.ok) break;
            const data = await res.json();
            if (data.Items) {
                allItems = allItems.concat(data.Items);
            }
            if (data.PagingInfo && data.PagingInfo.HasMoreItems && data.PagingInfo.Bookmark) {
                url = `/d2l/api/lp/1.40/enrollments/myenrollments/?bookmark=${data.PagingInfo.Bookmark}`;
            } else {
                url = null;
            }
        }
        return allItems;
    }""")

    courses = []
    if api_items:
        for item in api_items:
            org = item.get("OrgUnit", {})
            name = org.get("Name")
            org_id = org.get("Id")
            type_id = org.get("Type", {}).get("Id")
            
            # Type 3 is typically "Course Offering"
            if name and org_id and type_id == 3:
                try:
                    courses.append(BrightspaceCourse(
                        name=name, 
                        href=f"/d2l/home/{org_id}"
                    ))
                except Exception as e:
                    logger.error(f"Failed to parse BrightspaceCourse: {e} - Data: {item}")

    if not courses:
        logger.warning("No courses found via API.")
        console.print("[bold red]Debug: No courses found via API.[/bold red]")

    return courses



