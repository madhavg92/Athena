from athena.core.gateway import Source
from athena.tools.base import CLIENT_PARAM, Tool, ToolContext, ToolResult


def get_owner(ctx: ToolContext, client: str) -> ToolResult:
    c = ctx.cfg.owner_map.clients[client]
    row: dict = {"client": c.name, "hub": c.hub}
    for role, email in c.roles.items():
        person = ctx.cfg.person(email)
        row[role] = f"{person.name} <{email}>" if person else email
    source = Source(name="owner_map", ref="context/owner_map.yaml", as_of=ctx.now)
    return ToolResult(name="get_owner", ok=True, client=client, records=[row], sources=[source])


TOOL = Tool(
    name="get_owner",
    description="Owners of a client: hub leader, DM/AM, CSM and BA.",
    parameters={"type": "object", "properties": {"client": CLIENT_PARAM}, "required": ["client"]},
    fn=get_owner,
)
