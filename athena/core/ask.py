"""The ask loop (R1, and R4 for briefs). The model selects read-only tools and writes text.
Code builds the Sources footer, enforces the call limit, and replaces unsupported answers."""

from __future__ import annotations

import json
import logging
import re
import time
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import select

from athena.connectors.registry import Sources
from athena.core.config import AthenaConfig
from athena.core.db import Database, QuestionLog, Turn
from athena.core.gateway import STALE_MARK, Action, Gateway, Source
from athena.core.killswitch import blocked_by
from athena.core.model import ModelClient, ModelError, cost_usd
from athena.core.templates import SYSTEM_RULES, ask_prompt
from athena.tools import registry
from athena.tools.base import ToolContext, ToolResult

log = logging.getLogger(__name__)

IDK = "I do not know"
NOT_SET_UP = "You are not set up for Athena yet."
PAUSED = "Athena is paused for you right now. Please try again later."
MAX_TURNS = 6


class AskResult(BaseModel):
    question: str
    rule_id: str
    answer: str
    footer: str = ""
    idk: bool = False
    stale: bool = False
    refused: bool = False
    tools_used: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    status: str = "sent"

    @property
    def text(self) -> str:
        return f"{self.answer}\n\n{self.footer}" if self.footer else self.answer


def pick_rule(question: str) -> str:
    return "R4" if re.match(r"^\s*brief\b", question, re.IGNORECASE) else "R1"


class Asker:
    def __init__(
        self,
        cfg: AthenaConfig,
        db: Database,
        gateway: Gateway,
        sources: Sources,
        model: ModelClient,
    ) -> None:
        self.cfg, self.db, self.gateway, self.sources, self.model = cfg, db, gateway, sources, model

    def _system(self, user: str, rule_id: str, question: str) -> str:
        rule = self.cfg.rules[rule_id]
        persona = self.cfg.persona_of(user)
        person = self.cfg.person(user)
        clients = [f"{self.cfg.owner_map.clients[c].name} ({c})" for c in self.cfg.scope_of(user)]
        low = question.lower()
        metrics = {
            name: m.meaning
            for name, m in self.cfg.metrics.items()
            if rule_id == "R4" or name.replace("_", " ") in low or name in low
        }
        tz = self.cfg.work_hours_of(user)[1]
        now = self.gateway.clock().astimezone(ZoneInfo(tz))
        parts = [
            SYSTEM_RULES,
            ask_prompt(rule.template or "ask_default", rule.sections),
            f"User: {person.name if person else user}, persona {persona.persona if persona else '-'}.",
            f"Clients in scope: {', '.join(clients) or 'none'}.",
            f"Now: {now:%Y-%m-%d %H:%M} {tz}.",
        ]
        if metrics:
            parts.append(
                "Metric definitions:\n" + "\n".join(f"- {k}: {v}" for k, v in metrics.items())
            )
        return "\n\n".join(parts)

    def _history(self, conversation_id: str) -> list[dict]:
        with self.db.session() as s:
            rows = s.scalars(
                select(Turn)
                .where(Turn.conversation_id == conversation_id)
                .order_by(Turn.id.desc())
                .limit(MAX_TURNS)
            ).all()
        return [{"role": t.role, "content": t.text} for t in reversed(rows)]

    def ask(
        self,
        question: str,
        user: str,
        conversation_id: str | None = None,
        user_assertion: str | None = None,
    ) -> AskResult:
        started = time.monotonic()
        user = user.lower()
        rule_id = pick_rule(question)
        persona = self.cfg.persona_of(user)
        if persona is not None and rule_id not in persona.rules:
            rule_id = "R1"  # e.g. a hub leader asking for a brief gets a normal answer
        conversation_id = conversation_id or user
        if self.cfg.person(user) is None:
            return AskResult(
                question=question,
                rule_id=rule_id,
                answer=NOT_SET_UP,
                refused=True,
                status="refused",
            )
        if blocked_by(self.db, rule_id, [user]):
            return AskResult(
                question=question, rule_id=rule_id, answer=PAUSED, refused=True, status="refused"
            )

        rule = self.cfg.rules[rule_id]
        ctx = ToolContext(
            cfg=self.cfg,
            gateway=self.gateway,
            sources=self.sources,
            actor=user,
            rule_id=rule_id,
            user_assertion=user_assertion,
        )
        messages = [{"role": "system", "content": self._system(user, rule_id, question)}]
        messages += self._history(conversation_id)
        messages.append({"role": "user", "content": question})
        tools = registry.schemas(rule.tools)

        results: list[ToolResult] = []
        tokens_in = tokens_out = 0
        answer = ""
        try:
            while True:
                reply = self.model.chat(
                    messages, tools if len(results) < rule.max_tool_calls else None
                )
                tokens_in += reply.tokens_in
                tokens_out += reply.tokens_out
                if not reply.tool_calls or len(results) >= rule.max_tool_calls:
                    answer = reply.text.strip()
                    break
                messages.append(
                    {
                        "role": "assistant",
                        "content": reply.text or None,
                        "tool_calls": [
                            {
                                "id": c.id,
                                "type": "function",
                                "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                            }
                            for c in reply.tool_calls
                        ],
                    }
                )
                for call in reply.tool_calls:
                    if len(results) >= rule.max_tool_calls:
                        result = ToolResult(
                            name=call.name, ok=False, error="tool call limit reached; answer now"
                        )
                    else:
                        result = registry.call(ctx, call.name, call.arguments, allowed=rule.tools)
                        results.append(result)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": json.dumps(result.for_model(), default=str),
                        }
                    )
        except ModelError as exc:
            log.warning("model failed", extra={"error": str(exc)})
            answer = f"{IDK}. The model is not available right now."

        return self._finish(
            question,
            user,
            conversation_id,
            rule_id,
            answer,
            results,
            tokens_in,
            tokens_out,
            started,
        )

    def _finish(
        self,
        question,
        user,
        conversation_id,
        rule_id,
        answer,
        results,
        tokens_in,
        tokens_out,
        started,
    ) -> AskResult:
        with_data = [r for r in results if r.has_data]
        scope_refused = any(not r.ok and (r.error or "").startswith("refused") for r in results)
        stale = any(r.stale for r in with_data)
        if scope_refused and not with_data:
            answer = "I cannot answer this. That client is not in your scope."
        elif not with_data and not answer.startswith(IDK):
            checked = (
                ", ".join(sorted({r.name for r in results}))
                or "no data source matched the question"
            )
            answer = f"{IDK}. I checked: {checked}."
        elif not answer:
            answer = f"{IDK}."
        if stale and STALE_MARK.lower() not in answer.lower():
            old = [s for r in with_data if r.stale for s in r.sources]
            answer = (
                f"{STALE_MARK} (as of "
                + "; ".join(f"{s.name} {s.as_of:%Y-%m-%d %H:%M} UTC" for s in old)
                + ").\n"
                + answer
            )

        sources: list[Source] = []
        for r in with_data:
            for s in r.sources:
                if (s.name, s.ref) not in {(x.name, x.ref) for x in sources}:
                    sources.append(s)
        tz = self.cfg.work_hours_of(user)[1]
        footer = ""
        if sources:
            footer = "Sources:\n" + "\n".join(
                f"- {s.name}"
                + (f" ({s.ref})" if s.ref else "")
                + f", as of {s.as_of.astimezone(ZoneInfo(tz)):%Y-%m-%d %H:%M}"
                for s in sources
            )
        result = AskResult(
            question=question,
            rule_id=rule_id,
            answer=answer,
            footer=footer,
            idk=answer.startswith(IDK),
            stale=stale,
            refused=scope_refused and not with_data,
            tools_used=[r.name for r in results],
            sources=sources,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd(self.model.spec, tokens_in, tokens_out),
        )
        result.latency_ms = int((time.monotonic() - started) * 1000)
        clients = sorted({r.client for r in with_data if r.client})
        gw = self.gateway.submit(
            Action(
                type="answer",
                rule_id=rule_id,
                actor=user,
                recipients=[user],
                clients=clients,
                text=result.text,
                sources=sources,
                mode="live",
                delivery="now",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=result.cost_usd,
                latency_ms=result.latency_ms,
            )
        )
        if gw.refused:
            result.status = "refused"
            result.refused = True
            result.answer = f"I cannot share this answer. A safety check stopped it ({gw.reason.split(':')[0]})."
            result.footer = ""
        with self.db.session() as s:
            s.add(
                QuestionLog(
                    user=user,
                    question=question,
                    answer=result.text,
                    tools=result.tools_used,
                    idk=result.idk,
                    stale=result.stale,
                    tokens=tokens_in + tokens_out,
                    latency_ms=result.latency_ms,
                )
            )
            s.add(Turn(conversation_id=conversation_id, user=user, role="user", text=question))
            s.add(
                Turn(
                    conversation_id=conversation_id, user=user, role="assistant", text=result.answer
                )
            )
        return result
