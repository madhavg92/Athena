"""Golden-question evaluation: `athena eval golden --model <name>`."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from athena.app import build
from athena.connectors.base import fixture_anchor, mode
from athena.core.ask import AskResult
from athena.core.config import AthenaConfig
from athena.core.db import Database


class Expect(BaseModel):
    contains: list[str] = []
    not_contains: list[str] = []
    tools: list[str] = []
    idk: bool | None = None
    refused: bool | None = None
    stale: bool | None = None


class Golden(BaseModel):
    id: str
    persona: str
    user: str
    question: str
    expect: Expect


class Outcome(BaseModel):
    golden: Golden
    result: AskResult
    failures: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def load_golden(path: Path) -> list[Golden]:
    return [Golden.model_validate(item) for item in yaml.safe_load(path.read_text())]


def check(g: Golden, r: AskResult) -> list[str]:
    e, fails = g.expect, []
    text = r.text.lower()
    fails += [f"missing {s!r}" for s in e.contains if s.lower() not in text]
    fails += [f"has {s!r}" for s in e.not_contains if s.lower() in text]
    fails += [f"tool {t} not called" for t in e.tools if t not in r.tools_used]
    for flag in ("idk", "refused", "stale"):
        want = getattr(e, flag)
        if want is not None and getattr(r, flag) != want:
            fails.append(f"{flag} is {getattr(r, flag)}, expected {want}")
    return fails


class ContractError(Exception):
    """A model without a data contract was asked to read live data (G5)."""


def run(cfg: AthenaConfig, model_name: str, path: Path, model: Any = None) -> list[Outcome]:
    spec = cfg.models.models.get(model_name)
    if (
        mode() == "live"
        and spec is not None
        and spec.kind != "stub"
        and spec.contract_covers_data != "yes"
    ):
        raise ContractError(
            f"model {model_name}: contract_covers_data is {spec.contract_covers_data!r}; live runs need 'yes' (G5)"
        )
    clock = (lambda: fixture_anchor()) if mode() == "fixture" else (lambda: datetime.now(UTC))
    app = build(cfg=cfg, db=Database("sqlite://"), clock=clock, model=model or model_name)
    outcomes = []
    for g in load_golden(path):
        if cfg.person(g.user) is None or cfg.person(g.user).persona != g.persona:
            raise ValueError(f"golden {g.id}: user {g.user} is not persona {g.persona}")
        result = app.asker.ask(g.question, g.user, conversation_id=f"golden-{g.id}")
        outcomes.append(Outcome(golden=g, result=result, failures=check(g, result)))
    return outcomes


def summary(outcomes: list[Outcome]) -> dict[str, Any]:
    n = len(outcomes) or 1
    with_tools = [o for o in outcomes if o.golden.expect.tools]
    tool_ok = [
        o for o in with_tools if all(t in o.result.tools_used for t in o.golden.expect.tools)
    ]
    return {
        "questions": len(outcomes),
        "passed": sum(o.passed for o in outcomes),
        "pass_rate": round(sum(o.passed for o in outcomes) / n, 3),
        "tool_accuracy": round(len(tool_ok) / (len(with_tools) or 1), 3),
        "avg_latency_ms": round(sum(o.result.latency_ms for o in outcomes) / n),
        "tokens_in": sum(o.result.tokens_in for o in outcomes),
        "tokens_out": sum(o.result.tokens_out for o in outcomes),
        "cost_usd": round(sum(o.result.cost_usd for o in outcomes), 4),
    }


def write_report(
    model_name: str, outcomes: list[Outcome], out_dir: Path, now: datetime | None = None
) -> Path:
    now = now or datetime.now(UTC)
    s = summary(outcomes)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"eval-{model_name}-{now:%Y%m%dT%H%M%SZ}.md"
    lines = [
        f"# Golden eval: {model_name}",
        "",
        f"Run: {now:%Y-%m-%d %H:%M} UTC. Mode: {mode()}.",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Pass rate | {s['passed']}/{s['questions']} ({s['pass_rate']:.0%}) |",
        f"| Tool-call accuracy | {s['tool_accuracy']:.0%} |",
        f"| Average latency | {s['avg_latency_ms']} ms |",
        f"| Tokens in / out | {s['tokens_in']} / {s['tokens_out']} |",
        f"| Estimated cost | ${s['cost_usd']:.4f} |",
        "",
        "| ID | Persona | Result | Tools | Notes |",
        "|---|---|---|---|---|",
    ]
    for o in outcomes:
        notes = "; ".join(o.failures).replace("|", "/")
        lines.append(
            f"| {o.golden.id} | {o.golden.persona} | {'pass' if o.passed else 'FAIL'} | {', '.join(o.result.tools_used)} | {notes} |"
        )
    path.write_text("\n".join(lines) + "\n")
    data = {
        "model": model_name,
        "time": now.isoformat(),
        "mode": mode(),
        **s,
        "failed": [o.golden.id for o in outcomes if not o.passed],
    }
    path.with_suffix(".json").write_text(json.dumps(data, indent=1) + "\n")
    return path


def compare(reports: Path) -> str:
    """Markdown table comparing the latest eval of each model."""
    latest: dict[str, dict] = {}
    for f in sorted(reports.glob("eval-*.json")):
        data = json.loads(f.read_text())
        if data["model"] not in latest or data["time"] > latest[data["model"]]["time"]:
            latest[data["model"]] = data
    lines = [
        "| Model | Mode | Run (UTC) | Pass rate | Tool accuracy | Avg latency | Tokens in/out | Cost |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, d in sorted(latest.items(), key=lambda kv: (-kv[1]["pass_rate"], kv[0])):
        lines.append(
            f"| {name} | {d['mode']} | {d['time'][:16]} | {d['passed']}/{d['questions']} ({d['pass_rate']:.0%}) | "
            f"{d['tool_accuracy']:.0%} | {d['avg_latency_ms']} ms | {d['tokens_in']}/{d['tokens_out']} | ${d['cost_usd']:.4f} |"
        )
    return "\n".join(lines) + "\n"
