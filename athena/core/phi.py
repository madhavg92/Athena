"""PHI scrub (before the model reads text) and lint (before text leaves Athena).

Regex cannot find every name. This is a known limit; the real control is a model host
under a contract that covers the data (gate G5). See docs/DECISIONS.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_NAME = r"[A-Z][a-z]+(?:[ \t]+[A-Z]\.?)?(?:[ \t]+[A-Z][a-z'-]+)?"

# (label, pattern, mask). Order matters: identifiers before names, so that
# "member ID 12345" is masked as an ID and not as a name.
PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (
        "dob",
        re.compile(
            r"\b(?:DOB|D\.O\.B\.?|date of birth|birth ?date)\b[\s:#-]*"
            r"(?:\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}|[A-Z][a-z]{2,8}\.? \d{1,2},? \d{4}|\d{1,2} [A-Z][a-z]{2,8} \d{4})",
            re.IGNORECASE,
        ),
        "DOB [DOB]",
    ),
    (
        "identifier",
        re.compile(
            r"\b(?:MRN|medical record(?: number| no\.?)?|member(?: ?id| ?#| number| no\.?)|"
            r"subscriber(?: ?id| ?#)|acct(?:ount)?(?: ?#| number| no\.?)?|policy(?: ?#| number))"
            r"[\s:#-]*(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{3,}\b",
            re.IGNORECASE,
        ),
        "[ID]",
    ),
    (
        "phone",
        re.compile(
            r"(?:(?<![\w])\+?1[\s.-]?)?(?:\(\d{3}\)\s?|\b\d{3}[\s.-])\d{3}[\s.-]\d{4}\b"
            r"|\+91[\s-]?\d{5}[\s-]?\d{5}\b"
        ),
        "[PHONE]",
    ),
    (
        "name",
        re.compile(
            rf"\b(?i:patient|pt\.?|member|subscriber|beneficiary)(?:'s)?(?:[ \t]+name)?[ \t]*[:\-]?[ \t]*(?P<name>{_NAME})"
        ),
        "",
    ),
]
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)\b")
_NOT_NAMES = {"ID", "Id", "Number", "No", "Portal", "Services", "Eligibility", "Count", "Name"}


@dataclass
class Scrubbed:
    text: str
    suspect: bool
    found: list[str] = field(default_factory=list)


def _external_email(match: re.Match[str], internal: set[str]) -> bool:
    domain = match.group(1).lower()
    return not any(domain == d or domain.endswith("." + d) for d in internal)


def _find(text: str, internal: set[str]) -> list[tuple[str, int, int, str]]:
    hits: list[tuple[str, int, int, str]] = []
    for label, pattern, mask in PATTERNS:
        for m in pattern.finditer(text):
            if label == "name":
                name = m.group("name")
                if name.split()[0] in _NOT_NAMES:
                    continue
                hits.append((label, m.start("name"), m.end("name"), "[NAME]"))
            else:
                hits.append((label, m.start(), m.end(), mask))
    for m in _EMAIL.finditer(text):
        if _external_email(m, internal):
            hits.append(("email", m.start(), m.end(), "[EMAIL]"))
    hits.sort(key=lambda h: (h[1], -(h[2] - h[1])))
    merged: list[tuple[str, int, int, str]] = []
    for hit in hits:
        if merged and hit[1] < merged[-1][2]:
            continue  # overlaps an earlier, longer hit
        merged.append(hit)
    return merged


def scrub(text: str | None, internal_domains: list[str] | None = None) -> Scrubbed:
    """Mask PHI patterns in free text. `suspect` is True when anything was masked."""
    if not text:
        return Scrubbed(text or "", False)
    internal = {d.lower() for d in (internal_domains or [])}
    hits = _find(text, internal)
    out, last = [], 0
    for _, start, end, mask in hits:
        out.append(text[last:start])
        out.append(mask)
        last = end
    out.append(text[last:])
    return Scrubbed("".join(out), bool(hits), sorted({h[0] for h in hits}))


def lint(text: str | None, internal_domains: list[str] | None = None) -> list[str]:
    """Return the PHI pattern labels found in outbound text. Empty list = clean."""
    if not text:
        return []
    internal = {d.lower() for d in (internal_domains or [])}
    return sorted({h[0] for h in _find(text, internal)})
