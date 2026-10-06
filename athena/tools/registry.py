"""The read-only tools. Every call goes through the gateway scope check first."""

from __future__ import annotations

import logging
from typing import Any

from athena.connectors.base import NotConfigured
from athena.tools import (
    get_ar_aging,
    get_blocked_work,
    get_capacity,
    get_client_activity,
    get_client_economics,
    get_client_profile,
    get_denials,
    get_meetings,
    get_metrics,
    get_money_at_risk,
    get_my_alerts,
    get_owner,
    get_quality,
    get_standing_list,
    get_task_history,
    get_tasks,
    get_team,
    get_tickets,
    search_documents,
)
from athena.tools.base import Tool, ToolContext, ToolResult, stale_sources

log = logging.getLogger(__name__)

TOOLS: dict[str, Tool] = {
    m.TOOL.name: m.TOOL
    for m in (
        get_tasks,
        get_metrics,
        get_tickets,
        search_documents,
        get_owner,
        get_client_profile,
        get_denials,
        get_ar_aging,
        get_task_history,
        get_team,
        get_client_activity,
        get_my_alerts,
        get_money_at_risk,
        get_client_economics,
        get_meetings,
        get_standing_list,
        get_capacity,
        get_blocked_work,
        get_quality,
    )
}


TOOL_SOURCES = {
    "get_tasks": "smartsheet",
    "get_metrics": "supaboard",
    "get_tickets": "cs_hub",
    "search_documents": "sharepoint",
    "get_denials": "supaboard",
    "get_ar_aging": "supaboard",
    "get_task_history": "smartsheet",
    "get_team": "smartsheet",
    "get_client_activity": "cs_hub",
    "get_money_at_risk": "supaboard",
    "get_client_economics": "economics",
    "get_standing_list": "smartsheet",
    "get_capacity": "smartsheet",
    "get_blocked_work": "smartsheet",
    "get_quality": "smartsheet",
}  # get_owner and get_client_profile read Git context files: always allowed


def schemas(names: list[str] | None = None) -> list[dict[str, Any]]:
    return [TOOLS[n].schema() for n in (names or TOOLS)]


def resolve_client(ctx: ToolContext, value: str | None) -> str | None:
    if not value:
        return None
    if value in ctx.cfg.owner_map.clients:
        return value
    found = ctx.cfg.client_by_name(value)
    if found:
        return found
    # a short name ("Northwind"): accept it only when it matches exactly one client
    low = value.lower().strip()
    hits = [
        k
        for k, c in ctx.cfg.owner_map.clients.items()
        if low and (c.name.lower().startswith(low) or k.startswith(low))
    ]
    return hits[0] if len(hits) == 1 else None


def call(
    ctx: ToolContext, name: str, arguments: dict[str, Any], allowed: list[str] | None = None
) -> ToolResult:
    if name not in TOOLS or (allowed is not None and name not in allowed):
        return ToolResult(name=name, ok=False, error=f"unknown tool {name!r}")
    tool = TOOLS[name]
    args = dict(arguments or {})
    known = set(tool.parameters.get("properties", {}))
    unknown = set(args) - known
    if unknown:
        return ToolResult(
            name=name, ok=False, error=f"unknown arguments: {', '.join(sorted(unknown))}"
        )
    missing = [p for p in tool.parameters.get("required", []) if not args.get(p)]
    if missing:
        return ToolResult(name=name, ok=False, error=f"missing arguments: {', '.join(missing)}")
    persona = ctx.cfg.persona_of(ctx.actor)
    source = TOOL_SOURCES.get(name)
    if persona is not None and source and source not in persona.sources:
        return ToolResult(
            name=name, ok=False, error=f"refused: source {source} is not available to your persona"
        )
    if tool.needs_client:
        client = resolve_client(ctx, args.get("client"))
        if client is None:
            return ToolResult(name=name, ok=False, error=f"unknown client {args.get('client')!r}")
        refusal = ctx.gateway.authorize_tool(ctx.actor, ctx.rule_id, [client])
        if refusal:
            log.info("tool refused", extra={"tool": name, "reason": refusal.split(":")[0]})
            return ToolResult(
                name=name,
                ok=False,
                client=client,
                error=f"refused: {client} is not in your scope"
                if refusal.startswith("scope")
                else f"refused: {refusal}",
            )
        args["client"] = client
    try:
        result = tool.fn(ctx, **args)
    except NotConfigured as exc:
        return ToolResult(name=name, ok=False, error=f"source not available: {exc}")
    result.stale_sources = stale_sources(ctx, result.sources)
    result.stale = bool(result.stale_sources)
    if result.client:
        result.meta = {"client_name": ctx.cfg.owner_map.clients[result.client].name, **result.meta}
    if "metric" in args:
        result.meta = {**result.meta, "metric": args["metric"]}
    return result
