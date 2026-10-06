from sqlalchemy import inspect, select

from athena.core.db import Alert, Database, Receipt, as_utc

TABLES = {
    "receipts",
    "alerts",
    "digest_items",
    "question_log",
    "turns",
    "kill_switches",
    "review_marks",
    "rule_state",
}


def test_tables_created(db: Database) -> None:
    assert TABLES <= set(inspect(db.engine).get_table_names())


def test_receipt_and_alert_round_trip(db: Database) -> None:
    with db.session() as s:
        s.add(Receipt(actor="system", action_type="notify", mode="shadow", status="shadow"))
        s.add(Alert(rule_id="R2", item_key="R2:t1", severity="late", payload={"a": 1}))
    with db.session() as s:
        receipt = s.scalars(select(Receipt)).one()
        alert = s.scalars(select(Alert)).one()
    assert receipt.sources == [] and as_utc(receipt.time).tzinfo is not None
    assert alert.state == "open" and alert.payload == {"a": 1} and alert.sends_count == {}


def test_database_url_from_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/x.db")
    assert Database().url.endswith("x.db")
    assert (tmp_path / "x.db").exists()
