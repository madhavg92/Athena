from collections import defaultdict
from datetime import timedelta

from athena.tools.base import CLIENT_PARAM, Tool, ToolContext, ToolResult, sources_of

PERIODS = {"last_7_days": 7, "last_14_days": 14, "last_30_days": 30, "last_60_days": 60}


def get_denials(
    ctx: ToolContext, client: str, period: str = "last_30_days", group_by: str = "payer"
) -> ToolResult:
    if period not in PERIODS or group_by not in ("payer", "reason", "payer_and_reason", "week"):
        return ToolResult(
            name="get_denials",
            ok=False,
            client=client,
            error="period must be last_7/14/30/60_days; group_by payer, reason, payer_and_reason or week",
        )
    since = (ctx.now - timedelta(days=PERIODS[period])).date().isoformat()
    rows = [
        r for r in ctx.sources.read("supaboard.denials", client=client) if r.get("date") >= since
    ]
    claims = [
        r for r in ctx.sources.read("supaboard.claims", client=client) if r.get("date") >= since
    ]
    groups: dict[str, int] = defaultdict(int)
    for r in rows:
        if group_by == "payer":
            key = r.get("payer")
        elif group_by == "reason":
            key = f"{r.get('reason_code')} {r.get('reason')}"
        elif group_by == "week":
            key = r.get("date")[:8] + "w" + str((int(r.get("date")[8:]) - 1) // 7 + 1)
        else:
            key = f"{r.get('payer')} | {r.get('reason_code')} {r.get('reason')}"
        groups[key] += r.get("count") or 0
    total = sum(groups.values())
    submitted = sum(c.get("submitted") or 0 for c in claims)
    records = [
        {"group": k, "denials": v, "share_pct": round(100 * v / total, 1) if total else 0}
        for k, v in sorted(groups.items(), key=lambda kv: -kv[1])
    ][:12]
    summary = {
        "period": period,
        "claims_submitted": submitted,
        "denials": total,
        "denial_rate_pct": round(100 * total / submitted, 2) if submitted else None,
        "query_id": f"sb.denials.{group_by}",
    }
    return ToolResult(
        name="get_denials",
        ok=True,
        client=client,
        records=[summary, *records],
        sources=sources_of(rows + claims),
    )


TOOL = Tool(
    name="get_denials",
    description="Claim denials for a client from Supaboard over a period, grouped by payer, by reason (CARC code), by payer and reason, or by week; with claims submitted and the denial rate.",
    parameters={
        "type": "object",
        "properties": {
            "client": CLIENT_PARAM,
            "period": {
                "type": "string",
                "enum": list(PERIODS),
                "description": "Default last_30_days.",
            },
            "group_by": {
                "type": "string",
                "enum": ["payer", "reason", "payer_and_reason", "week"],
                "description": "Default payer.",
            },
        },
        "required": ["client"],
    },
    fn=get_denials,
)
