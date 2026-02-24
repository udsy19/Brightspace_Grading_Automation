"""
DRIVER Transcript Analyzer
Refactored for Anthropic Claude Agents
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from anthropic import Anthropic, APIError
import re
import os

@dataclass
class DRIVEREvidence:
    """Evidence of DRIVER stages found in transcript"""

    # Stage 1: Discover & Design
    problem_definition_quotes: List[str] = field(default_factory=list)
    goal_setting_quotes: List[str] = field(default_factory=list)
    requirement_understanding_quotes: List[str] = field(default_factory=list)

    # Stage 2: Represent
    planning_quotes: List[str] = field(default_factory=list)
    visualization_quotes: List[str] = field(default_factory=list)
    structure_quotes: List[str] = field(default_factory=list)

    # Stage 3: Implement
    execution_quotes: List[str] = field(default_factory=list)
    code_demonstration_quotes: List[str] = field(default_factory=list)
    problem_solving_quotes: List[str] = field(default_factory=list)

    # Stage 4: Validate
    verification_quotes: List[str] = field(default_factory=list)
    external_validation_quotes: List[str] = field(default_factory=list)
    accuracy_check_quotes: List[str] = field(default_factory=list)

    # Stage 5: Evolve
    extension_quotes: List[str] = field(default_factory=list)
    improvement_quotes: List[str] = field(default_factory=list)
    innovation_quotes: List[str] = field(default_factory=list)

    # Stage 6: Reflect
    learning_insight_quotes: List[str] = field(default_factory=list)
    aha_moment_quotes: List[str] = field(default_factory=list)
    metacognition_quotes: List[str] = field(default_factory=list)

    # Metadata
    transcript_length: int = 0
    stage_coverage: Dict[str, bool] = field(default_factory=dict)

    def get_stage_quotes(self, stage: str) -> List[str]:
        """Get all quotes for a specific DRIVER stage"""
        stage_map = {
            "discover": self.problem_definition_quotes + self.goal_setting_quotes + self.requirement_understanding_quotes,
            "represent": self.planning_quotes + self.visualization_quotes + self.structure_quotes,
            "implement": self.execution_quotes + self.code_demonstration_quotes + self.problem_solving_quotes,
            "validate": self.verification_quotes + self.external_validation_quotes + self.accuracy_check_quotes,
            "evolve": self.extension_quotes + self.improvement_quotes + self.innovation_quotes,
            "reflect": self.learning_insight_quotes + self.aha_moment_quotes + self.metacognition_quotes,
        }
        return stage_map.get(stage.lower(), [])

    def has_stage(self, stage: str) -> bool:
        """Check if stage was demonstrated"""
        return self.stage_coverage.get(stage.upper(), False)


class DRIVERTranscriptAnalyzer:
    """
    Extracts DRIVER framework evidence from student transcripts using Claude.
    """

    def __init__(self, client: Anthropic):
        self.client = client

    def analyze(self, transcript: str) -> DRIVEREvidence:
        """
        Analyze transcript using Claude to extract DRIVER evidence.
        """
        prompt = self._build_preprocessing_prompt(self._truncate_transcript_for_prompt(transcript))
        
        # Claude 3.5 Sonnet is efficient and high quality
        model = "claude-3-5-sonnet-latest" 

        try:
            response_text = self._run_preprocessing_request(prompt, model)
        except Exception:
            # Fallback for very large context errors using simple truncation
            # Claude has 200k context, so this is rare for transcripts
            prompt = self._build_preprocessing_prompt(
                self._truncate_transcript_for_prompt(transcript, max_chars=150000)
            )
            response_text = self._run_preprocessing_request(prompt, model)

        return self._parse_driver_evidence(
            response_text,
            len(transcript)
        )

    def _run_preprocessing_request(self, prompt: str, model: str) -> str:
        """Send request to Anthropic API."""
        message = self.client.messages.create(
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model=model,
            temperature=0, # Deterministic evidence extraction
        )
        # Extract text content
        return message.content[0].text

    @staticmethod
    def _truncate_transcript_for_prompt(transcript: str, max_chars: int = 200000) -> str:
        # Claude context is 200k tokens (~800k chars), so we can be generous
        if len(transcript) <= max_chars:
            return transcript
        keep_start_chars = int(max_chars * 0.6)
        keep_end_chars = int(max_chars * 0.3)
        return (
            transcript[:keep_start_chars]
            + "\n\n[... TRANSCRIPT TRUNCATED ...]\n\n"
            + transcript[-keep_end_chars:]
        )

    def _build_preprocessing_prompt(self, transcript: str) -> str:
        return f"""<task>
You are analyzing a student video transcript for evidence of the DRIVER framework.

DRIVER Framework Stages:
1. DISCOVER & DESIGN: Understanding the problem, defining goals, identifying requirements
2. REPRESENT: Planning approach, creating visualizations, structuring solution
3. IMPLEMENT: Executing the plan, writing code, solving problems
4. VALIDATE: Verifying results, external validation, checking accuracy
5. EVOLVE: Extending beyond minimum, improving solution, innovative approaches
6. REFLECT: Learning insights, aha moments, metacognition about process

TRANSCRIPT:
<transcript_text>
{transcript}
</transcript_text>

INSTRUCTIONS:
Extract quotes that demonstrate each DRIVER stage. Use the student's exact words (keep quotes short, 1-2 sentences max).

If a stage is not demonstrated, leave that section empty.

REQUIRED OUTPUT FORMAT (use exactly this structure):

DISCOVER_DESIGN:
- [Quote showing problem understanding]
- [Quote showing goal setting]
- [Quote showing requirement understanding]

REPRESENT:
- [Quote showing planning/visualization]
- [Quote showing structure]

IMPLEMENT:
- [Quote showing execution]
- [Quote showing code demonstration]
- [Quote showing problem solving]

VALIDATE:
- [Quote showing verification]
- [Quote showing external validation]
- [Quote showing accuracy checks]

EVOLVE:
- [Quote showing extensions]
- [Quote showing improvements]
- [Quote showing innovation]

REFLECT:
- [Quote showing learning insights]
- [Quote showing aha moments]
- [Quote showing metacognition]

STAGE_COVERAGE: [List only the stages that were clearly demonstrated, separated by commas: D, R, I, V, E, R]
</task>"""

    def _parse_driver_evidence(
        self,
        llm_output: str,
        transcript_length: int
    ) -> DRIVEREvidence:
        evidence = DRIVEREvidence(transcript_length=transcript_length)

        sections = {
            "DISCOVER_DESIGN": [
                ("problem_definition_quotes", "problem understanding"),
                ("goal_setting_quotes", "goal setting"),
                ("requirement_understanding_quotes", "requirement"),
            ],
            "REPRESENT": [
                ("planning_quotes", "planning"),
                ("visualization_quotes", "visualization"),
                ("structure_quotes", "structure"),
            ],
            "IMPLEMENT": [
                ("execution_quotes", "execution"),
                ("code_demonstration_quotes", "code"),
                ("problem_solving_quotes", "problem solving"),
            ],
            "VALIDATE": [
                ("verification_quotes", "verification"),
                ("external_validation_quotes", "external validation"),
                ("accuracy_check_quotes", "accuracy"),
            ],
            "EVOLVE": [
                ("extension_quotes", "extension"),
                ("improvement_quotes", "improvement"),
                ("innovation_quotes", "innovation"),
            ],
            "REFLECT": [
                ("learning_insight_quotes", "learning"),
                ("aha_moment_quotes", "aha"),
                ("metacognition_quotes", "metacognition"),
            ],
        }

        for section_name, field_mappings in sections.items():
            section_text = self._extract_section(llm_output, section_name)
            quotes = self._extract_quotes(section_text)

            for i, quote in enumerate(quotes):
                field_name = field_mappings[i % len(field_mappings)][0]
                getattr(evidence, field_name).append(quote)

        coverage_text = self._extract_section(llm_output, "STAGE_COVERAGE")
        evidence.stage_coverage = self._parse_stage_coverage(coverage_text)

        return evidence

    def _extract_section(self, text: str, section_name: str) -> str:
        pattern = rf"{section_name}:\s*(.*?)(?=\n[A-Z_]+:|$)"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else ""

    def _extract_quotes(self, section_text: str) -> List[str]:
        quotes = []
        for line in section_text.split("\n"):
            line = line.strip()
            if line.startswith("-") or line.startswith("*"):
                quote = line[1:].strip()
                quote = re.sub(r"^\[|\]$", "", quote)
                if quote and len(quote) > 10:
                    quotes.append(quote)
        return quotes

    def _parse_stage_coverage(self, coverage_text: str) -> Dict[str, bool]:
        coverage = {
            "D": False, "R": False, "I": False, "V": False, "E": False, "R2": False,
        }
        letters = re.findall(r"\b([DRIVER])\b", coverage_text.upper())
        for letter in letters:
            if letter == "R":
                if not coverage["R"]:
                    coverage["R"] = True
                else:
                    coverage["R2"] = True
            else:
                coverage[letter] = True
        return coverage

def analyze_transcript_for_driver(
    transcript: str,
    api_key: Optional[str] = None
) -> DRIVEREvidence:
    """
    Convenience function to analyze a transcript using Claude.
    """
    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        
    if not api_key:
        # Try to find OPENAI key as fallback? No, we need Anthropic key.
        # But maybe user put it in .env? config.py loads .env
        pass
        
    client = Anthropic(api_key=api_key)
    analyzer = DRIVERTranscriptAnalyzer(client)
    return analyzer.analyze(transcript)
