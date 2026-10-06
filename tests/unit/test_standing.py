from athena.connectors.base import fixture_anchor
from athena.connectors.registry import Sources
from athena.core import phi, standing

ANCHOR = fixture_anchor()
HL = "hl.key@fixture.local"


def _sources(cfg) -> Sources:
    return Sources(cfg, clock=lambda: ANCHOR, run_mode="fixture")


def test_capacity_finds_gaps_and_trained_cover(cfg) -> None:
    gaps = {
        (g.client, g.work_type): g
        for g in standing.capacity(cfg, _sources(cfg), cfg.scope_of(HL), ANCHOR)
    }
    assert ("cedar_family_clinic", "Full cycle") not in gaps  # other hub
    posting = gaps[("northwind_ortho", "Payment posting")]
    assert posting.present_fte == 0 and posting.gap_fte > 0.5 and posting.over_tat
    assert posting.absent == ["Analyst N2 (planned leave)"]
    auth = gaps[("bluefield_imaging", "Prior auth")]
    assert auth.absent == ["Analyst B2 (unplanned absence)"]
    assert auth.covers and auth.covers[0].startswith("Analyst B1 (leaves Eligibility")
    assert gaps[("bluefield_imaging", "Eligibility")].gap_fte < 0  # room


def test_blocked_work_counts_hours_and_expiry(cfg) -> None:
    rows = {
        b["blocker_id"]: b for b in standing.blocked(cfg, _sources(cfg), cfg.scope_of(HL), ANCHOR)
    }
    assert "BL-309" not in rows and "BL-310" not in rows  # closed; other hub
    assert rows["BL-301"]["people_blocked"] == 2 and 0 < rows["BL-301"]["hours_lost"] < 4
    assert 0 < rows["BL-302"]["expires_in_hours"] <= 48
    assert rows["BL-304"]["age_days"] > 5 and rows["BL-304"]["amount_usd"] == 12800


def test_standing_list_flags_what_needs_the_hub_leader(cfg) -> None:
    items = {i.key: i for i in standing.standing_list(cfg, _sources(cfg), HL, ANCHOR)}
    assert list(items) == [
        "absent",
        "short",
        "people_pipeline",
        "access",
        "waiting_on_client",
        "clearinghouse",
        "over_tat",
        "deadlines",
        "quality",
        "escalations",
        "promises",
    ]
    assert items["absent"].count == 2 and items["absent"].needs_you  # one unplanned absence
    assert items["short"].count == 2 and "no trained cover" not in items["short"].detail
    waiting = items["waiting_on_client"]
    assert waiting.count == 4 and set(waiting.refs) == {"BL-303", "BL-304", "BL-306"}
    assert items["access"].needs_you and "BL-302" in items["access"].refs
    assert items["quality"].needs_you and items["quality"].refs == ["QF-41"]
    assert not items["promises"].needs_you and not items["people_pipeline"].needs_you
    assert "Cedar" not in " ".join(i.detail for i in items.values())


def test_report_is_a_clean_draft(cfg) -> None:
    items = standing.standing_list(cfg, _sources(cfg), HL, ANCHOR)
    text = standing.report_text(cfg, items, HL, ANCHOR)
    assert text.startswith("Hub report, Mon 05 Oct 11:30")
    assert "Waiting on the client: 4." in text and standing.NOT_VISIBLE in text
    assert not phi.lint(text, ["fixture.local"])
