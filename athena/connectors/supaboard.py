"""Supaboard / Intelligence connector (metrics). Live API waits for gate G2.

Live interface (to implement when G2 gives the API documents):
    GET {SUPABOARD_BASE_URL}/metrics?client=<key>&metric=<name>&from=<date>&to=<date>
    -> rows: client, metric, date, actual, target, query_id; response time = as_of
"""

from __future__ import annotations

from typing import Any

from athena.connectors.base import Connector, NotConfigured


class SupaboardConnector(Connector):
    NAME = "supaboard"
    DATASETS = {
        "metrics": {
            "file": "supaboard/metrics.json",
            "allowed": [
                "client",
                "metric",
                "date",
                "actual",
                "target",
                "query_id",
                "client_metric",
            ],
            "dates": ["date"],
            "fixture_age_minutes": 180,
        }
    }

    def _fixture(self, dataset: str):
        rows, _ = super()._fixture(dataset)
        for row in rows:
            row["client_metric"] = f"{row['client']}:{row['metric']}"
        return rows, None  # fixture rows carry their own as_of

    def _live(self, dataset: str, **filters: Any):
        self._env("SUPABOARD_BASE_URL", "SUPABOARD_API_KEY")
        raise NotConfigured("supaboard: live API not implemented; waiting for API documents (G2)")


def latest(records):
    """Latest record for each client + metric."""
    best = {}
    for r in records:
        key = (r.get("client"), r.get("metric"))
        if key not in best or r.get("date") > best[key].get("date"):
            best[key] = r
    return list(best.values())
