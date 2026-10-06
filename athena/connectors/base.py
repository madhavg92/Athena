"""Connector base: fixture/live switch, allowlisted fields, PHI scrub, source + as_of."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel

from athena.core import phi
from athena.core.config import AthenaConfig
from athena.core.db import utcnow

log = logging.getLogger(__name__)
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


class NotConfigured(Exception):
    """Live mode needs a gate that is not open yet (missing settings)."""


class Record(BaseModel):
    source: str  # e.g. "smartsheet.tasks"
    as_of: datetime  # UTC time of the data
    data: dict[str, Any]
    link: str | None = None
    suspect: bool = False  # PHI scrub masked something

    def get(self, field: str, default: Any = None) -> Any:
        return self.data.get(field, default)


def mode() -> str:
    value = os.environ.get("ATHENA_MODE", "fixture")
    if value not in ("fixture", "live"):
        raise ValueError(f"ATHENA_MODE must be fixture or live, not {value!r}")
    return value


def parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@lru_cache(maxsize=32)
def _fixture_file(path: str) -> Any:
    return json.loads(Path(path).read_text())


def fixture_anchor(fixtures: Path = FIXTURES) -> datetime:
    return parse_time(_fixture_file(str(fixtures / "meta.json"))["anchor"])


class Connector:
    """Subclasses set NAME and DATASETS and implement `_live`."""

    NAME: ClassVar[str]
    # dataset -> settings: file, allowed fields, free-text fields, time fields, link field, fixture as_of age
    DATASETS: ClassVar[dict[str, dict[str, Any]]]

    def __init__(
        self,
        cfg: AthenaConfig,
        clock: Callable[[], datetime] = utcnow,
        fixtures: Path = FIXTURES,
        run_mode: str | None = None,
        http: Any = None,
    ) -> None:
        self.cfg = cfg
        self.http = http  # a ReadOnlyClient; built lazily in live mode
        self.clock = clock
        self.fixtures = fixtures
        self.mode = run_mode or mode()

    def allowed_fields(self, dataset: str) -> set[str]:
        return set(self.DATASETS[dataset]["allowed"])

    def read(self, dataset: str, **filters: Any) -> list[Record]:
        if dataset not in self.DATASETS:
            raise KeyError(f"{self.NAME} has no dataset {dataset!r}")
        if self.mode == "live":
            rows, as_of = self._live(dataset, **filters)
        else:
            rows, as_of = self._fixture(dataset)
        records = [self._clean(dataset, row, as_of) for row in rows]
        return [
            r
            for r in records
            if all(_match(r.get(k), v) for k, v in filters.items() if v is not None)
        ]

    # ---- fixture mode ----

    def _fixture(self, dataset: str) -> tuple[list[dict], datetime]:
        spec = self.DATASETS[dataset]
        rows = _fixture_file(str(self.fixtures / spec["file"]))
        shift = self.clock() - fixture_anchor(self.fixtures)
        time_fields = set(spec.get("times", ())) | {"as_of"}
        date_fields = set(spec.get("dates", ()))
        out = []
        for row in rows:
            row = dict(row)
            for f in time_fields & row.keys():
                if row[f]:
                    row[f] = parse_time(row[f]) + shift
            for f in date_fields & row.keys():
                if row[f]:
                    row[f] = (
                        (datetime.fromisoformat(row[f]) + timedelta(days=shift.days))
                        .date()
                        .isoformat()
                    )
            out.append(row)
        as_of = self.clock() - timedelta(minutes=spec.get("fixture_age_minutes", 5))
        return out, as_of

    # ---- live mode ----

    def _live(self, dataset: str, **filters: Any) -> tuple[list[dict], datetime]:
        raise NotConfigured(f"{self.NAME} live mode is not built yet")

    def _env(self, *names: str) -> list[str]:
        values = [os.environ.get(n, "") for n in names]
        missing = [n for n, v in zip(names, values, strict=True) if not v]
        if missing:
            raise NotConfigured(
                f"{self.NAME}: missing settings {', '.join(missing)} (see docs/BLOCKERS.md)"
            )
        return values

    # ---- cleaning ----

    def _clean(self, dataset: str, row: dict[str, Any], default_as_of: datetime | None) -> Record:
        spec = self.DATASETS[dataset]
        allowed = set(spec["allowed"])
        dropped = set(row) - allowed - {"as_of"}
        if dropped:
            log.debug(
                "fields dropped", extra={"source": f"{self.NAME}.{dataset}", "count": len(dropped)}
            )
        data = {k: v for k, v in row.items() if k in allowed}
        suspect = False
        for f in spec.get("free_text", ()):
            if isinstance(data.get(f), str):
                result = phi.scrub(data[f], self.cfg.internal_domains)
                data[f] = result.text
                suspect = suspect or result.suspect
        for f in spec.get("times", ()):
            if f in data and data[f] is not None and not isinstance(data[f], datetime):
                data[f] = parse_time(data[f])
        as_of = parse_time(row.get("as_of")) or default_as_of or self.clock()
        link_field = spec.get("link")
        link = data.get(link_field) if link_field else None
        return Record(
            source=f"{self.NAME}.{dataset}", as_of=as_of, data=data, link=link, suspect=suspect
        )


def _match(value: Any, wanted: Any) -> bool:
    if isinstance(wanted, list | tuple | set):
        return value in wanted
    if isinstance(value, str) and isinstance(wanted, str):
        return value.lower() == wanted.lower()
    return value == wanted
