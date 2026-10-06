from athena.core import phi
from athena.core.gateway import Source
from athena.tools.base import CLIENT_PARAM, Tool, ToolContext, ToolResult


def get_client_profile(ctx: ToolContext, client: str) -> ToolResult:
    path = ctx.cfg.root / "context" / "clients" / f"{client}.md"
    if not path.exists():
        return ToolResult(name="get_client_profile", ok=True, client=client, records=[])
    text = phi.scrub(path.read_text(), ctx.cfg.internal_domains).text
    source = Source(name="client_profile", ref=f"context/clients/{client}.md", as_of=ctx.now)
    return ToolResult(
        name="get_client_profile",
        ok=True,
        client=client,
        records=[{"profile": text}],
        sources=[source],
    )


TOOL = Tool(
    name="get_client_profile",
    description="The client profile file: specialty, services, turnaround, meeting rhythm and watch items.",
    parameters={"type": "object", "properties": {"client": CLIENT_PARAM}, "required": ["client"]},
    fn=get_client_profile,
)
