"""
Rubric and Assignment Context Parser
Ported from SimpleGradingAPP/StructuredCode/assignment_context_parser.py
"""
import re
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

@dataclass
class GradingCriterion:
    """Individual grading criterion with evaluation details"""
    criterion_id: str
    description: str
    evaluation_points: List[str]
    weight_within_category: Optional[float] = None

    def to_dict(self) -> Dict:
        return asdict(self)

@dataclass
class GradingCategory:
    """Top-level grading category with weight and sub-criteria"""
    category_id: str
    category_name: str
    weight: float
    description: str
    criteria: List[GradingCriterion]
    competency_level: str  # e.g., "CORE COMPETENCY", "EXECUTION QUALITY"

    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            'criteria': [c.to_dict() for c in self.criteria]
        }

@dataclass
class RubricLevel:
    """Rubric performance level definition"""
    level_name: str  # e.g., "excellent", "good", "satisfactory"
    score_range: str  # e.g., "95-100", "88-94"
    description: str

    def to_dict(self) -> Dict:
        return asdict(self)

@dataclass
class AssignmentContext:
    """Complete assignment context for student understanding"""
    session_number: int
    assignment_title: str
    scenario: str
    requirements: List[str]
    deliverables: List[str]
    approach_framework: str  # e.g., "DRIVER"
    execution_format: str
    constraints: Optional[List[str]] = None

    def to_dict(self) -> Dict:
        return asdict(self)

@dataclass
class GradingContext:
    """Complete grading context for LLM evaluation"""
    assignment_id: str
    grading_focus: str
    categories: List[GradingCategory]
    rubric_levels: List[RubricLevel]
    total_points: int = 100

    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            'categories': [c.to_dict() for c in self.categories],
            'rubric_levels': [r.to_dict() for r in self.rubric_levels]
        }
        
    def validate_weights(self) -> bool:
        """Verify that category weights sum to 1.0"""
        total = sum(cat.weight for cat in self.categories)
        return abs(total - 1.0) < 0.01

class AssignmentContextParser:
    """
    Parser for extracting and structuring assignment information from Markdown.
    """

    def __init__(self, textbook_path: str):
        self.textbook_path = textbook_path
        with open(textbook_path, 'r', encoding='utf-8') as f:
            self.content = f.read()

        # Extract session number from filename
        self.session_number = self._extract_session_number()

    def _extract_session_number(self) -> int:
        match = re.search(r'session(\d+)', self.textbook_path)
        return int(match.group(1)) if match else 0

    def parse(self) -> tuple[AssignmentContext, GradingContext]:
        assignment_ctx = self._extract_assignment_context()
        grading_ctx = self._extract_grading_context()
        return assignment_ctx, grading_ctx

    def _extract_assignment_context(self) -> AssignmentContext:
        # Find assignment section
        assignment_match = re.search(
            r'## Section \d+: Assignment - (.+?)$',
            self.content,
            re.MULTILINE
        )
        assignment_title = assignment_match.group(1).strip() if assignment_match else "Unknown"

        scenario = self._extract_section_content(r'### Your Mission and Situation', r'###')
        requirements = self._extract_list_items(r'### Requirements', r'Demonstrate the following')
        if not requirements:
            requirements = self._extract_list_items(r'\*\*Minimum Questions to explore:\*\*', r'###')

        deliverables = self._extract_list_items(r'### What You.?ll Create', r'###')
        
        execution = self._extract_section_content(r'### Video Guidelines', r'###')
        if not execution:
            execution = self._extract_section_content(r'### Execution Format', r'###')

        return AssignmentContext(
            session_number=self.session_number,
            assignment_title=assignment_title,
            scenario=scenario or "See assignment description",
            requirements=requirements or ["See assignment details"],
            deliverables=deliverables or ["Video presentation", "Code file"],
            approach_framework="DRIVER",
            execution_format=execution or "Record video explaining your work"
        )

    def _extract_grading_context(self) -> GradingContext:
        # Find grading criteria section
        grading_section = None
        for heading in [
            r'### SUGGESTED GRADING CRITERIA', r'### Assessment', r'### ASSESSMENT', r'### Grading', r'### GRADING CRITERIA'
        ]:
            grading_section = re.search(rf'{heading}.*?(?=## Section|\Z)', self.content, re.DOTALL | re.IGNORECASE)
            if grading_section:
                break

        if not grading_section:
            # Fallback: Treat whole file as rubric if small
            if len(self.content) < 5000:
                 grading_text = self.content
            else:
                 raise ValueError("No grading criteria section found")
        else:
            grading_text = grading_section.group(0)

        categories = self._parse_grading_categories(grading_text)
        rubric_levels = self._parse_rubric_levels(grading_text)

        focus_match = re.search(r'grading_focus[:\s]+["\'](.+?)["\']', self.content)
        grading_focus = focus_match.group(1) if focus_match else f"Session {self.session_number} Assignment"

        return GradingContext(
            assignment_id=f"session{self.session_number:02d}",
            grading_focus=grading_focus,
            categories=categories,
            rubric_levels=rubric_levels
        )

    def _parse_grading_categories(self, grading_text: str) -> List[GradingCategory]:
        categories = []
        # Pattern: "1. **Category Name (Weight%)**"
        category_pattern = r'\d+\.\s+\*\*(.+?)\s*\((\d+)%\)\*\*\s*\n\s+\*\*(.+?)\*\*\s*\n(.*?)(?=\d+\.\s+\*\*|\Z)'
        matches = list(re.finditer(category_pattern, grading_text, re.DOTALL))

        if matches:
            for match in matches:
                category_name = match.group(1).strip()
                weight = int(match.group(2)) / 100.0
                competency_level = match.group(3).strip()
                criteria_text = match.group(4)

                category_id = re.sub(r'[^a-z0-9]+', '_', category_name.lower())
                criteria = self._parse_criteria_items(criteria_text)
                desc_match = re.search(r'-\s*(.+?)(?:\n|$)', criteria_text)
                description = desc_match.group(1).strip() if desc_match else competency_level

                categories.append(GradingCategory(
                    category_id=category_id,
                    category_name=category_name,
                    weight=weight,
                    description=description,
                    criteria=criteria,
                    competency_level=competency_level
                ))
            return categories

        # Fallback pattern: "#### 1. Category Name (50 points)"
        heading_pattern = r'####\s*\d+\.\s*(.+?)\s*\((\d+)\s*(?:points|%)\)\s*(.*?)(?=####\s*\d+\.|\Z)'
        heading_matches = re.finditer(heading_pattern, grading_text, re.DOTALL | re.IGNORECASE)

        for match in heading_matches:
            category_name = match.group(1).strip()
            weight_value = int(match.group(2))
            weight = weight_value / 100.0
            criteria_text = match.group(3)

            category_id = re.sub(r'[^a-z0-9]+', '_', category_name.lower())
            criteria = self._parse_criteria_items(criteria_text)
            desc_match = re.search(r'-\s*(.+?)(?:\n|$)', criteria_text)
            description = desc_match.group(1).strip() if desc_match else category_name

            categories.append(GradingCategory(
                category_id=category_id,
                category_name=category_name,
                weight=weight,
                description=description,
                criteria=criteria,
                competency_level=category_name
            ))
        return categories

    def _parse_criteria_items(self, criteria_text: str) -> List[GradingCriterion]:
        criteria = []
        bullet_pattern = r'-\s+(.+?)(?=\n\s*-|\Z)'
        matches = re.finditer(bullet_pattern, criteria_text, re.DOTALL)

        for i, match in enumerate(matches, 1):
            criterion_text = match.group(1).strip()
            if criterion_text.startswith('###') or criterion_text.startswith('**###'):
                continue
            if len(criterion_text) < 10:
                continue

            if '\n' in criterion_text:
                lines = [line.strip() for line in criterion_text.split('\n') if line.strip()]
                description = lines[0]
                evaluation_points = lines[1:]
            else:
                description = criterion_text
                evaluation_points = []
            
            description = description.replace('**', '').strip()
            criterion_id = f"criterion_{i}"

            criteria.append(GradingCriterion(
                criterion_id=criterion_id,
                description=description,
                evaluation_points=evaluation_points
            ))
        return criteria

    def _parse_rubric_levels(self, grading_text: str) -> List[RubricLevel]:
        levels = []
        level_pattern = r'(\w+):\s*["\'](.+?)\s*\(([^)]+)\)["\']'
        matches = re.finditer(level_pattern, grading_text, re.IGNORECASE)

        for match in matches:
            level_name = match.group(1).lower()
            description = match.group(2).strip()
            score_range = match.group(3).strip()

            levels.append(RubricLevel(
                level_name=level_name,
                score_range=score_range,
                description=description
            ))

        if not levels:
            levels = [
                RubricLevel("excellent", "95-100", "Outstanding demonstration with insightful analysis"),
                RubricLevel("good", "88-94", "Strong understanding with minor gaps"),
                RubricLevel("satisfactory", "82-87", "Meets core requirements"),
                RubricLevel("needs_improvement", "<82", "Significant gaps in understanding or execution")
            ]
        return levels

    def _extract_section_content(self, start_pattern: str, end_pattern: str) -> str:
        pattern = f'{start_pattern}(.*?)(?={end_pattern}|\\Z)'
        match = re.search(pattern, self.content, re.DOTALL)
        if match:
            content = match.group(1).strip()
            content = re.sub(r'\*\*(.+?)\*\*', r'\1', content)
            return content
        return ""

    def _extract_list_items(self, section_pattern: str, end_pattern: str) -> List[str]:
        section = self._extract_section_content(section_pattern, end_pattern)
        if not section:
            return []
        items = re.findall(r'(?:^|\n)\s*[-*\d.]+\s+(.+?)(?=\n\s*[-*\d.]|\n\n|\Z)', section, re.DOTALL)
        return [item.strip() for item in items if item.strip()]
