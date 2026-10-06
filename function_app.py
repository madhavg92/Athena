"""Azure Functions entry point (Python v2 programming model).

- Timer every 15 minutes -> scheduler.tick()
- HTTP POST /api/messages -> Teams bot -> ask loop
The user deploys this (see docs/RUNBOOK.md). Settings come from app settings, never from the repo.
"""

from __future__ import annotations

import json
import logging

import azure.functions as func

from athena.app import build
from athena.bot.teams import TeamsBot
from athena.core import scheduler

app = func.FunctionApp(
    http_auth_level=func.AuthLevel.ANONYMOUS
)  # the bot validates the Bot Framework JWT
_state: dict = {}


def _athena():
    if "app" not in _state:
        _state["app"] = build()
    return _state["app"]


def _host():
    if "host" not in _state:
        from athena.bot.sdk import BotHost

        _state["host"] = BotHost(TeamsBot(_athena()))
    return _state["host"]


@app.timer_trigger(
    schedule="0 */15 * * * *", arg_name="timer", run_on_startup=False, use_monitor=True
)
def tick(timer: func.TimerRequest) -> None:
    result = scheduler.tick(_athena())
    logging.info("athena tick", extra=result)


@app.route(route="messages", methods=["POST"])
async def messages(req: func.HttpRequest) -> func.HttpResponse:
    status, body = await _host().process(req.method, dict(req.headers), req.get_body())
    return func.HttpResponse(
        body=json.dumps(body) if body is not None else None,
        status_code=status,
        mimetype="application/json",
    )
