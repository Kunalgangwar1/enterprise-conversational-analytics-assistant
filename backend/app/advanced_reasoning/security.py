"""Shared deterministic rejection of executable planner output."""

import re

_EXECUTABLE_PREFIX = re.compile(
    r"^\s*(?:"
    r"select\b|with\s+[a-z_][a-z0-9_]*\s+as\s*\(|insert\s+into\b|"
    r"update\s+[a-z_][a-z0-9_]*\s+set\b|delete\s+from\b|"
    r"drop\s+(?:table|view)\b|alter\s+(?:table|view)\b|"
    r"create\s+(?:table|view)\b|truncate\s+table\b|merge\s+into\b|"
    r"grant\s+|revoke\s+|python(?:3)?\s+|bash\s+|sh\s+|curl\s+|wget\s+|rm\s+|sudo\s+"
    r")",
    re.IGNORECASE,
)
_URL = re.compile(r"https?://", re.IGNORECASE)


def contains_disallowed_executable_content(value: str) -> bool:
    """Reject code-like output while allowing ordinary analytical instructions."""

    return _EXECUTABLE_PREFIX.search(value) is not None or _URL.search(value) is not None
