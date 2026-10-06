"""Wiring: build the config, database, gateway, sources, model and loops in one place."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from athena.connectors.registry import Sources
from athena.core.ask import Asker
from athena.core.config import AthenaConfig, load_config
from athena.core.db import Database, utcnow
from athena.core.gateway import Deliverer, Gateway
from athena.core.model import ModelClient, get_model


@dataclass
class App:
    cfg: AthenaConfig
    db: Database
    gateway: Gateway
    sources: Sources
    model: ModelClient
    clock: Callable[[], datetime]

    @property
    def asker(self) -> Asker:
        return Asker(self.cfg, self.db, self.gateway, self.sources, self.model)


def build(
    cfg: AthenaConfig | None = None,
    db: Database | None = None,
    clock: Callable[[], datetime] = utcnow,
    model: ModelClient | str | None = None,
    deliverer: Deliverer | None = None,
    run_mode: str | None = None,
) -> App:
    cfg = cfg or load_config()
    db = db or Database()
    gateway = Gateway(cfg, db, deliverer, clock)
    sources = Sources(cfg, clock=clock, run_mode=run_mode)
    model = model if model is not None and not isinstance(model, str) else get_model(cfg, model)
    return App(cfg=cfg, db=db, gateway=gateway, sources=sources, model=model, clock=clock)
