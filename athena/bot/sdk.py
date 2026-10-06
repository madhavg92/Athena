"""Glue between Azure Functions and the Microsoft 365 Agents SDK (1.8.0). Needs `.[teams]`.

Settings (app settings, never in the repo), as the SDK reads them:
  CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID / __CLIENTSECRET / __TENANTID   (G6)
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from typing import Any

from microsoft_agents.activity import load_configuration_from_env
from microsoft_agents.authentication.msal import MsalConnectionManager
from microsoft_agents.hosting.aiohttp import CloudAdapter
from microsoft_agents.hosting.core import (
    AgentApplication,
    ClaimsIdentity,
    JwtTokenValidator,
    MemoryStorage,
    MessageFactory,
    TurnContext,
    TurnState,
)

from athena.bot.teams import Reply, TeamsBot


class FunctionsRequest:
    """Azure Functions HttpRequest -> the SDK's HttpRequestProtocol."""

    def __init__(
        self, method: str, headers: Mapping[str, str], body: bytes, claims: ClaimsIdentity | None
    ) -> None:
        self._method, self._headers, self._body, self._claims = method, dict(headers), body, claims

    @property
    def method(self) -> str:
        return self._method

    @property
    def headers(self) -> Mapping[str, str]:
        return self._headers

    async def json(self) -> dict[str, Any]:
        return json.loads(self._body or b"{}")

    def get_claims_identity(self) -> ClaimsIdentity | None:
        return self._claims

    def get_path_param(self, name: str) -> str:
        return ""


def reply_activity(reply: Reply):
    if reply.card is not None:
        from microsoft_agents.hosting.core import CardFactory

        return MessageFactory.attachment(CardFactory.adaptive_card(reply.card))
    return MessageFactory.text(reply.text)


class BotHost:
    def __init__(self, bot: TeamsBot, env: Mapping[str, str] | None = None) -> None:
        config = load_configuration_from_env(env or os.environ)
        self.storage = MemoryStorage()
        self.connections = MsalConnectionManager(**config)
        self.adapter = CloudAdapter(connection_manager=self.connections)
        self.agent = AgentApplication[TurnState](
            storage=self.storage, connection_manager=self.connections, **config
        )
        self.auth_config = self.connections.get_default_connection_configuration()
        self.bot = bot

        @self.agent.activity("message")
        async def on_message(context: TurnContext, state: TurnState) -> None:
            act = context.activity
            sender = act.from_property
            reply = await asyncio.to_thread(
                self.bot.handle_message,
                act.text or "",
                getattr(sender, "aad_object_id", None),
                None,  # UPN is not sent in the activity; Entra maps the object ID
                act.conversation.id,
            )
            await context.send_activity(reply_activity(reply))

    async def process(
        self, method: str, headers: Mapping[str, str], body: bytes
    ) -> tuple[int, dict | None]:
        auth = headers.get("Authorization") or headers.get("authorization") or ""
        parts = auth.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return 401, {"error": "unauthorized"}
        try:
            claims = await JwtTokenValidator(self.auth_config).validate_token(parts[1])
        except Exception:  # invalid token: never echo details
            return 401, {"error": "unauthorized"}
        response = await self.adapter.process_request(
            FunctionsRequest(method, headers, body, claims), self.agent
        )
        return response.status_code, response.body
