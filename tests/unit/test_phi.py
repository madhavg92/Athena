import pytest

from athena.core.phi import lint, scrub

INTERNAL = ["fixture.local"]

CASES = [
    # (input, expected labels, must not survive, must survive)
    ("SSN 123-45-6789 on file", ["ssn"], ["123-45-6789"], ["on file"]),
    ("DOB: 04/12/1961 needs check", ["dob"], ["04/12/1961"], ["needs check"]),
    ("date of birth 1961-04-12", ["dob"], ["1961-04-12"], []),
    ("MRN 00A12345 pending", ["identifier"], ["00A12345"], ["pending"]),
    ("member ID W123456789 denied", ["identifier"], ["W123456789"], ["denied"]),
    ("acct # 99887766 rebill", ["identifier"], ["99887766"], ["rebill"]),
    ("call (555) 123-4567 today", ["phone"], ["123-4567"], ["today"]),
    ("call 555-123-4567", ["phone"], ["555-123-4567"], []),
    ("call +91 98765 43210", ["phone"], ["98765 43210"], []),
    ("mail jo@gmail.com now", ["email"], ["jo@gmail.com"], ["now"]),
    ("patient John Smith called", ["name"], ["John Smith"], ["called"]),
    ("pt: Mary Jones denied", ["name"], ["Mary Jones"], ["denied"]),
    ("Member Ann Lee appeal", ["name"], ["Ann Lee"], ["appeal"]),
]

CLEAN = [
    "Backlog for Northwind Orthopedics is 412 items, target 300.",
    "Task T-1042 is due 2026-10-06 14:00 and owned by dm.one@fixture.local.",
    "Patient count rose by 4% this week.",
    "First pass rate 93.1% on 2026-10-01.",
    "Sheet 1000000000000001 has 14 rows.",
    "Eligibility checks are at risk.",
]


@pytest.mark.parametrize("text,labels,gone,kept", CASES)
def test_scrub_masks(text: str, labels: list[str], gone: list[str], kept: list[str]) -> None:
    result = scrub(text, INTERNAL)
    assert result.suspect
    assert result.found == labels
    for item in gone:
        assert item not in result.text
    for item in kept:
        assert item in result.text
    assert lint(text, INTERNAL) == labels


@pytest.mark.parametrize("text", CLEAN)
def test_clean_text_passes(text: str) -> None:
    result = scrub(text, INTERNAL)
    assert not result.suspect and result.text == text
    assert lint(text, INTERNAL) == []


def test_scrubbed_text_lints_clean() -> None:
    for text, *_ in CASES:
        assert lint(scrub(text, INTERNAL).text, INTERNAL) == []


def test_empty() -> None:
    assert scrub(None).text == "" and lint("") == []
