from athena.core import meetings
from athena.core.gateway import Source
from athena.tools.base import Tool, ToolContext, ToolResult, fmt_time


def get_meetings(ctx: ToolContext, title: str | None = None) -> ToolResult:
    """The user's own meetings this week; with a title, the prepared facts and decisions for that meeting."""
    rows = meetings.upcoming(ctx.sources, ctx.actor, ctx.now)
    if title:
        match = next((m for m in rows if title.lower() in m["title"].lower()), None)
        if match is None:
            return ToolResult(name="get_meetings", ok=True, records=[])
        facts = meetings.brief(ctx.cfg, ctx.sources, ctx.actor, match, ctx.now)
        facts["start"] = fmt_time(facts["start"], ctx.tz)
        return ToolResult(
            name="get_meetings",
            ok=True,
            records=[facts],
            sources=[
                Source(name="calendar", as_of=ctx.now),
                Source(name="supaboard.metrics", as_of=ctx.now),
            ],
        )
    records = [
        {
            "title": m["title"],
            "start": fmt_time(m["start"], ctx.tz),
            "type": m["type"],
            "client": ctx.cfg.owner_map.clients[m["client"]].name if m.get("client") else None,
        }
        for m in rows
    ]
    return ToolResult(
        name="get_meetings",
        ok=True,
        records=records,
        sources=[Source(name="calendar", as_of=ctx.now)] if records else [],
    )


TOOL = Tool(
    name="get_meetings",
    description="The user's meetings this week (titles and times only). Pass a title to get the prepared facts for that meeting: what changed, tickets waiting on us, commitments, money at risk and the decisions needed.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Optional: part of a meeting title."}
        },
    },
    fn=get_meetings,
    needs_client=False,
)
