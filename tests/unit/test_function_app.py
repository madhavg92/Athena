import asyncio
import importlib

import pytest

pytest.importorskip("azure.functions")
pytest.importorskip("microsoft_agents.hosting.core")

ENV = {
    "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID": "00000000-0000-0000-0000-000000000001",
    "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET": "fixture-secret",
    "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID": "00000000-0000-0000-0000-000000000002",
}


def test_function_app_registers_timer_and_http() -> None:
    fa = importlib.import_module("function_app")
    names = {f.get_function_name() for f in fa.app.get_functions()}
    assert {"tick", "messages"} <= names


def test_timer_runs_tick(monkeypatch, app) -> None:
    fa = importlib.import_module("function_app")
    monkeypatch.setitem(fa._state, "app", app)
    fa.tick(None)  # no held messages: nothing to send, no error


def test_bot_host_rejects_missing_or_bad_token(app) -> None:
    from athena.bot.sdk import BotHost
    from athena.bot.teams import TeamsBot

    host = BotHost(TeamsBot(app), env=ENV)
    status, body = asyncio.run(host.process("POST", {}, b"{}"))
    assert status == 401 and body == {"error": "unauthorized"}
    status, _ = asyncio.run(host.process("POST", {"Authorization": "Bearer not-a-jwt"}, b"{}"))
    assert status == 401
