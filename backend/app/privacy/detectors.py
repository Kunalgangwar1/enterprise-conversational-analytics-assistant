"""Deterministic detectors for seeded identifiers and conservative generic PII."""

import re
from dataclasses import dataclass

from app.privacy.models import IdentifierType


@dataclass(frozen=True, slots=True)
class IdentifierPattern:
    """An explicitly prioritized synthetic identifier pattern."""

    identifier_type: IdentifierType
    pattern: re.Pattern[str]
    priority: int


@dataclass(frozen=True, slots=True)
class IdentifierMatch:
    """A detected identifier span without any logging behavior."""

    start: int
    end: int
    identifier_type: IdentifierType
    priority: int


_IDENTIFIER_BOUNDARY_LEFT = r"(?<![A-Za-z0-9_@])"
_IDENTIFIER_BOUNDARY_RIGHT = r"(?![A-Za-z0-9_@])"

IDENTIFIER_PATTERNS: tuple[IdentifierPattern, ...] = (
    IdentifierPattern(
        IdentifierType.MEMBER,
        re.compile(rf"{_IDENTIFIER_BOUNDARY_LEFT}M\d{{6}}{_IDENTIFIER_BOUNDARY_RIGHT}"),
        0,
    ),
    IdentifierPattern(
        IdentifierType.PROVIDER,
        re.compile(rf"{_IDENTIFIER_BOUNDARY_LEFT}P\d{{5}}{_IDENTIFIER_BOUNDARY_RIGHT}"),
        1,
    ),
    IdentifierPattern(
        IdentifierType.FACILITY,
        re.compile(rf"{_IDENTIFIER_BOUNDARY_LEFT}F\d{{4}}{_IDENTIFIER_BOUNDARY_RIGHT}"),
        2,
    ),
    IdentifierPattern(
        IdentifierType.ENCOUNTER,
        re.compile(rf"{_IDENTIFIER_BOUNDARY_LEFT}E\d{{7}}{_IDENTIFIER_BOUNDARY_RIGHT}"),
        3,
    ),
    IdentifierPattern(
        IdentifierType.CLAIM,
        re.compile(rf"{_IDENTIFIER_BOUNDARY_LEFT}C\d{{7}}{_IDENTIFIER_BOUNDARY_RIGHT}"),
        4,
    ),
    IdentifierPattern(
        IdentifierType.APPOINTMENT,
        re.compile(rf"{_IDENTIFIER_BOUNDARY_LEFT}A\d{{7}}{_IDENTIFIER_BOUNDARY_RIGHT}"),
        5,
    ),
)

EXISTING_TOKEN_PATTERN = re.compile(r"(?<![A-Za-z0-9_])T\d{3,}(?![A-Za-z0-9_])")
EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_%+\-])"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~\-]+"
    r"@[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?)+"
    r"(?![A-Za-z0-9_%+\-])"
)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+1[ .\-]?)?(?:\(\d{3}\)|\d{3})[ .\-]\d{3}[ .\-]\d{4}(?!\w)")
CREDENTIAL_PATTERN = re.compile(
    r"(?i)(?:\bbearer\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"\b(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*[^\s,;]+)"
)


def detect_identifiers(text: str) -> tuple[IdentifierMatch, ...]:
    """Find business identifiers and resolve overlap by explicit pattern priority."""

    candidates = [
        IdentifierMatch(match.start(), match.end(), definition.identifier_type, definition.priority)
        for definition in IDENTIFIER_PATTERNS
        for match in definition.pattern.finditer(text)
    ]
    candidates.sort(key=lambda item: (item.start, item.priority, -(item.end - item.start)))

    selected: list[IdentifierMatch] = []
    for candidate in candidates:
        if any(candidate.start < match.end and match.start < candidate.end for match in selected):
            continue
        selected.append(candidate)
    return tuple(sorted(selected, key=lambda item: item.start))
