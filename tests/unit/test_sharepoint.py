import json

import httpx
import pytest

from athena.connectors.base import NotConfigured
from athena.connectors.http import ReadOnlyClient
from athena.connectors.sharepoint import SharePointConnector


def test_fixture_search(cfg) -> None:
    conn = SharePointConnector(cfg, run_mode="fixture")
    hits = conn.search("northwind_ortho", "escalation SOP")
    assert hits and hits[0].get("title").endswith("Escalation SOP")
    assert hits[0].link.startswith("https://example.sharepoint.com/sites/client-context")
    assert all(h.get("client") == "northwind_ortho" for h in hits)
    assert conn.search("northwind_ortho", "zebra") == []


def test_live_needs_user_token(cfg) -> None:
    with pytest.raises(NotConfigured, match="Teams SSO"):
        SharePointConnector(cfg, run_mode="live").search("northwind_ortho", "sow")


def test_live_search_restricted_to_allowlist(cfg) -> None:
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer obo-token"
        hits = [
            {
                "summary": "Scope <c0>charge</c0> entry",
                "resource": {
                    "name": "sow.docx",
                    "webUrl": "https://example.sharepoint.com/sites/client-context/a/sow.docx",
                    "lastModifiedDateTime": "2026-10-01T00:00:00Z",
                },
            },
            {
                "summary": "other",
                "resource": {
                    "name": "x.docx",
                    "webUrl": "https://example.sharepoint.com/sites/hr/x.docx",
                },
            },
        ]
        return httpx.Response(200, json={"value": [{"hitsContainers": [{"hits": hits}]}]})

    conn = SharePointConnector(
        cfg,
        run_mode="live",
        http=ReadOnlyClient(transport=httpx.MockTransport(handler)),
        token_provider=lambda assertion: "obo-token",
    )
    hits = conn.search("northwind_ortho", "charge entry", user_assertion="sso")
    query = sent[0]["requests"][0]["query"]["queryString"]
    assert 'path:"https://example.sharepoint.com/sites/client-context"' in query
    assert len(hits) == 1 and hits[0].get("snippet") == "Scope charge entry"
