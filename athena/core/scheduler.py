"""Scheduler tick. Runs every 15 minutes (Azure Functions timer, or `athena tick`)."""

from __future__ import annotations

import logging

from athena.app import App

log = logging.getLogger(__name__)


def tick(app: App) -> dict[str, int]:
    """Release held messages. The rule loop is added in M6.2."""
    released = app.gateway.release_held()
    log.info("tick", extra={"released": released})
    return {"released": released}
