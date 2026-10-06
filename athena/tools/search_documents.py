from athena.connectors.sharepoint import SharePointConnector
from athena.tools.base import (
    CLIENT_PARAM,
    Tool,
    ToolContext,
    ToolResult,
    is_stale,
    sources_of,
    to_model_rows,
)


def search_documents(ctx: ToolContext, client: str, words: str) -> ToolResult:
    conn = ctx.sources.connector("sharepoint")
    assert isinstance(conn, SharePointConnector)
    persona = ctx.cfg.persona_of(ctx.actor)
    group = persona.sharepoint_sites if persona else "client_context"
    hits = conn.search(client, words, site_group=group, user_assertion=ctx.user_assertion)
    rows = to_model_rows(hits, ["title", "snippet", "url", "modified"], ctx.tz)
    sources = sources_of(hits)
    return ToolResult(
        name="search_documents",
        ok=True,
        client=client,
        records=rows,
        sources=sources,
        stale=is_stale(ctx, sources),
    )


TOOL = Tool(
    name="search_documents",
    description="Search allowlisted SharePoint sites for a client. Returns up to 5 short snippets with links.",
    parameters={
        "type": "object",
        "properties": {
            "client": CLIENT_PARAM,
            "words": {"type": "string", "description": "Search words."},
        },
        "required": ["client", "words"],
    },
    fn=search_documents,
)
