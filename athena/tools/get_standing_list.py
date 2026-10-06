from athena.core import standing
from athena.tools.base import Tool, ToolContext, ToolResult, sources_of

DATASETS = [
    "smartsheet.attendance",
    "smartsheet.team",
    "smartsheet.blockers",
    "smartsheet.quality",
    "supaboard.workload",
    "cs_hub.tickets",
]


def get_standing_list(ctx: ToolContext) -> ToolResult:
    items = standing.standing_list(ctx.cfg, ctx.sources, ctx.actor, ctx.now)
    records = [i.model_dump() for i in items]
    records.append({"key": "not_visible", "detail": standing.NOT_VISIBLE})
    srcs = [s for d in DATASETS for s in sources_of(ctx.sources.read(d))]
    return ToolResult(name="get_standing_list", ok=True, records=records, sources=srcs)


TOOL = Tool(
    name="get_standing_list",
    description="The hub leader's always-open list across all their clients, counted now: who is not working today, short-staffed work, people on notice or in training, logins and access problems, things waiting on the client, clearinghouse problems, work over turnaround, claims near deadlines, audit findings, escalations and promises to clients. Each item says whether it needs the hub leader today.",
    parameters={"type": "object", "properties": {}},
    fn=get_standing_list,
    needs_client=False,
)
