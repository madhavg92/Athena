from athena.tools.base import CLIENT_PARAM, Tool, ToolContext, ToolResult, sources_of, to_model_rows


def get_task_history(ctx: ToolContext, client: str, task_id: str | None = None) -> ToolResult:
    rows = ctx.sources.read("smartsheet.task_history", client=client)
    if task_id:
        rows = [r for r in rows if str(r.get("task_id")).lower() == str(task_id).lower()]
    rows.sort(key=lambda r: r.get("time"))
    records = to_model_rows(rows[-40:], ["task_id", "time", "change", "old", "new", "by"], ctx.tz)
    for rec in records:
        person = ctx.cfg.person(str(rec.get("by", "")))
        if person:
            rec["by"] = person.name
    return ToolResult(
        name="get_task_history", ok=True, client=client, records=records, sources=sources_of(rows)
    )


TOOL = Tool(
    name="get_task_history",
    description="Change history of a client's Smartsheet tasks (created, due date moved, reassigned, status changes), optionally for one task id. Use it to explain why a task is late.",
    parameters={
        "type": "object",
        "properties": {"client": CLIENT_PARAM, "task_id": {"type": "string"}},
        "required": ["client"],
    },
    fn=get_task_history,
)
