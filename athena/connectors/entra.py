"""Entra (Azure AD) users and managers. Live: Graph /users with app-only auth (G4)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from athena.connectors.base import Connector
from athena.connectors.http import ReadOnlyClient

USERS_URL = "https://graph.microsoft.com/v1.0/users"


class EntraConnector(Connector):
    NAME = "entra"
    DATASETS = {
        "users": {
            "file": "entra/users.json",
            "allowed": ["id", "email", "name", "job_title", "manager"],
        }
    }

    def __init__(
        self, *args: Any, token_provider: Callable[[], str] | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.token_provider = token_provider

    def _live(self, dataset: str, **_: Any):
        if self.token_provider is None:
            from athena.connectors.graph_auth import app_token

            self.token_provider = app_token
        token = self.token_provider()
        http = self.http or ReadOnlyClient()
        params: dict[str, Any] | None = {
            "$select": "id,mail,displayName,jobTitle",
            "$expand": "manager($select=mail)",
            "$top": "999",
        }
        url, rows = USERS_URL, []
        while url:
            data = http.get(url, params=params, headers={"Authorization": f"Bearer {token}"}).json()
            for u in data.get("value", []):
                if not u.get("mail"):
                    continue
                rows.append(
                    {
                        "id": u.get("id"),
                        "email": u["mail"].lower(),
                        "name": u.get("displayName"),
                        "job_title": u.get("jobTitle"),
                        "manager": ((u.get("manager") or {}).get("mail") or "").lower() or None,
                    }
                )
            url, params = data.get("@odata.nextLink"), None
        return rows, self.clock()
