from pydantic import BaseModel
from typing import Optional


class BrightspaceCourse(BaseModel):
    name: str
    href: str

class BrightspaceAssignment(BaseModel):
    name: str
    href: str
    completed: str = "-"
    due_date: str = ""
    is_group: bool = False

class BrightspaceQuiz(BaseModel):
    name: str
    href: str
    qi: str
    completed: str = "-"
