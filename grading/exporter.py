"""Export grading results to CSV"""

import csv
from pathlib import Path


def export_grades_csv(results: list[dict], rubric: dict, output_path: Path) -> Path:
    """
    Write grading results to a CSV file.

    Columns: username, raw_total, max_total, percentage, final_score, late,
             <criterion1_score>, <criterion1_level>, ..., feedback
    """
    criteria_names = [c["name"] for c in rubric.get("criteria", [])]

    fieldnames = [
        "username",
        "raw_total",
        "max_total",
        "percentage",
        "final_score",
        "late",
    ]

    # Add per-criterion columns
    for name in criteria_names:
        safe = name.replace(",", "").replace('"', "")[:30]
        fieldnames.append(f"{safe}_score")
        fieldnames.append(f"{safe}_level")

    fieldnames.append("feedback")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for r in results:
            row = {
                "username": r.get("username", ""),
                "raw_total": r.get("raw_total", ""),
                "max_total": r.get("max_total", ""),
                "percentage": r.get("percentage", ""),
                "final_score": r.get("final_score", r.get("percentage", "")),
                "late": r.get("late", ""),
                "feedback": r.get("feedback", "").replace("\n", " "),
            }

            # Per-criterion scores
            criteria_by_name = {c.get("name", ""): c for c in r.get("criteria", [])}
            for name in criteria_names:
                safe = name.replace(",", "").replace('"', "")[:30]
                c = criteria_by_name.get(name, {})
                row[f"{safe}_score"] = c.get("score", "")
                row[f"{safe}_level"] = c.get("level", "")

            writer.writerow(row)

    return output_path
