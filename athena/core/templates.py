"""Prompt templates for the ask loop and plain message templates for alerts and digests."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

SYSTEM_RULES = """You are Athena, Anka's internal assistant for managers.
Rules:
- Use only tool results and context files. Do not use outside knowledge about clients.
- If the tools do not give the answer, say "I do not know" and say what you checked.
- If a tool result says the data is old, say "Data is not current" and give the as_of time.
- Never give patient-level details.
- Keep answers short: the answer first, then up to 5 bullet points.
- Do not add a sources list; Athena adds it."""

ASK_TEMPLATES = {
    "ask_default": "Answer the user's question about their clients.",
    "client_brief": (
        "Write a pre-call brief on the client with these sections, in this order: "
        "{sections}. One to three lines for each section. Use the tools for every section."
    ),
}


def ask_prompt(template: str, sections: list[str]) -> str:
    text = ASK_TEMPLATES.get(template, ASK_TEMPLATES["ask_default"])
    return text.format(sections=", ".join(s.replace("_", " ") for s in sections))


# ---- alert and digest messages ----

WRITER_SYSTEM = (
    "You write short alert messages for Anka managers. Use only the JSON payload. "
    "One or two sentences. Include the client, the item, the due time and the severity. "
    "Do not add facts. Never give patient details."
)
MAX_MESSAGE_CHARS = 400


class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return "-"


@lru_cache(maxsize=4)
def message_templates(root: str) -> dict[str, str]:
    path = Path(root) / "context" / "templates" / "messages.yaml"
    return yaml.safe_load(path.read_text()) if path.exists() else {}


def render(root: Path, template: str, payload: dict[str, Any]) -> str:
    templates = message_templates(str(root))
    text = templates.get(template) or templates.get("default") or "{severity_label}: {item_key}"
    return " ".join(text.format_map(_Safe(payload)).split())


def write_message(
    model: Any, root: Path, template: str, payload: dict[str, Any], writer: str = "model"
) -> tuple[str, int, int]:
    """Model writes from the payload only; the plain template is used if the model fails.
    Returns (text, tokens_in, tokens_out)."""
    plain = render(root, template, payload)
    if writer != "model" or model is None:
        return plain, 0, 0
    messages = [
        {"role": "system", "content": WRITER_SYSTEM},
        {
            "role": "user",
            "content": json.dumps({"template_hint": plain, "payload": payload}, default=str),
        },
    ]
    try:
        reply = model.chat(messages, None)
    except Exception as exc:  # any model failure -> plain template
        log.warning("message writer failed", extra={"error": type(exc).__name__})
        return plain, 0, 0
    text = " ".join((reply.text or "").split())
    key = str(payload.get("item_key", ""))
    if (
        not text
        or len(text) > MAX_MESSAGE_CHARS
        or (key and key not in text and str(payload.get("title", "")) not in text)
    ):
        return plain, reply.tokens_in, reply.tokens_out
    return text, reply.tokens_in, reply.tokens_out
