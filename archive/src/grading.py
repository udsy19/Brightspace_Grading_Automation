from rich.console import Console
from rich.prompt import Prompt, Confirm
from pathlib import Path
import json
import os
from grading_engine.rubric import AssignmentContextParser
from grading_engine.loader import load_from_excel
from grading_engine.grader import DRIVERPerCriterionGrader

console = Console()

def process_grading_workflow(default_submissions_path=None):
    """
    Main workflow for the grading engine.
    1. Prompts for Context (Rubric)
    2. Prompts for Submissions (Excel) - uses download path as default if provided
    3. Loads and Parses data
    4. Runs Parallel Grading
    5. Saves Results
    """
    console.rule("[bold green]Grading Engine[/bold green]")
    
    if not Confirm.ask("Do you want to proceed with AI Grading?"):
        return None

    # 1. Rubric Selection
    rubric_path = Prompt.ask(
        "Enter path to Rubric/Textbook Markdown file", 
        default="Textbook/session08_market_efficiency.md"
    )
    if not os.path.exists(rubric_path):
        console.print(f"[red]Rubric file not found: {rubric_path}[/red]")
        return None

    console.log("Parsing rubric...")
    try:
        parser = AssignmentContextParser(rubric_path)
        assignment_ctx, grading_ctx = parser.parse()
        console.print(f"[green]Parsed Rubric:[/green] {len(grading_ctx.categories)} Categories, {sum(len(c.criteria) for c in grading_ctx.categories)} Criteria")
    except Exception as e:
        console.print(f"[red]Failed to parse rubric: {e}[/red]")
        return None

    # 2. Submissions Selection
    submissions_path = Prompt.ask(
        "Enter path to Submissions Excel file",
        default=str(default_submissions_path) if default_submissions_path else "Submission/MiniProject3-AttemptDetails.xlsx"
    )
    if not os.path.exists(submissions_path):
        console.print(f"[red]Submissions file not found: {submissions_path}[/red]")
        return None

    console.log("Loading submissions...")
    try:
        # We need a temp output path for the JSON conversion
        temp_json_path = Path("temp_submissions.json")
        submissions = load_from_excel(Path(submissions_path), temp_json_path)
        if not submissions:
            console.print("[red]No valid submissions found (check for Q#2 transcripts).[/red]")
            return None
    except Exception as e:
        console.print(f"[red]Failed to load submissions: {e}[/red]")
        return None

    # 3. Grading Execution
    count = int(Prompt.ask("How many students to grade? (0 for all)", default="3"))
    if count == 0: count = len(submissions)
    
    students_to_grade = submissions[:count]
    console.print(f"[bold]Starting grading for {len(students_to_grade)} students...[/bold]")

    grader = DRIVERPerCriterionGrader(assignment_ctx, grading_ctx)
    results = []
    
    output_dir = Path("results") / f"session_{assignment_ctx.session_number}"
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, student in enumerate(students_to_grade, 1):
        console.rule(f"Grading Student {i}/{len(students_to_grade)}: {student['student_name']}")
        
        try:
            report = grader.grade_student(
                student_name=student["student_name"],
                transcript=student["transcript"]
            )
            
            # Save individual result
            safe_name = "".join(x for x in student['student_name'] if x.isalnum() or x in " _-").strip()
            report_path = output_dir / f"{safe_name}.json"
            
            # Convert dataclass to dict for JSON serialization
            from dataclasses import asdict
            report_dict = asdict(report)
            
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report_dict, f, indent=2, ensure_ascii=False)
                
            console.print(f"[green]Grade: {report.overall_grade:.2f}/100 - Saved to {report_path}[/green]")
            results.append(report_dict)
            
        except Exception as e:
            console.print(f"[red]Error grading {student['student_name']}: {e}[/red]")

    console.rule("[bold green]Grading Complete[/bold green]")
    console.print(f"Results saved to: [link]{output_dir}[/link]")
    
    return results
