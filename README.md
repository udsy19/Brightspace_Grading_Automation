# Brightspace Grading Automation

An end-to-end grading automation system for Purdue Brightspace. Authenticates via Playwright, downloads student submissions (assignments and quizzes), grades them using Claude AI with structured tool use and prompt caching, validates results, and uploads scores back to Brightspace.

Built with FERPA compliance in mind: student identities are anonymized before any data is sent to the AI model.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Setup](#setup)
- [Usage](#usage)
- [How It Works](#how-it-works)
  - [Authentication](#authentication)
  - [Course & Assignment Discovery](#course--assignment-discovery)
  - [Downloading Submissions](#downloading-submissions)
  - [Grading Pipeline](#grading-pipeline)
  - [Grade Upload](#grade-upload)
- [Directory Structure](#directory-structure)
- [Configuration](#configuration)
- [FERPA & Privacy](#ferpa--privacy)

---

## Features

- **Browser Automation** -- Playwright-based login with Duo 2FA support and persistent session reuse
- **Assignment & Quiz Support** -- Scrapes Brightspace tables to discover assignments and quizzes, downloads files and inline text submissions
- **AI Grading with Claude** -- Uses Anthropic's Claude API with structured tool use (no regex parsing) to grade against a user-provided rubric
- **Prompt Caching** -- Rubric and reference material are cached across students in a batch, reducing cost by ~50-70%
- **Calibration Phase** -- Grades 3 diverse samples first for instructor review before batch grading
- **FERPA-Safe Anonymization** -- Student names are replaced with random UUIDs; PII is stripped from submissions before sending to Claude
- **Validation & Outlier Detection** -- Checks score bounds, flags statistical outliers (z-score > 2.0)
- **Crash Recovery** -- Saves state after each student; interrupted runs resume where they left off
- **Grade Upload** -- Navigates each student's evaluation page in Brightspace and fills in score + feedback
- **Rich TUI** -- Interactive terminal UI with menus, progress bars, and color-coded output

---

## Architecture

```
main.py                          Entry point & interactive menu
ui.py                            Rich-based TUI (menus, progress, output)
config.py                        Environment variables & path management
logger.py                        Loguru rotating file logger

brightspace/                     Browser automation layer
  browser.py                     Playwright lifecycle & session persistence
  auth.py                        Purdue SSO login + Duo 2FA handling
  courses.py                     Course discovery via Brightspace REST API
  assignments.py                 Assignment listing & student link extraction
  quizzes.py                     Quiz listing & attempt content scraping
  downloader.py                  Submission file/text downloads
  uploader.py                    Grade upload (assignments & quizzes)
  models.py                      Pydantic data models

grading/                         AI grading engine
  runner.py                      Orchestration: calibration, batching, export
  grader.py                      Claude API integration with tool use
  anonymizer.py                  FERPA anonymization & PII stripping
  validator.py                   Score validation & outlier flagging
  exporter.py                    CSV export for upload
```

---

## Setup

### Prerequisites

- Python 3.10+
- A Purdue Brightspace instructor account
- An Anthropic API key

### Installation

```bash
git clone https://github.com/udsy19/Brightspace_Grading_Automation.git
cd Brightspace_Grading_Automation

python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
playwright install chromium
```

### Environment

Copy the example and fill in your credentials:

```bash
cp .env.example .env
```

```env
PURDUE_USERNAME=your_username
PURDUE_PASSWORD=your_password
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Usage

```bash
python main.py
```

The interactive menu walks you through:

1. **Connect** -- Launches browser, restores session or logs in with Duo 2FA
2. **Select Course** -- Lists your enrolled courses
3. **Select Type** -- Assignments or Quizzes
4. **Select Item** -- Shows submission counts and due dates
5. **Actions**:
   - `[d]ownload` -- Fetch all student submissions locally
   - `[g]rade` -- Run the AI grading pipeline (requires a rubric)
   - `[u]pload` -- Push grades back to Brightspace
   - `[v]iew` -- Display score statistics and distribution

### Rubric Setup

Before grading, place a `rubric.json` in the assignment's `assignment/` folder:

```json
{
  "total_points": 100,
  "criteria": [
    {
      "name": "Content Quality",
      "description": "Depth of analysis and use of evidence",
      "max_points": 40
    },
    {
      "name": "Critical Thinking",
      "description": "Originality and logical reasoning",
      "max_points": 35
    },
    {
      "name": "Writing Quality",
      "description": "Grammar, structure, and clarity",
      "max_points": 25
    }
  ]
}
```

You can optionally add reference material (`instructions.md`, `example_solution.txt`) to the same folder -- these are included in the AI prompt.

---

## How It Works

### Authentication

1. **Session Restore** -- On launch, the browser checks for a saved session file at `.sessions/auth_session_<username>.json`. If valid cookies exist, login is skipped entirely.
2. **Purdue SSO** -- If no valid session, Playwright navigates to the Brightspace login page, selects "Purdue West Lafayette", and submits the username/password from `.env`.
3. **Duo 2FA** -- The system clicks through to the Duo Push option, extracts the 3-digit verification code via regex, and displays it in the terminal. The user approves the push on their phone.
4. **Session Save** -- After successful auth, `page.context.storage_state()` captures all cookies and localStorage to disk for reuse.

### Course & Assignment Discovery

**Courses** are fetched via the Brightspace REST API (`/d2l/api/lp/1.40/enrollments/myenrollments/`) with pagination support. Only Course Offering types are returned.

**Assignments** are discovered by navigating to the dropbox page and scraping the `.d2l-table` DOM. Each row yields the assignment name, due date, submission count, and a link to the student submission list. The page size is set to 200 to capture all students in one load.

**Quizzes** follow a similar pattern via the Manage Quizzes page. The quiz ID (`qi` parameter) is extracted from each link. Student attempts are found on the grading page, where JavaScript-routed links are parsed to get each attempt URL.

### Downloading Submissions

For each student in the submission list:

1. Navigate to their submission page
2. If files are attached, click "Download All Files" to save a zip
3. If the submission is inline text, extract it and save as `submission.txt`
4. Write a `metadata.json` with timestamp and submission info
5. Already-downloaded students are skipped (resume support)

For quizzes, the system navigates to each attempt page and scrapes all `.d2l-htmlblock` / `.d2l-textblock` elements to capture the student's written responses.

### Grading Pipeline

The grading engine (`grading/runner.py`) orchestrates a multi-phase pipeline:

#### Phase 1: Calibration

If the batch has more than 3 students, the system selects 3 diverse samples (short, medium, and long submissions) and grades them first. Results are displayed in a table with per-criterion scores and feedback. The instructor can:

- **Accept** -- The calibration examples become part of the system prompt for consistency
- **Cancel** -- Abort grading
- **Re-grade** -- Try again with different parameters

#### Phase 2: Prompt Construction

The system prompt is built in two blocks:

| Block | Content | Cached |
|-------|---------|--------|
| Instructions | Scoring rules, process overview, tool usage requirements | No |
| Content | Rubric JSON, reference material, calibration examples | Yes (`cache_control: ephemeral`) |

The content block is marked for Anthropic's prompt caching. After the first student is graded, all subsequent students reuse the cached prompt, saving tokens and cost.

#### Phase 3: Per-Student Grading

For each student:

1. **Anonymize** -- Map real name to a random UUID (`student_a1b2c3d4`). Strip emails, student IDs, and name declarations from the submission text.
2. **Truncate** -- Cap submission at 600KB to stay within API limits.
3. **API Call** -- Send to Claude with `tool_choice: {"type": "any"}` and `temperature: 0.1`:
   - Claude calls `grade_criterion` once per rubric criterion, providing: score, level (PASS/PARTIAL/FAIL), evidence (direct quotes), and reasoning
   - Claude calls `submit_final_grade` with the total score and written feedback
4. **Multi-turn handling** -- If Claude doesn't finish in one response, tool results are sent back to continue the conversation (up to 5 rounds).
5. **Save** -- Individual result JSON and audit trail are written to disk.
6. **State checkpoint** -- `run-state.json` is updated so the run can resume if interrupted.

#### Phase 4: Validation & Export

- **Bounds check** -- Every score must be within `[0, max_points]`
- **Outlier detection** -- Students with z-scores > 2.0 are flagged as unusually high or low
- **Late policy** -- If a deadline is configured, late submissions can be zeroed out based on `metadata.json` timestamps
- **CSV export** -- `grades.csv` is written with columns: `username, raw_total, max_total, percentage, final_score, late, <criterion>_score, <criterion>_level, ..., feedback`

### Grade Upload

The uploader reads `grades.csv` and navigates Brightspace to post each grade:

**For assignments:**
- Open the student's "Evaluate" page
- Fill the score input and feedback textarea
- Click Save, navigate back, repeat

**For quizzes:**
- Match CSV rows to attempt links by username
- Navigate to each attempt's grading page
- Fill "Attempt Grade" and feedback (handles iframe-based rich text editors)
- Click Update

---

## Directory Structure

After downloading and grading, the local file tree looks like:

```
classes/
  <Course-Name>/
    class.json                       # Course metadata
    <Assignment-Name>/
      config.json                    # Model, deadline, late policy
      assignment/
        rubric.json                  # User-provided rubric (required)
        instructions.md              # Optional reference material
      submissions/
        <Student-1>/
          submission.txt             # Or .zip for file uploads
          metadata.json              # Timestamp, submission info
        <Student-2>/
          ...
      grading/
        grades.csv                   # Final grades for upload
        flags.json                   # Validation warnings & outliers
        anon_mapping.json            # UUID-to-name mapping (local only)
        run-state.json               # Crash recovery checkpoint
        audit/
          student_a1b2c3d4.json      # Per-student audit trail
```

---

## Configuration

### Assignment Config (`config.json`)

```json
{
  "name": "Session 4 Assignment",
  "created_at": "2026-02-12T00:17:12.779684",
  "deadline": "2026-02-15T23:59:00",
  "late_policy": "zero",
  "grading_model": "claude-sonnet-4-5-20250929"
}
```

| Field | Description |
|-------|-------------|
| `deadline` | ISO timestamp. If set, submissions after this time are flagged as late. |
| `late_policy` | `"zero"` sets late submissions to 0. `null` applies no penalty. |
| `grading_model` | Anthropic model ID used for grading. |

---

## FERPA & Privacy

This system is designed with student privacy in mind:

- **Anonymization** -- Real student names are never sent to Claude. Each student is assigned a random UUID for the grading session.
- **PII Stripping** -- Email addresses, student IDs, and name declarations are redacted from submission text before it reaches the API.
- **Local-Only Mappings** -- The `anon_mapping.json` file that maps UUIDs back to real names is stored locally and excluded from version control.
- **Audit Trail** -- Every grading decision is logged with the anonymized ID, the evidence Claude cited, and the reasoning provided. This supports compliance review without exposing student data.
- **Gitignore Templates** -- Class directories are initialized with a `.gitignore` that excludes submissions, audit logs, and session data.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `playwright` | Browser automation for Brightspace navigation |
| `anthropic` | Claude API client for AI grading |
| `rich` | Terminal UI (menus, progress bars, tables) |
| `python-dotenv` | Load credentials from `.env` |
| `pandas` | CSV/statistics handling |
| `openpyxl` | Excel export support (via pandas) |
| `tiktoken` | Token counting for prompt size management |
