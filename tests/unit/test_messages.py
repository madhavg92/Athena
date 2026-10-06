from pathlib import Path

from athena.core.model import ModelError, ModelReply, StubModel
from athena.core.templates import render, write_message

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = {
    "item_key": "T-1001",
    "severity_label": "Late",
    "title": "Post payments batch",
    "client_name": "Northwind Orthopedics",
    "due": "05 Oct 10:00",
    "status": "In Progress",
    "owner": "dm.one@fixture.local",
    "link": "https://x",
}


def test_render_template_and_missing_fields() -> None:
    text = render(ROOT, "late_task_alert", PAYLOAD)
    assert text.startswith("Late: Post payments batch (Northwind Orthopedics) is due 05 Oct 10:00")
    assert render(ROOT, "late_task_alert", {"severity_label": "Late"}).startswith("Late: - (-)")
    assert render(ROOT, "no_such_template", PAYLOAD) == "Late: T-1001 for Northwind Orthopedics."


def test_template_writer_skips_model() -> None:
    class Boom:
        def chat(self, *a):
            raise AssertionError("should not be called")

    assert write_message(Boom(), ROOT, "late_task_alert", PAYLOAD, writer="template")[0].startswith(
        "Late:"
    )


def test_model_writes_from_payload() -> None:
    model = StubModel(
        script=[
            ModelReply(
                text="Post payments batch for Northwind Orthopedics is late (due 05 Oct 10:00)."
            )
        ]
    )
    text, t_in, _ = write_message(model, ROOT, "late_task_alert", PAYLOAD)
    assert text.startswith("Post payments batch for Northwind") and t_in > 0


def test_model_failure_falls_back() -> None:
    class Broken:
        def chat(self, *a):
            raise ModelError("down")

    assert write_message(Broken(), ROOT, "late_task_alert", PAYLOAD)[0] == render(
        ROOT, "late_task_alert", PAYLOAD
    )


def test_bad_model_text_falls_back() -> None:
    for bad in ("", "x" * 500, "Something unrelated happened."):
        model = StubModel(script=[ModelReply(text=bad)])
        assert write_message(model, ROOT, "late_task_alert", PAYLOAD)[0] == render(
            ROOT, "late_task_alert", PAYLOAD
        )


def test_stub_writer_mode_returns_template() -> None:
    assert write_message(StubModel(), ROOT, "late_task_alert", PAYLOAD)[0] == render(
        ROOT, "late_task_alert", PAYLOAD
    )
