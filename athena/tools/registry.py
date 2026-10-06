"""The six read-only tools. Every call goes through the gateway scope check first."""

from __future__ import annotations

import logging
from typing import Any

from athena.connectors.base import NotConfigured
from athena.tools import (
    get_client_profile,
    get_metrics,
    get_owner,
    get_tasks,
    get_tickets,
    search_documents,
)
from athena.tools.base import Tool, ToolContext, ToolResult

log = logging.getLogger(__name__)

TOOLS: dict[str, Tool] = {
    m.TOOL.name: m.TOOL
    for m in (get_tasks, get_metrics, get_tickets, search_documents, get_owner, get_client_profile)
}


def schemas(names: list[str] | None = None) -> list[dict[str, Any]]:
    return [TOOLS[n].schema() for n in (names or TOOLS)]


def resolve_client(ctx: ToolContext, value: str | None) -> str | None:
    if not value:
        return None
    if value in ctx.cfg.owner_map.clients:
        return value
    return ctx.cfg.client_by_name(value)


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
    if result.client:
        result.meta = {"client_name": ctx.cfg.owner_map.clients[result.client].name, **result.meta}
    if "metric" in args:
        result.meta = {**result.meta, "metric": args["metric"]}
    return result
