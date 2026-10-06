"""Prompt templates for the ask loop and plain message templates for alerts and digests."""

from __future__ import annotations

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
