from athena.core import standing
from athena.tools.base import (
    OPTIONAL_CLIENT,
    Tool,
    ToolContext,
    ToolResult,
    scope_clients,
    sources_of,
)


def get_quality(ctx: ToolContext, client: str | None = None) -> ToolResult:
    clients = scope_clients(ctx, "get_quality", client)
    if isinstance(clients, ToolResult):
        return clients
    rows = standing.findings(ctx.cfg, ctx.sources, clients, ctx.now)
    for r in rows:
        r["due"] = r["due"].isoformat() if r["due"] else None
    return ToolResult(
        name="get_quality",
        ok=True,
        client=clients[0] if len(clients) == 1 else None,
        records=rows,
        sources=sources_of(ctx.sources.read("smartsheet.quality")) if rows else [],
    )


TOOL = Tool(
    name="get_quality",
    description="Open audit findings: internal audits and errors the client found, with severity, due date and whether overdue. All clients in scope, or one.",
    parameters=OPTIONAL_CLIENT,
    fn=get_quality,
    needs_client=False,
)
