"""
Preprocess Submissions (Excel) -> JSON
Adapted from SimpleGradingAPP/StructuredCode/xlsx_submission_loader.py
"""
import json
from pathlib import Path
import openpyxl
from rich.console import Console

console = Console()

def clean_transcript(text):
    if not text:
        return ""
    return str(text).strip()

def load_from_excel(input_path: Path, output_path: Path) -> list:
    """
    Reads Brightspace Attempt Details Excel file and converts to JSON.
    Returns the list of student submission dictionaries.
    """
    if not input_path.exists():
        console.print(f"[red]Error: Input file {input_path} not found.[/red]")
        return []

    console.log(f"Reading {input_path}...")
    
    try:
        workbook = openpyxl.load_workbook(input_path)
        sheet = workbook.active
        
        # Get headers from first row
        headers = [cell.value for cell in sheet[1]]
        headers_map = {str(h).strip(): i for i, h in enumerate(headers) if h}
        
        # Verify critical columns exist
        required_cols = ["Q #", "Answer", "Username", "Org Defined ID"]
        for col in required_cols:
            if col not in headers_map:
                console.print(f"[yellow]Warning: Exact column '{col}' not found in headers: {list(headers_map.keys())}[/yellow]")
        
        col_q_num = headers_map.get("Q #")
        col_answer = headers_map.get("Answer")
        col_username = headers_map.get("Username")
        col_org_id = headers_map.get("Org Defined ID")
        col_first_name = headers_map.get("FirstName")
        col_last_name = headers_map.get("LastName")
        
        students = {}
        count_q2_found = 0
        
        for row_idx, row in enumerate(sheet.iter_rows(min_row=2), start=2):
            # Safe value extraction
            def get_col_val(idx):
                if idx is not None and 0 <= idx < len(row):
                    return row[idx].value
                return None

            q_num_raw = get_col_val(col_q_num)
            ans = get_col_val(col_answer)
            username = get_col_val(col_username)
            org_id = get_col_val(col_org_id)
            
            # Construct Student Name
            first = get_col_val(col_first_name) or ""
            last = get_col_val(col_last_name) or ""
            full_name = f"{first} {last}".strip()
            
            # Identify Student
            key = str(org_id) if org_id else str(username) if username else full_name
            if not key:
                # console.log(f"Skipping row {row_idx}: No identifier")
                continue

            if key not in students:
                students[key] = {
                    "student_name": full_name,
                    "org_defined_id": str(org_id) if org_id else "",
                    "username": str(username) if username else "",
                    "video_url": "",
                    "transcript": ""
                }
            
            # Check Question Number
            if q_num_raw is not None:
                try:
                    q_num = int(float(str(q_num_raw))) # Handle 2, 2.0, "2", "2.0"
                    
                    if q_num == 2:
                        # Q2 is usually the transcript/text answer
                        cleaned_ans = clean_transcript(ans)
                        if cleaned_ans:
                            students[key]["transcript"] = cleaned_ans
                            count_q2_found += 1
                            
                    elif q_num == 1:
                        # Q1 is usually the Video Link
                        if ans:
                            students[key]["video_url"] = str(ans).strip()
                            
                except ValueError:
                    pass
               
        # Collect results
        final_submissions = [s for s in students.values() if s["transcript"]]
        
        console.print(f"Total rows processed: {row_idx - 1}")
        console.print(f"Found {count_q2_found} rows with Q#2 answers.")
        console.print(f"Consolidated into {len(final_submissions)} unique student submissions with transcripts.")
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_submissions, f, indent=2, ensure_ascii=False)
            
        console.log(f"Saved processed submissions to {output_path}")
        return final_submissions

    except Exception as e:
        console.print(f"[red]Error processing Excel file: {e}[/red]")
        return []
