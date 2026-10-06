from athena.core import standing
from athena.tools.base import (
    OPTIONAL_CLIENT,
    Tool,
    ToolContext,
    ToolResult,
    scope_clients,
    sources_of,
)


def get_capacity(ctx: ToolContext, client: str | None = None) -> ToolResult:
    clients = scope_clients(ctx, "get_capacity", client)
    if isinstance(clients, ToolResult):
        return clients
    gaps = standing.capacity(ctx.cfg, ctx.sources, clients, ctx.now)
    srcs = sources_of(ctx.sources.read("smartsheet.attendance")) + sources_of(
        ctx.sources.read("supaboard.workload")
    )
    return ToolResult(
        name="get_capacity",
        ok=True,
        client=clients[0] if len(clients) == 1 else None,
        records=[g.model_dump(exclude={"client"}) for g in gaps],
        sources=srcs if gaps else [],
    )


TOOL = Tool(
    name="get_capacity",
    description="Today's people against today's work, by client and work type: expected inflow, backlog, oldest item against the turnaround target, FTE needed and present, the gap (positive = short), who is absent, and who is trained to cover and what that leaves short. All clients in scope, or one.",
    parameters=OPTIONAL_CLIENT,
    fn=get_capacity,
    needs_client=False,
)
