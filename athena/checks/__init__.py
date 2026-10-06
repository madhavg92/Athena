"""Check types. Code decides; no eval, no expression strings."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Hit(BaseModel):
    key: str
    severity: str
    client: str | None = None
    fields: dict[str, Any] = {}
