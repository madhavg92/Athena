from athena.tools.base import CLIENT_PARAM, Tool, ToolContext, ToolResult, sources_of

BUCKETS = ["0_30", "31_60", "61_90", "over_90"]


def get_ar_aging(ctx: ToolContext, client: str, weeks: int = 4) -> ToolResult:
    weeks = max(1, min(int(weeks or 4), 8))
    rows = sorted(
        ctx.sources.read("supaboard.ar_aging", client=client), key=lambda r: r.get("week_start")
    )[-weeks:]
    records = []
    for r in rows:
        total = r.get("total") or 0
        records.append(
            {
                "week_start": r.get("week_start"),
                "total_usd": total,
                **{f"{b}_usd": r.get(b) for b in BUCKETS},
                "over_90_pct": round(100 * (r.get("over_90") or 0) / total, 1) if total else None,
            }
        )
    return ToolResult(
        name="get_ar_aging", ok=True, client=client, records=records, sources=sources_of(rows)
    )


TOOL = Tool(
    name="get_ar_aging",
    description="Weekly accounts-receivable aging for a client from Supaboard: amounts (USD) in 0-30, 31-60, 61-90 and over-90-day buckets, and the over-90 share. Up to 8 weeks.",
    parameters={
        "type": "object",
        "properties": {
            "client": CLIENT_PARAM,
            "weeks": {"type": "integer", "description": "1-8, default 4."},
        },
        "required": ["client"],
    },
    fn=get_ar_aging,
)
