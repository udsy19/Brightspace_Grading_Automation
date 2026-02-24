"""
AI grading using Anthropic Claude — prompt caching + tool use

- System prompt (rubric + reference + instructions) is cached after the first student
- Tool use forces structured output — no regex parsing, no format errors
- Each student is one API call with just their submission as the user message
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from anthropic import Anthropic

from config import get_anthropic_key


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CriterionResult:
    name: str
    max_points: float
    score: float
    level: str             # FAIL / PARTIAL / PASS
    evidence: list[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class GradeResult:
    student_id: str
    raw_total: float
    max_total: float
    percentage: float
    criteria: list[CriterionResult] = field(default_factory=list)
    feedback: str = ""
    graded_at: str = ""
    model_used: str = ""
    cached: bool = False

    # Audit
    full_response: str = ""


# ---------------------------------------------------------------------------
# Tool definitions — Claude MUST call these, guaranteeing structured output
# ---------------------------------------------------------------------------

GRADING_TOOLS = [
    {
        "name": "grade_criterion",
        "description": (
            "Submit your evaluation for one rubric criterion. "
            "Call this once for EACH criterion in the rubric."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "criterion_name": {
                    "type": "string",
                    "description": "Exact name of the criterion from the rubric",
                },
                "score": {
                    "type": "number",
                    "description": "Points awarded (0 to max_points for this criterion)",
                },
                "max_points": {
                    "type": "number",
                    "description": "Maximum possible points for this criterion",
                },
                "level": {
                    "type": "string",
                    "enum": ["PASS", "PARTIAL", "FAIL"],
                    "description": "PASS = full marks, PARTIAL = half, FAIL = zero",
                },
                "evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Direct quotes or specific observations from the submission",
                },
                "reasoning": {
                    "type": "string",
                    "description": "2-3 sentence explanation of why this score was given",
                },
            },
            "required": ["criterion_name", "score", "max_points", "level", "evidence", "reasoning"],
        },
    },
    {
        "name": "submit_final_grade",
        "description": (
            "Submit the overall grade and feedback AFTER grading all criteria. "
            "Call this exactly once, after all grade_criterion calls."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "total_score": {
                    "type": "number",
                    "description": "Sum of all criterion scores awarded",
                },
                "max_total": {
                    "type": "number",
                    "description": "Sum of all criterion max_points",
                },
                "percentage": {
                    "type": "number",
                    "description": "Percentage score (0-100)",
                },
                "feedback": {
                    "type": "string",
                    "description": "2-4 sentences of constructive feedback for the student",
                },
            },
            "required": ["total_score", "max_total", "percentage", "feedback"],
        },
    },
]


# ---------------------------------------------------------------------------
# Cached system prompt builder
# ---------------------------------------------------------------------------

def build_system_prompt(
    rubric: dict,
    reference_text: str = "",
    calibration_examples: list[dict] | None = None,
) -> list[dict]:
    """
    Build the system prompt with cache_control on the heavy content.

    The rubric + reference material block is marked for caching —
    Anthropic will cache it after the first call, so subsequent students
    only pay for the new submission text.
    """
    instructions = (
        "You are a precise, fair grading assistant. Your job is to evaluate student "
        "submissions against a rubric.\n\n"
        "PROCESS:\n"
        "1. Read the student's submission carefully\n"
        "2. For EACH criterion in the rubric, call the grade_criterion tool with your evaluation\n"
        "3. After ALL criteria are graded, call submit_final_grade with the totals and feedback\n\n"
        "SCORING RULES:\n"
        "- PASS: Full marks — clear, strong evidence of meeting the criterion\n"
        "- PARTIAL: Half marks — some evidence but gaps or incomplete\n"
        "- FAIL: Zero marks — no evidence, missing, or fundamentally wrong\n\n"
        "IMPORTANT:\n"
        "- Base scores ONLY on evidence in the submission, not assumptions\n"
        "- Be consistent — same quality of work should get the same score\n"
        "- Evidence must be specific quotes or observations, not vague\n"
        "- Feedback should be constructive and actionable\n"
        "- You MUST call grade_criterion for every criterion in the rubric\n"
        "- You MUST call submit_final_grade exactly once at the end"
    )

    # Format rubric
    criteria_text = ""
    for i, c in enumerate(rubric.get("criteria", []), 1):
        criteria_text += f"\n{i}. {c['name']} ({c.get('max_points', 10)} pts)"
        if c.get("description"):
            criteria_text += f"\n   {c['description']}"
        criteria_text += "\n"

    rubric_block = (
        f"RUBRIC\n"
        f"Total Points: {rubric.get('total_points', '?')}\n"
        f"\nCRITERIA:{criteria_text}"
    )

    # Format calibration examples if provided
    examples_block = ""
    if calibration_examples:
        examples_block = "\n\nCALIBRATION EXAMPLES (use these as scoring reference):\n"
        for ex in calibration_examples:
            examples_block += f"\n--- Example: {ex.get('student_id', '?')} ---\n"
            for c in ex.get("criteria", []):
                examples_block += (
                    f"  {c['name']}: {c['level']} ({c['score']}/{c['max_points']})\n"
                )
            examples_block += f"  Overall: {ex.get('percentage', '?')}%\n"

    # The heavy block (rubric + reference + examples) gets cached
    cached_content = rubric_block
    if reference_text:
        ref = reference_text[:200000]  # Safety limit
        cached_content += f"\n\nREFERENCE MATERIAL:\n{ref}"
    if examples_block:
        cached_content += examples_block

    return [
        {
            "type": "text",
            "text": instructions,
        },
        {
            "type": "text",
            "text": cached_content,
            "cache_control": {"type": "ephemeral"},
        },
    ]


# ---------------------------------------------------------------------------
# Grade one student
# ---------------------------------------------------------------------------

def grade_student(
    student_id: str,
    submission_text: str,
    system_prompt: list[dict],
    model: str = "claude-sonnet-4-5-20250929",
    client: Anthropic | None = None,
    audit_dir: Path | None = None,
) -> GradeResult:
    """
    Grade a single student. System prompt should be pre-built (and will be cached).

    Returns GradeResult with structured scores from tool calls.
    """
    if client is None:
        api_key = get_anthropic_key()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set in .env")
        client = Anthropic(api_key=api_key)

    # Truncate very long submissions
    submission = submission_text[:600000] if len(submission_text) > 600000 else submission_text

    user_message = f"Grade this student's submission:\n\nStudent ID: {student_id}\n\n{submission}"

    # API call with tool use
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        tools=GRADING_TOOLS,
        tool_choice={"type": "any"},  # Force tool use
        messages=[{"role": "user", "content": user_message}],
        temperature=0.1,
    )

    # Parse tool calls from response
    criterion_results = []
    final_grade = None

    for block in response.content:
        if block.type == "tool_use":
            if block.name == "grade_criterion":
                inp = block.input
                criterion_results.append(CriterionResult(
                    name=inp.get("criterion_name", "?"),
                    max_points=inp.get("max_points", 0),
                    score=min(inp.get("score", 0), inp.get("max_points", 0)),
                    level=inp.get("level", "FAIL"),
                    evidence=inp.get("evidence", []),
                    reasoning=inp.get("reasoning", ""),
                ))
            elif block.name == "submit_final_grade":
                final_grade = block.input

    # If Claude only returned one tool call, we need to continue the conversation
    # to get the remaining tool calls
    if not final_grade or len(criterion_results) == 0:
        # Build tool results and ask for more
        result = _continue_grading(client, model, system_prompt, user_message,
                                   response, criterion_results, final_grade)
        criterion_results = result[0]
        final_grade = result[1]

    # Compute totals (from tool calls or fallback to our sum)
    raw_total = final_grade.get("total_score", sum(c.score for c in criterion_results)) if final_grade else sum(c.score for c in criterion_results)
    max_total = final_grade.get("max_total", sum(c.max_points for c in criterion_results)) if final_grade else sum(c.max_points for c in criterion_results)
    percentage = final_grade.get("percentage", (raw_total / max_total * 100) if max_total > 0 else 0) if final_grade else ((raw_total / max_total * 100) if max_total > 0 else 0)
    feedback = final_grade.get("feedback", "") if final_grade else ""

    cached = getattr(response, "usage", None) and getattr(response.usage, "cache_read_input_tokens", 0) > 0

    result = GradeResult(
        student_id=student_id,
        raw_total=round(raw_total, 2),
        max_total=round(max_total, 2),
        percentage=round(percentage, 2),
        criteria=criterion_results,
        feedback=feedback,
        graded_at=datetime.now().isoformat(),
        model_used=model,
        cached=cached,
        full_response=json.dumps([
            {"type": b.type, **({"name": b.name, "input": b.input} if b.type == "tool_use" else {"text": b.text if hasattr(b, "text") else ""})}
            for b in response.content
        ], indent=2),
    )

    # Save audit trail
    if audit_dir:
        _save_audit(audit_dir, student_id, result, response)

    return result


def _continue_grading(client, model, system_prompt, user_message, prev_response,
                      criterion_results, final_grade, max_rounds=5):
    """
    Continue the conversation if Claude didn't finish all tool calls in one response.
    Sends tool_result messages back to get remaining grade_criterion / submit_final_grade calls.
    """
    messages = [{"role": "user", "content": user_message}]

    # Add the assistant's response
    messages.append({"role": "assistant", "content": prev_response.content})

    # Send tool results for what we got
    tool_results = []
    for block in prev_response.content:
        if block.type == "tool_use":
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": "Recorded. Continue grading the remaining criteria.",
            })

    if tool_results:
        messages.append({"role": "user", "content": tool_results})

    for _round in range(max_rounds):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            tools=GRADING_TOOLS,
            messages=messages,
            temperature=0.1,
        )

        new_tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                if block.name == "grade_criterion":
                    inp = block.input
                    criterion_results.append(CriterionResult(
                        name=inp.get("criterion_name", "?"),
                        max_points=inp.get("max_points", 0),
                        score=min(inp.get("score", 0), inp.get("max_points", 0)),
                        level=inp.get("level", "FAIL"),
                        evidence=inp.get("evidence", []),
                        reasoning=inp.get("reasoning", ""),
                    ))
                elif block.name == "submit_final_grade":
                    final_grade = block.input

                new_tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "Recorded.",
                })

        # If we got submit_final_grade, we're done
        if final_grade:
            break

        # If stop_reason is end_turn with no more tool calls, we're done
        if response.stop_reason == "end_turn" and not new_tool_results:
            break

        # Continue the conversation
        messages.append({"role": "assistant", "content": response.content})
        if new_tool_results:
            messages.append({"role": "user", "content": new_tool_results})

    return criterion_results, final_grade


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def _save_audit(audit_dir: Path, student_id: str, result: GradeResult, response):
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_file = audit_dir / f"{student_id}.json"

    usage = {}
    if hasattr(response, "usage"):
        u = response.usage
        usage = {
            "input_tokens": getattr(u, "input_tokens", 0),
            "output_tokens": getattr(u, "output_tokens", 0),
            "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0),
            "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0),
        }

    audit_data = {
        "student_id": student_id,
        "model": result.model_used,
        "graded_at": result.graded_at,
        "cached": result.cached,
        "usage": usage,
        "scores": {
            c.name: {"score": c.score, "max": c.max_points, "level": c.level}
            for c in result.criteria
        },
        "raw_total": result.raw_total,
        "max_total": result.max_total,
        "percentage": result.percentage,
        "feedback": result.feedback,
        "criteria_detail": [
            {
                "name": c.name,
                "score": c.score,
                "max_points": c.max_points,
                "level": c.level,
                "evidence": c.evidence,
                "reasoning": c.reasoning,
            }
            for c in result.criteria
        ],
        "raw_response": result.full_response,
    }
    audit_file.write_text(json.dumps(audit_data, indent=2, ensure_ascii=False))
