from athena.tools.base import (
    CLIENT_PARAM,
    Tool,
    ToolContext,
    ToolResult,
    is_stale,
    sources_of,
    to_model_rows,
)

FIELDS = ["task_id", "title", "owner", "due", "status", "last_update"]


def get_tasks(ctx: ToolContext, client: str, status: str | None = None) -> ToolResult:
    records = ctx.sources.read("smartsheet.tasks", client=client)
    if status:
        records = [r for r in records if (r.get("status") or "").lower() == status.lower()]
    else:
        records = [r for r in records if r.get("status") != "Complete"]
    records.sort(key=lambda r: r.get("due"))
    sources = sources_of(records)
    rows = to_model_rows(records, FIELDS, ctx.tz)
    for row, rec in zip(rows, records, strict=True):
        row["late"] = rec.get("due") < ctx.now and rec.get("status") != "Complete"
    return ToolResult(
        name="get_tasks",
        ok=True,
        client=client,
        records=rows,
        sources=sources,
        stale=is_stale(ctx, sources),
    )


TOOL = Tool(
    name="get_tasks",
    description="Open tasks for a client from Smartsheet: id, title, owner, due, status, last update, late flag.",
    parameters={
        "type": "object",
        "properties": {
            "client": CLIENT_PARAM,
            "status": {"type": "string", "description": "Optional status filter, e.g. 'Complete'."},
        },
        "required": ["client"],
    },
    fn=get_tasks,
)
