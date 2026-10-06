import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "fixtures"


def load(name: str):
    return json.loads((FIX / name).read_text())


def digest() -> str:
    h = hashlib.sha256()
    for p in sorted(FIX.rglob("*.json")):
        h.update(p.read_bytes())
    return h.hexdigest()


def test_generator_is_deterministic_and_committed_output_matches() -> None:
    before = digest()
    subprocess.run([sys.executable, str(FIX / "make_fixtures.py")], check=True)
    assert digest() == before


def test_tasks_have_late_at_risk_and_done() -> None:
    anchor = datetime.fromisoformat(load("meta.json")["anchor"])
    tasks = load("smartsheet/tasks.json")
    assert {t["client"] for t in tasks} == {
        "northwind_ortho",
        "bluefield_imaging",
        "cedar_family_clinic",
    }
    late = [
        t for t in tasks if datetime.fromisoformat(t["due"]) < anchor and t["status"] != "Complete"
    ]
    risk = [
        t for t in tasks if anchor < datetime.fromisoformat(t["due"]) < anchor + timedelta(hours=4)
    ]
    done = [t for t in tasks if t["status"] == "Complete"]
    assert late and risk and done


def test_metrics_cover_60_days() -> None:
    rows = load("supaboard/metrics.json")
    days = {r["date"] for r in rows}
    assert len(days) == 60
    assert all("target" in r and "query_id" in r for r in rows)


def test_stale_health_and_history_labels() -> None:
    anchor = datetime.fromisoformat(load("meta.json")["anchor"])
    stale = [
        h
        for h in load("cshub/health.json")
        if anchor - datetime.fromisoformat(h["as_of"]) > timedelta(days=1)
    ]
    assert len(stale) == 1
    hist = load("history/tasks.json")
    assert len(hist) > 300
    assert load("history/labels.json")


def test_meta_marks_synthetic() -> None:
    assert load("meta.json")["synthetic"] is True
