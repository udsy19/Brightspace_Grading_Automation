"""FERPA-safe anonymization — generate throwaway anonymous IDs, never send PII to AI"""

import json
import uuid
import re
from pathlib import Path


class Anonymizer:
    """
    Maps real student identifiers to anonymous IDs for AI grading.

    - Generates fresh UUIDs each grading run (not persistent)
    - Strips PII patterns from submission text
    - Maps back to real identities locally after grading
    """

    def __init__(self):
        self._forward: dict[str, str] = {}   # username -> anon_id
        self._reverse: dict[str, str] = {}   # anon_id -> username

    def anonymize(self, username: str) -> str:
        """Get or create an anonymous ID for a student."""
        if username in self._forward:
            return self._forward[username]
        anon_id = f"student_{uuid.uuid4().hex[:8]}"
        self._forward[username] = anon_id
        self._reverse[anon_id] = username
        return anon_id

    def reveal(self, anon_id: str) -> str:
        """Map an anonymous ID back to the real username."""
        return self._reverse.get(anon_id, anon_id)

    def reveal_all(self, data: dict) -> dict:
        """Replace all anonymous IDs in a dict with real usernames."""
        out = {}
        for k, v in data.items():
            real_key = self.reveal(k) if k in self._reverse else k
            out[real_key] = v
        return out

    def strip_pii(self, text: str) -> str:
        """
        Remove common PII patterns from submission text before sending to AI.

        Strips:
        - Email addresses
        - Student ID numbers (7-10 digits)
        - Common name patterns near keywords
        """
        # Remove emails
        text = re.sub(r'\b[\w.-]+@[\w.-]+\.\w+\b', '[EMAIL_REMOVED]', text)

        # Remove student ID patterns (7-10 consecutive digits)
        text = re.sub(r'\b\d{7,10}\b', '[ID_REMOVED]', text)

        # Remove lines that look like name declarations
        text = re.sub(
            r'(?i)(?:my name is|name:|student:)\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+',
            '[NAME_REMOVED]',
            text,
        )

        return text

    def save_mapping(self, path: Path):
        """Save the ID mapping to a file (for audit/debug — keep local only)."""
        mapping = {
            "forward": self._forward,
            "reverse": self._reverse,
        }
        path.write_text(json.dumps(mapping, indent=2))

    def load_mapping(self, path: Path):
        """Load a previously saved ID mapping."""
        if not path.exists():
            return
        data = json.loads(path.read_text())
        self._forward = data.get("forward", {})
        self._reverse = data.get("reverse", {})

    @property
    def count(self) -> int:
        return len(self._forward)
