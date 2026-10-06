"""All connectors by name, and reading a source such as `smartsheet.tasks`."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from athena.connectors.base import Connector, Record
from athena.connectors.cshub import CSHubConnector
from athena.connectors.entra import EntraConnector
from athena.connectors.sharepoint import SharePointConnector
from athena.connectors.smartsheet import SmartsheetConnector
from athena.connectors.supaboard import SupaboardConnector
from athena.core.config import AthenaConfig
from athena.core.db import utcnow

CONNECTORS: dict[str, type[Connector]] = {
    c.NAME: c
    for c in (
        SmartsheetConnector,
        SupaboardConnector,
        CSHubConnector,
        SharePointConnector,
        EntraConnector,
    )
}


class Sources:
    """One connector instance per source for a run (shared clock and mode)."""

    def __init__(
        self,
        cfg: AthenaConfig,
        clock: Callable[[], datetime] = utcnow,
        run_mode: str | None = None,
        data_clock: Callable[[], datetime] | None = None,
        **kw: Any,
    ):
        self.cfg, self.clock, self.run_mode, self.kw = cfg, clock, run_mode, kw
        self.data_clock = data_clock
        self._cache: dict[str, Connector] = {}

    def connector(self, name: str) -> Connector:
        if name not in CONNECTORS:
            raise KeyError(f"unknown connector {name!r}; known: {', '.join(CONNECTORS)}")
        if name not in self._cache:
            self._cache[name] = CONNECTORS[name](
                self.cfg,
                clock=self.clock,
                run_mode=self.run_mode,
                data_clock=self.data_clock,
                **self.kw.get(name, {}),
            )
        return self._cache[name]

    def read(self, source: str, **filters: Any) -> list[Record]:
        name, _, dataset = source.partition(".")
        return self.connector(name).read(dataset, **filters)
