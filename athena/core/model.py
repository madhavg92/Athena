"""Model layer: one interface, a deterministic stub, and any OpenAI-compatible endpoint."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, Field

from athena.core.config import AthenaConfig, ModelSpec


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = {}


class ModelReply(BaseModel):
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0


class ModelClient(Protocol):
    name: str
    spec: ModelSpec

    def chat(self, messages: list[dict], tools: list[dict] | None) -> ModelReply: ...


class ModelError(Exception):
    pass


def cost_usd(spec: ModelSpec, tokens_in: int, tokens_out: int) -> float:
    return round(
        tokens_in / 1e6 * spec.price_per_mtok_in + tokens_out / 1e6 * spec.price_per_mtok_out, 6
    )


def _tokens(messages: list[dict]) -> int:
    return sum(len(str(m.get("content") or "")) for m in messages) // 4 + 1


# ---------------------------------------------------------------- stub

METRIC_WORDS = {
    "backlog": "backlog",
    "first pass": "first_pass_rate",
    "first_pass": "first_pass_rate",
    "fpr": "first_pass_rate",
    "ar days": "ar_days",
    "ar_days": "ar_days",
    "days in ar": "ar_days",
    "denial rate": "denial_rate",
    "denial_rate": "denial_rate",
    "denials": "denial_rate",
}
TOOL_WORDS = [
    ("get_tasks", ("task", "late", "overdue", "at risk", "due")),
    ("get_tickets", ("ticket", "health", "complain", "issue")),
    (
        "get_owner",
        (
            "who owns",
            "owner",
            "who is the",
            "dm/am",
            "csm for",
            "ba for",
            "hub leader for",
            "contact",
        ),
    ),
    (
        "search_documents",
        (
            "document",
            "sop",
            "contract",
            "statement of work",
            "sow",
            "policy",
            "payer list",
            "turnaround",
            "scope",
        ),
    ),
    ("get_client_profile", ("profile", "about", "weekly call", "specialty", "watch")),
]
BRIEF_TOOLS = ["get_tickets", "get_metrics", "get_tasks", "search_documents", "get_client_profile"]
ROLE_LABELS = {"hub_leader": "Hub leader", "dm_am": "DM/AM", "csm": "CSM", "ba": "BA"}


class StubModel:
    """Deterministic, for tests and the golden harness in fixture mode.

    With `script`, returns the scripted replies in order. Otherwise routes by client name and
    keywords to tools, then writes a templated answer from the tool results only.
    """

    def __init__(
        self,
        clients: dict[str, str] | None = None,
        script: list[ModelReply] | None = None,
        spec: ModelSpec | None = None,
        name: str = "stub",
    ) -> None:
        self.clients = clients or {}  # display name -> key
        self.script = list(script or [])
        self.spec = spec or ModelSpec(kind="stub")
        self.name = name

    def chat(self, messages: list[dict], tools: list[dict] | None) -> ModelReply:
        started = time.monotonic()
        if self.script:
            reply = self.script.pop(0)
        else:
            reply = self._route(messages, tools or [])
        reply.tokens_in = reply.tokens_in or _tokens(messages)
        reply.tokens_out = reply.tokens_out or (len(reply.text) // 4 + 10 * len(reply.tool_calls))
        reply.latency_ms = reply.latency_ms or int((time.monotonic() - started) * 1000)
        return reply

    # -- routing

    def _route(self, messages: list[dict], tools: list[dict]) -> ModelReply:
        last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
        question = messages[last_user]["content"]
        system = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
        results = [m for m in messages[last_user + 1 :] if m["role"] == "tool"]
        if results:
            return ModelReply(text=self._answer(question, results, system))
        available = {t["function"]["name"] for t in tools}
        calls = self._plan(question, available)
        if not calls:
            return ModelReply(
                text="I do not know. I could not find a client or a matching data source in the question."
            )
        return ModelReply(
            tool_calls=[
                ToolCall(id=f"call_{i}", name=n, arguments=a) for i, (n, a) in enumerate(calls)
            ]
        )

    def _client(self, text: str) -> str | None:
        low = text.lower()
        for name, key in sorted(self.clients.items(), key=lambda kv: -len(kv[0])):
            if (
                name.lower() in low
                or key in low
                or name.split()[0].lower() in re.findall(r"[a-z0-9_]+", low)
            ):
                return name
        return None

    def _plan(self, question: str, available: set[str]) -> list[tuple[str, dict]]:
        client = self._client(question)
        if client is None:
            return []
        low = question.lower()
        if low.startswith("brief"):
            calls = []
            for name in BRIEF_TOOLS:
                if name == "get_metrics":
                    calls += [
                        ("get_metrics", {"client": client, "metric": m})
                        for m in ("backlog", "first_pass_rate")
                    ]
                elif name == "search_documents":
                    calls.append(
                        (
                            "search_documents",
                            {"client": client, "words": "statement of work escalation"},
                        )
                    )
                else:
                    calls.append((name, {"client": client}))
            return [c for c in calls if c[0] in available]
        calls: list[tuple[str, dict]] = []
        for word, metric in METRIC_WORDS.items():
            if word in low and not any(c[1].get("metric") == metric for c in calls):
                period = (
                    "last_30_days"
                    if ("month" in low or "30" in low)
                    else "last_7_days"
                    if "week" in low
                    else "latest"
                )
                calls.append(
                    ("get_metrics", {"client": client, "metric": metric, "period": period})
                )
        for tool, words in TOOL_WORDS:
            if any(w in low for w in words):
                args: dict[str, Any] = {"client": client}
                if tool == "search_documents":
                    args["words"] = question
                calls.append((tool, args))
        return [c for c in calls if c[0] in available]

    # -- answers from tool results only

    def _answer(self, question: str, results: list[dict], system: str) -> str:
        lines: list[str] = []
        stale_as_of: list[str] = []
        for msg in results:
            data = json.loads(msg["content"])
            name = msg.get("name", "")
            if not data.get("ok"):
                err = data.get("error", "")
                if "not in your scope" in err:
                    return "I cannot answer this. That client is not in your scope."
                if err.startswith("refused"):
                    lines.append(f"{name}: not available to you.")
                    continue
                lines.append(f"{name}: not available ({err.split(':')[0]}).")
                continue
            if data.get("warning"):
                stale_as_of += data.get("stale_as_of", [])
            lines += _summarise(name, data)
        if not any(lines):
            return "I do not know. The tools returned no data for this question."
        if question.lower().lstrip().startswith("brief"):
            lines = _brief(results)
        text = "\n".join(line for line in lines if line)
        if stale_as_of:
            text = f"Data is not current ({'; '.join(stale_as_of)}).\n" + text
        return text


BRIEF_SECTIONS = [
    ("Health and open tickets", ("get_tickets",)),
    ("Metrics", ("get_metrics",)),
    ("Open tasks", ("get_tasks",)),
    ("Recent documents", ("search_documents",)),
    ("Profile", ("get_client_profile",)),
]


def _brief(results: list[dict]) -> list[str]:
    out: list[str] = []
    for title, names in BRIEF_SECTIONS:
        body: list[str] = []
        for msg in results:
            data = json.loads(msg["content"])
            if msg.get("name") in names and data.get("ok"):
                body += _summarise(msg["name"], data)
        out.append(f"**{title}**")
        out += body or ["No data."]
    return out


def _summarise(name: str, data: dict) -> list[str]:
    rows = data.get("records", [])
    client = data.get("client_name") or data.get("client") or "the client"
    if not rows:
        return [f"No {name.replace('get_', '').replace('_', ' ')} found for {client}."]
    if name == "get_tasks":
        late = [r for r in rows if r.get("late")]
        out = [f"{client} has {len(rows)} open tasks; {len(late)} late."]
        out += [
            f"- {r['task_id']} {r['title']} (due {r['due']}, {r['status']})"
            for r in (late or rows)[:5]
        ]
        return out
    if name == "get_metrics":
        last = rows[-1]
        metric = data.get("metric", "metric")
        if len(rows) == 1:
            return [
                f"{metric} for {client} is {last['actual']} (target {last['target']}) on {last['date']}."
            ]
        avg = round(sum(r["actual"] for r in rows) / len(rows), 1)
        return [
            f"{metric} for {client}: average {avg} over {len(rows)} days; latest {last['actual']} (target {last['target']}) on {last['date']}."
        ]
    if name == "get_tickets":
        out = []
        tickets = rows
        if "health_score" in rows[0]:
            out.append(
                f"Health score for {client} is {rows[0]['health_score']} (trend {rows[0]['trend']})."
            )
            tickets = rows[1:]
        out.append(f"{len(tickets)} open tickets for {client}.")
        out += [
            f"- {t['ticket_id']} {t['subject']} ({t['status']}, {t['priority']})"
            for t in tickets[:5]
        ]
        return out
    if name == "get_owner":
        r = rows[0]
        parts = [
            f"{ROLE_LABELS.get(k, k)}: {v}" for k, v in r.items() if k not in ("client", "hub")
        ]
        return [f"Owners for {r['client']}: " + "; ".join(parts) + "."]
    if name == "search_documents":
        return [f"Documents for {client}:"] + [f"- {d['title']}: {d['snippet']}" for d in rows[:5]]
    if name == "get_client_profile":
        body = [ln for ln in rows[0]["profile"].splitlines() if ln.startswith("- ")]
        return [f"Profile of {client}:"] + body[:5]
    return []


# ---------------------------------------------------------------- OpenAI-compatible


class OpenAICompatModel:
    """Any OpenAI-compatible chat-completions endpoint with tool calls (vLLM, Ollama, Azure AI Foundry...)."""

    def __init__(self, name: str, spec: ModelSpec, client: Any = None) -> None:
        self.name = name
        self.spec = spec
        if client is None:
            from openai import OpenAI

            base_url = os.environ.get(spec.base_url_env or "", "")
            api_key = os.environ.get(spec.api_key_env or "", "")
            if not base_url:
                raise ModelError(f"model {name}: {spec.base_url_env} is not set (G5)")
            client = OpenAI(base_url=base_url, api_key=api_key or "none", timeout=60, max_retries=2)
        self.client = client

    def chat(self, messages: list[dict], tools: list[dict] | None) -> ModelReply:
        started = time.monotonic()
        kwargs: dict[str, Any] = {"model": self.spec.model, "messages": messages, "temperature": 0}
        if tools:
            kwargs["tools"] = tools
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except Exception as exc:  # network, auth, rate limit
            raise ModelError(f"model {self.name}: {type(exc).__name__}") from exc
        msg = resp.choices[0].message
        calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_invalid": tc.function.arguments}
            calls.append(
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args if isinstance(args, dict) else {},
                )
            )
        usage = getattr(resp, "usage", None)
        return ModelReply(
            text=msg.content or "",
            tool_calls=calls,
            tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
            tokens_out=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=int((time.monotonic() - started) * 1000),
        )


def get_model(
    cfg: AthenaConfig, name: str | None = None, factory: Callable[..., Any] | None = None
) -> ModelClient:
    name = name or cfg.models.default
    if name not in cfg.models.models:
        raise ModelError(f"unknown model {name!r}; known: {', '.join(cfg.models.models)}")
    spec = cfg.models.models[name]
    if spec.kind == "stub":
        clients = {c.name: key for key, c in cfg.owner_map.clients.items()}
        return StubModel(clients=clients, spec=spec, name=name)
    return (factory or OpenAICompatModel)(name, spec)
