"""SharePoint document search. Live: Graph /search/query on allowlisted sites, delegated auth (G4).

Delegated auth (Teams SSO + on-behalf-of) is used so results are trimmed to what the user may see.
App-only auth would not trim by user, so it is not used here.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from athena.connectors.base import Connector, NotConfigured, Record
from athena.connectors.http import ReadOnlyClient

SEARCH_URL = "https://graph.microsoft.com/v1.0/search/query"
MAX_RESULTS = 5
SNIPPET_CHARS = 300


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2]


class SharePointConnector(Connector):
    NAME = "sharepoint"
    DATASETS = {
        "documents": {
            "file": "sharepoint/documents.json",
            "allowed": ["client", "title", "snippet", "url", "modified"],
            "free_text": ["title", "snippet"],
            "times": ["modified"],
            "link": "url",
            "fixture_age_minutes": 1,
        }
    }

    def __init__(
        self, *args: Any, token_provider: Callable[[str], str] | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.token_provider = token_provider

    def sites(self, group: str) -> list[str]:
        return self.cfg.allowlist.sharepoint_sites.get(group, [])

    def search(
        self,
        client: str,
        words: str,
        site_group: str = "client_context",
        user_assertion: str | None = None,
    ) -> list[Record]:
        if self.mode == "live":
            rows = self._live_search(client, words, site_group, user_assertion)
            records = [self._clean("documents", row, self.clock()) for row in rows]
            return records[:MAX_RESULTS]
        wanted = set(_words(words))
        scored = []
        for rec in self.read("documents", client=client):
            have = set(_words(f"{rec.get('title')} {rec.get('snippet')}"))
            score = len(wanted & have)
            if score:
                scored.append((score, rec))
        scored.sort(key=lambda x: -x[0])
        return [r for _, r in scored[:MAX_RESULTS]]

    def _live_search(
        self, client: str, words: str, site_group: str, user_assertion: str | None
    ) -> list[dict]:
        sites = self.sites(site_group)
        if not sites:
            raise NotConfigured(f"sharepoint: no allowlisted sites for {site_group!r} (G4)")
        if not user_assertion:
            raise NotConfigured(
                "sharepoint: delegated search needs the user's Teams SSO token (G4)"
            )
        if self.token_provider is None:
            from athena.connectors.graph_auth import delegated_token

            self.token_provider = delegated_token
        token = self.token_provider(user_assertion)
        http = self.http or ReadOnlyClient()
        name = self.cfg.owner_map.clients[client].name
        paths = " OR ".join(f'path:"{s}"' for s in sites)
        clean = " ".join(_words(words)) or "*"
        body = {
            "requests": [
                {
                    "entityTypes": ["driveItem", "listItem"],
                    "query": {"queryString": f'{clean} "{name}" ({paths})'},
                    "from": 0,
                    "size": MAX_RESULTS,
                    "fields": ["name", "webUrl", "lastModifiedDateTime"],
                }
            ]
        }
        data = http.post(SEARCH_URL, json=body, headers={"Authorization": f"Bearer {token}"}).json()
        rows = []
        for container in data.get("value", []):
            for hits in container.get("hitsContainers", []):
                for hit in hits.get("hits", []):
                    res = hit.get("resource", {})
                    url = res.get("webUrl", "")
                    if not any(url.lower().startswith(s.lower()) for s in sites):
                        continue  # defence in depth: never return a non-allowlisted site
                    rows.append(
                        {
                            "client": client,
                            "title": res.get("name", ""),
                            "snippet": re.sub(r"<[^>]+>", "", hit.get("summary", ""))[
                                :SNIPPET_CHARS
                            ],
                            "url": url,
                            "modified": res.get("lastModifiedDateTime"),
                        }
                    )
        return rows
