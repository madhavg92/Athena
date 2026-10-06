from athena.core import money
from athena.core.gateway import Source
from athena.tools.base import Tool, ToolContext, ToolResult


def get_money_at_risk(ctx: ToolContext, client: str | None = None) -> ToolResult:
    scope = ctx.cfg.scope_of(ctx.actor)
    clients = scope
    if client:
        from athena.tools.registry import resolve_client

        key = resolve_client(ctx, client)
        if key is None or key not in scope:
            return ToolResult(
                name="get_money_at_risk", ok=False, error=f"refused: {client} is not in your scope"
            )
        clients = [key]
    risks = money.at_risk(ctx.cfg, ctx.sources, clients, ctx.now)
    move = money.biggest_move(ctx.cfg, ctx.sources, risks, clients)
    records = [
        {
            "total_at_risk_usd": sum(r.amount_usd for r in risks),
            "horizon_days": money.assumptions(ctx.cfg)["horizon_days"],
            "biggest_move": move.text if move else None,
            "query_id": "athena.money_at_risk",
        }
    ]
    records += [r.model_dump(mode="json", exclude={"client"}) for r in risks[:10]]
    srcs = (
        [
            Source(name="supaboard.denied_claims", as_of=ctx.now),
            Source(name="supaboard.ar_over_90", as_of=ctx.now),
        ]
        if risks
        else []
    )
    return ToolResult(
        name="get_money_at_risk",
        ok=True,
        client=clients[0] if len(clients) == 1 else None,
        records=records,
        sources=srcs,
    )


TOOL = Tool(
    name="get_money_at_risk",
    description="Dollars that will be lost in the next 14 days unless someone acts, ranked: denials not yet appealed before their appeal deadline, and over-90 AR before timely filing. With expected recovery, Anka's fee at risk, hours of work, and the single biggest move. All clients in scope, or one.",
    parameters={
        "type": "object",
        "properties": {"client": {"type": "string", "description": "Optional: one client."}},
    },
    fn=get_money_at_risk,
    needs_client=False,
)
