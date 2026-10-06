from datetime import timedelta

from athena.tools.base import CLIENT_PARAM, Tool, ToolContext, ToolResult, sources_of, to_model_rows


def get_client_activity(ctx: ToolContext, client: str, days: int = 30) -> ToolResult:
    since = ctx.now - timedelta(days=max(1, min(int(days or 30), 90)))
    rows = sorted(
        (r for r in ctx.sources.read("cs_hub.activity", client=client) if r.get("time") >= since),
        key=lambda r: r.get("time"),
    )
    records = to_model_rows(rows, ["time", "type", "summary", "owner"], ctx.tz)
    for rec in records:
        person = ctx.cfg.person(str(rec.get("owner", "")))
        if person:
            rec["owner"] = person.name
    return ToolResult(
        name="get_client_activity",
        ok=True,
        client=client,
        records=records,
        sources=sources_of(rows),
    )


TOOL = Tool(
    name="get_client_activity",
    description="The client activity log from CS Hub: meetings, escalations, commitments Anka made (with dates) and notes. No email or chat content.",
    parameters={
        "type": "object",
        "properties": {
            "client": CLIENT_PARAM,
            "days": {"type": "integer", "description": "Look back, default 30."},
        },
        "required": ["client"],
    },
    fn=get_client_activity,
)
