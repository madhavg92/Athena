"""Microsoft Graph tokens via MSAL (gate G4). Token calls go only to the Entra token endpoint."""

from __future__ import annotations

import os

from athena.connectors.base import NotConfigured

GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]


def _app():
    import msal

    tenant, client_id, secret = (
        os.environ.get(n, "") for n in ("GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET")
    )
    if not (tenant and client_id and secret):
        raise NotConfigured(
            "graph: missing GRAPH_TENANT_ID / GRAPH_CLIENT_ID / GRAPH_CLIENT_SECRET (G4)"
        )
    return msal.ConfidentialClientApplication(
        client_id, authority=f"https://login.microsoftonline.com/{tenant}", client_credential=secret
    )


def _token(result: dict) -> str:
    if "access_token" not in result:
        raise NotConfigured(f"graph: token request failed: {result.get('error', 'unknown')} (G4)")
    return result["access_token"]


def app_token() -> str:
    """App-only token (client credentials). Used for Entra users; not for document search."""
    return _token(_app().acquire_token_for_client(scopes=GRAPH_SCOPE))


def delegated_token(user_assertion: str) -> str:
    """On-behalf-of token from the user's Teams SSO token, so search is trimmed to the user."""
    return _token(_app().acquire_token_on_behalf_of(user_assertion, scopes=GRAPH_SCOPE))
