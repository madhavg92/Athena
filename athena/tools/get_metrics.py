from datetime import timedelta

from athena.connectors.supaboard import latest
from athena.tools.base import CLIENT_PARAM, Tool, ToolContext, ToolResult, is_stale, sources_of

PERIODS = {"latest": 1, "last_7_days": 7, "last_week": 7, "last_30_days": 30, "last_60_days": 60}


def get_metrics(ctx: ToolContext, client: str, metric: str, period: str = "latest") -> ToolResult:
    if metric not in ctx.cfg.metrics:
        return ToolResult(
            name="get_metrics",
            ok=False,
            client=client,
            error=f"unknown metric {metric!r}; known: {', '.join(ctx.cfg.metrics)}",
        )
    if period not in PERIODS:
        return ToolResult(
            name="get_metrics",
            ok=False,
            client=client,
            error=f"unknown period {period!r}; use one of {', '.join(PERIODS)}",
        )
    records = ctx.sources.read("supaboard.metrics", client=client, metric=metric)
    if period == "latest":
        records = latest(records)
    else:
        since = (ctx.now - timedelta(days=PERIODS[period])).date().isoformat()
        records = [r for r in records if r.get("date") >= since]
    records.sort(key=lambda r: r.get("date"))
    definition = ctx.cfg.metrics[metric]
    rows = [
        {
            "date": r.get("date"),
            "actual": r.get("actual"),
            "target": r.get("target"),
            "query_id": r.get("query_id"),
        }
        for r in records
    ]
    if rows:
        rows[0]["meaning"] = definition.meaning
    sources = sources_of(records)
    return ToolResult(
        name="get_metrics",
        ok=True,
        client=client,
        records=rows,
        sources=sources,
        stale=is_stale(ctx, sources),
    )


TOOL = Tool(
    name="get_metrics",
    description="Values and targets of one metric for a client from Supaboard. Metrics: backlog, first_pass_rate, ar_days, denial_rate.",
    parameters={
        "type": "object",
        "properties": {
            "client": CLIENT_PARAM,
            "metric": {"type": "string", "description": "Metric name, e.g. backlog."},
            "period": {"type": "string", "enum": list(PERIODS), "description": "Default latest."},
        },
        "required": ["client", "metric"],
    },
    fn=get_metrics,
)
