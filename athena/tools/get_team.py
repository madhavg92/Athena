from athena.tools.base import CLIENT_PARAM, Tool, ToolContext, ToolResult, sources_of


def get_team(ctx: ToolContext, client: str) -> ToolResult:
    rows = ctx.sources.read("smartsheet.team", client=client)
    records = [
        {
            k: r.get(k)
            for k in (
                "member",
                "role",
                "fte",
                "on_leave_today",
                "leave_until",
                "open_items",
                "utilisation_pct",
            )
        }
        for r in rows
    ]
    return ToolResult(
        name="get_team", ok=True, client=client, records=records, sources=sources_of(rows)
    )


TOOL = Tool(
    name="get_team",
    description="The team working on a client (from the resource sheet): member, role, FTE, who is on leave and until when, open items and utilisation.",
    parameters={"type": "object", "properties": {"client": CLIENT_PARAM}, "required": ["client"]},
    fn=get_team,
)
