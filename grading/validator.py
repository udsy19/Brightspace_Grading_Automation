"""Score validation and outlier detection"""

import json
import statistics
from pathlib import Path

from ui import console, warning, info


def validate_grades(results: list[dict], rubric: dict) -> list[dict]:
    """
    Validate grading results. Returns list of flagged issues.

    Checks:
    - Scores within bounds (0 <= score <= max_points per criterion)
    - Total within 0-100%
    - No missing criteria
    """
    flags = []
    total_points = rubric.get("total_points", 100)
    criteria_names = {c["name"] for c in rubric.get("criteria", [])}

    for r in results:
        student = r.get("student_id", r.get("username", "?"))

        # Check total bounds
        pct = r.get("percentage", 0)
        if pct < 0 or pct > 100:
            flags.append({
                "student": student,
                "type": "out_of_bounds",
                "detail": f"Percentage {pct}% outside 0-100 range",
            })

        # Check each criterion
        for c in r.get("criteria", []):
            score = c.get("score", 0)
            max_pts = c.get("max_points", 0)
            if score < 0:
                flags.append({
                    "student": student,
                    "type": "negative_score",
                    "detail": f"{c.get('name', '?')}: score {score} < 0",
                })
            if max_pts > 0 and score > max_pts:
                flags.append({
                    "student": student,
                    "type": "over_max",
                    "detail": f"{c.get('name', '?')}: score {score} > max {max_pts}",
                })

        # Check missing criteria
        graded_names = {c.get("name") for c in r.get("criteria", [])}
        missing = criteria_names - graded_names
        if missing:
            flags.append({
                "student": student,
                "type": "missing_criteria",
                "detail": f"Missing: {', '.join(missing)}",
            })

    return flags


def flag_outliers(results: list[dict], threshold: float = 2.0) -> list[dict]:
    """
    Flag students whose scores are statistical outliers (z-score > threshold).
    """
    if len(results) < 3:
        return []

    scores = [r.get("percentage", 0) for r in results]
    mean = statistics.mean(scores)
    stdev = statistics.stdev(scores) if len(scores) > 1 else 0

    if stdev == 0:
        return []

    flags = []
    for r in results:
        student = r.get("student_id", r.get("username", "?"))
        pct = r.get("percentage", 0)
        z = abs(pct - mean) / stdev
        if z > threshold:
            direction = "high" if pct > mean else "low"
            flags.append({
                "student": student,
                "type": f"outlier_{direction}",
                "detail": f"{pct:.1f}% (z={z:.1f}, mean={mean:.1f}, stdev={stdev:.1f})",
            })

    return flags


def save_flags(flags: list[dict], path: Path):
    """Save flags to a JSON file for review."""
    if flags:
        path.write_text(json.dumps(flags, indent=2))
        warning(f"{len(flags)} flags saved to {path.name}")
    else:
        info("No validation flags")
