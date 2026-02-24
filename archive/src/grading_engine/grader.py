"""
DRIVER Per-Criterion Grader
Refactored for Anthropic Claude Agents
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
from anthropic import Anthropic
import re
import os
from .analyzer import DRIVERTranscriptAnalyzer, DRIVEREvidence

@dataclass
class CriterionResult:
    """Result for one criterion evaluation"""
    criterion_id: str
    criterion_name: str
    category_name: str
    category_weight: float

    # Evaluation
    score: float  # 0.0, 0.5, 1.0
    level: str    # "FAIL", "PARTIAL", "PASS"
    evidence: List[str] = field(default_factory=list)
    driver_alignment: str = ""
    reasoning: str = ""

    # Metadata
    response_id: str = ""
    timestamp: float = 0.0
    model_used: str = "claude-3-5-sonnet-latest"

@dataclass
class GradeReport:
    """Complete grading report for one student"""
    student_name: str
    overall_grade: float  # 0-100
    criterion_results: List[CriterionResult]
    driver_evidence: DRIVEREvidence
    feedback: str

    # Statistics
    total_criteria: int = 0
    passed_criteria: int = 0
    partial_criteria: int = 0
    failed_criteria: int = 0

    # DRIVER stage coverage
    driver_stages_demonstrated: Dict[str, bool] = field(default_factory=dict)

    # Metadata
    timestamp: str = ""
    grading_model: str = "claude-3-5-sonnet-latest"


class DRIVERPerCriterionGrader:
    """
    Grade student submissions using DRIVER framework lens (via Claude).
    """

    def __init__(
        self,
        assignment_context: Any,
        grading_context: Any,
        client: Optional[Anthropic] = None
    ):
        self.assignment = assignment_context
        self.grading = grading_context
        
        # Initialize client
        if client:
            self.client = client
        else:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            self.client = Anthropic(api_key=api_key)
            
        self.analyzer = DRIVERTranscriptAnalyzer(self.client)

    def grade_student(
        self,
        student_name: str,
        transcript: str
    ) -> GradeReport:
        # Preprocess - Extract DRIVER evidence
        driver_evidence = self.analyzer.analyze(transcript)

        # Evaluate each criterion
        criterion_results = []

        for category in self.grading.categories:
            for i, criterion in enumerate(category.criteria, 1):
                result = self.evaluate_criterion(
                    criterion=criterion,
                    transcript=transcript,
                    driver_evidence=driver_evidence,
                    category_context=category
                )
                criterion_results.append(result)

        # Aggregate scores
        overall_grade = self.aggregate(criterion_results)

        # Generate DRIVER-informed feedback
        feedback = self.generate_driver_feedback(
            criterion_results,
            driver_evidence
        )

        # Build report
        report = GradeReport(
            student_name=student_name,
            overall_grade=overall_grade,
            criterion_results=criterion_results,
            driver_evidence=driver_evidence,
            feedback=feedback,
            total_criteria=len(criterion_results),
            passed_criteria=sum(1 for r in criterion_results if r.level == "PASS"),
            partial_criteria=sum(1 for r in criterion_results if r.level == "PARTIAL"),
            failed_criteria=sum(1 for r in criterion_results if r.level == "FAIL"),
            driver_stages_demonstrated=driver_evidence.stage_coverage,
            timestamp=datetime.now().isoformat(),
            grading_model=criterion_results[0].model_used if criterion_results else "claude-3-5-sonnet-latest"
        )
        return report

    def evaluate_criterion(
        self,
        criterion: Any,
        transcript: str,
        driver_evidence: DRIVEREvidence,
        category_context: Any,
        model: str = "claude-3-5-sonnet-latest"
    ) -> CriterionResult:
        prompt = self._build_criterion_prompt(
            criterion=criterion,
            transcript=transcript,
            driver_evidence=driver_evidence,
            category=category_context
        )

        try:
            message = self.client.messages.create(
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model=model,
                temperature=0.2, # Slightly creative for reasoning
            )
            output_text = message.content[0].text
            response_id = message.id
            
        except Exception as exc:
            # Fallback for extreme length, though rare for Claude
            prompt = self._build_criterion_prompt(
                criterion=criterion,
                transcript=transcript,
                driver_evidence=driver_evidence,
                category=category_context,
                max_transcript_chars=100000, # Significantly reduce if error
            )
            message = self.client.messages.create(
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
                model=model,
            )
            output_text = message.content[0].text
            response_id = message.id

        return self._parse_criterion_result(
            output_text=output_text,
            criterion=criterion,
            category=category_context,
            model=model,
            response_id=response_id
        )

    def _build_criterion_prompt(
        self,
        criterion: Any,
        transcript: str,
        driver_evidence: DRIVEREvidence,
        category: Any,
        max_transcript_chars: int = 600000, # ~150k tokens safe buffer
    ) -> str:
        driver_quotes = self._get_relevant_driver_quotes(
            driver_evidence,
            category.category_name
        )
        
        criterion_desc = criterion.description.lower()
        is_driver_category = category.category_name == "Following the DRIVER Framework"

        is_validate_criterion = is_driver_category and "validate" in criterion_desc
        is_implement_criterion = is_driver_category and "implement" in criterion_desc

        if is_validate_criterion:
            strictness_level = "MODERATE (External validation through discussion acceptable)"
        elif is_implement_criterion:
            strictness_level = "MODERATE (Systematic methodology demonstration acceptable)"
        else:
            strictness_level = self._get_strictness_level(category.category_name)

        return f"""<evaluation_task>
You are evaluating ONE specific criterion for a student assignment using the DRIVER framework lens.

<context>
CATEGORY: {category.category_name} ({category.weight*100:.0f}% of grade)
COMPETENCY LEVEL: {category.competency_level}
EVALUATION STRICTNESS: {strictness_level}

CRITERION TO EVALUATE:
{criterion.description}

{self._format_evaluation_points(criterion)}
</context>

<driver_evidence>
The student demonstrated the following DRIVER stages in their submission:

{driver_quotes}
</driver_evidence>

<full_transcript>
{self._truncate_if_needed(transcript, max_chars=max_transcript_chars)}
</full_transcript>

<task>
Evaluate whether the student PASSES, PARTIALLY PASSES, or FAILS this criterion.

{self._get_criterion_specific_rubric(category.category_name, criterion.description)}

SCORING RUBRIC:
PASS (1.0): Fully demonstrates the criterion with clear evidence, strong understanding, specific evidence.
PARTIAL (0.5): Partially demonstrates with some evidence but gaps in methodology or completion.
FAIL (0.0): Does not demonstrate criterion, missing evidence, or significant confusion.

REQUIRED OUTPUT FORMAT (use exactly this structure):

SCORE: [FAIL/PARTIAL/PASS]

EVIDENCE:
- [Quote 1]
- [Quote 2]

DRIVER_ALIGNMENT:
[Explanation]

REASONING:
[2-3 sentences]
</task>
</evaluation_task>"""

    def _get_relevant_driver_quotes(self, evidence: DRIVEREvidence, category_name: str) -> str:
        stage_mapping = {
            "Understanding of Financial Concepts": ["discover", "implement", "validate", "reflect"],
            "Technical Implementation": ["represent", "implement", "validate"],
            "Integration of Finance and Technology": ["discover", "implement", "evolve"],
            "Following the DRIVER Framework": ["discover", "represent", "implement", "validate", "evolve", "reflect"],
            "Clear Communication": ["represent", "implement", "reflect"],
        }
        relevant_stages = stage_mapping.get(category_name, ["discover", "implement", "reflect"])
        quotes_by_stage = []
        for stage in relevant_stages:
            stage_quotes = evidence.get_stage_quotes(stage)
            if stage_quotes:
                quotes_by_stage.append(f"\n{stage.upper()} STAGE:")
                for quote in stage_quotes[:2]:
                    quotes_by_stage.append(f"- {quote}")
        return "\n".join(quotes_by_stage) if quotes_by_stage else "No explicit DRIVER evidence found."

    def _get_strictness_level(self, category_name: str) -> str:
        strict_categories = ["Following the DRIVER Framework"]
        if category_name in strict_categories:
            return "STRICT (Explicit demonstration required)"
        else:
            return "MODERATE (Conceptual understanding through discussion acceptable)"

    def _get_criterion_specific_rubric(self, category_name: str, criterion_desc: str) -> str:
        if category_name == "Following the DRIVER Framework" and "validate" in criterion_desc.lower():
            return "THIS IS A MODERATE EVALUATION FOR DRIVER VALIDATE - EXTERNAL VALIDATION ACCEPTABLE"
        elif category_name == "Following the DRIVER Framework" and "implement" in criterion_desc.lower():
            return "THIS IS A MODERATE EVALUATION FOR DRIVER IMPLEMENT - SYSTEMATIC METHODOLOGY ACCEPTABLE"
        elif category_name in ["Following the DRIVER Framework"]:
             return "THIS IS A STRICT EVALUATION CATEGORY FOR DRIVER STAGES - EXPLICIT STAGE DEMONSTRATION REQUIRED"
        else:
            return "THIS IS A MODERATE EVALUATION CATEGORY - CONCEPTUAL UNDERSTANDING ACCEPTABLE"

    def _format_evaluation_points(self, criterion: Any) -> str:
        if hasattr(criterion, "evaluation_points") and criterion.evaluation_points:
            points = "\n".join(f"- {point}" for point in criterion.evaluation_points)
            return f"\nEVALUATION POINTS:\n{points}"
        return ""

    def _truncate_if_needed(self, text: str, max_chars: int = 600000) -> str:
        if len(text) <= max_chars:
            return text
        keep_start = int(max_chars * 0.6)
        keep_end = int(max_chars * 0.3)
        return f"{text[:keep_start]}\n\n[... TRUNCATED ...]\n\n{text[-keep_end:]}"

    def _parse_criterion_result(
        self,
        output_text: str,
        criterion: Any,
        category: Any,
        model: str,
        response_id: str
    ) -> CriterionResult:
        score_match = re.search(r"SCORE:\s*(FAIL|PARTIAL|PASS)", output_text, re.IGNORECASE)
        level = score_match.group(1).upper() if score_match else "FAIL"
        score_map = {"FAIL": 0.0, "PARTIAL": 0.5, "PASS": 1.0}
        score = score_map.get(level, 0.0)
        
        evidence = self._extract_section_bullets(output_text, "EVIDENCE")
        driver_alignment = self._extract_section_text(output_text, "DRIVER_ALIGNMENT")
        reasoning = self._extract_section_text(output_text, "REASONING")

        return CriterionResult(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.description,
            category_name=category.category_name,
            category_weight=category.weight,
            score=score,
            level=level,
            evidence=evidence,
            driver_alignment=driver_alignment,
            reasoning=reasoning,
            response_id=response_id,
            timestamp=datetime.now().timestamp(),
            model_used=model
        )

    def _extract_section_bullets(self, text: str, section_name: str) -> List[str]:
        pattern = rf"{section_name}:\s*(.*?)(?=\n[A-Z_]+:|$)"
        match = re.search(pattern, text, re.DOTALL)
        if not match: return []
        section_text = match.group(1)
        bullets = []
        for line in section_text.split("\n"):
            line = line.strip()
            if line.startswith("-") or line.startswith("*"):
                bullets.append(line[1:].strip())
        return bullets

    def _extract_section_text(self, text: str, section_name: str) -> str:
        pattern = rf"{section_name}:\s*(.*?)(?=\n[A-Z_]+:|$)"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else ""

    def aggregate(self, criterion_results: List[CriterionResult]) -> float:
        by_category: Dict[str, List[CriterionResult]] = {}
        for result in criterion_results:
            if result.category_name not in by_category:
                by_category[result.category_name] = []
            by_category[result.category_name].append(result)

        total_weighted_score = 0.0
        for category_name, results in by_category.items():
            category_avg = sum(r.score for r in results) / len(results)
            category_weight = results[0].category_weight
            total_weighted_score += category_weight * category_avg
        return total_weighted_score * 100

    def generate_driver_feedback(
        self,
        criterion_results: List[CriterionResult],
        driver_evidence: DRIVEREvidence
    ) -> str:
        feedback_parts = []
        stages_found = [k for k, v in driver_evidence.stage_coverage.items() if v]
        
        if len(stages_found) >= 5:
            feedback_parts.append(f"Excellent DRIVER application. Demonstrated: {', '.join(stages_found)}.")
        elif len(stages_found) >= 3:
            feedback_parts.append(f"Good DRIVER application. Demonstrated: {', '.join(stages_found)}.")
        else:
            missing = set(["D", "R", "I", "V", "E", "R2"]) - set(stages_found)
            feedback_parts.append(f"Limited DRIVER demonstration. Focus on: {', '.join(missing)}.")

        strengths = [r for r in criterion_results if r.level == "PASS"]
        if strengths:
            feedback_parts.append("\n\nSTRENGTHS:")
            for result in strengths[:3]:
                feedback_parts.append(f"- {result.category_name}: {result.reasoning}")

        improvements = [r for r in criterion_results if r.level != "PASS"]
        if improvements:
            feedback_parts.append("\n\nAREAS FOR IMPROVEMENT:")
            for result in improvements[:3]:
                feedback_parts.append(f"- {result.category_name}: {result.reasoning}")

        return "\n".join(feedback_parts)
