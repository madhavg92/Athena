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
                "off_target",
                "metric_label",
            ],
            "dates": ["date"],
            "fixture_age_minutes": 180,
        },
        "claims": {
            "file": "supaboard/claims.json",
            "allowed": ["client", "date", "submitted", "denied", "paid", "query_id"],
            "dates": ["date"],
            "fixture_age_minutes": 180,
        },
        "denials": {
            "file": "supaboard/denials.json",
            "allowed": ["client", "date", "payer", "reason_code", "reason", "count"],
            "dates": ["date"],
            "fixture_age_minutes": 180,
        },
        "ar_aging": {
            "file": "supaboard/ar_aging.json",
            "allowed": [
                "client",
                "week_start",
                "0_30",
                "31_60",
                "61_90",
                "over_90",
                "total",
                "query_id",
            ],
            "dates": ["week_start"],
            "fixture_age_minutes": 180,
        },
        "denied_claims": {  # claim-level denials (no patient fields): amount, appeal deadline, status
            "file": "supaboard/denied_claims.json",
            "allowed": [
                "claim_id",
                "client",
                "payer",
                "reason_code",
                "reason",
                "denied_on",
                "amount_usd",
                "appeal_deadline",
                "status",
            ],
            "dates": ["denied_on", "appeal_deadline"],
            "fixture_age_minutes": 180,
        },
        "ar_over_90": {  # claims in the over-90-day AR bucket with their timely-filing deadline
            "file": "supaboard/ar_over_90.json",
            "allowed": [
                "claim_id",
                "client",
                "payer",
                "date_of_service",
                "amount_usd",
                "timely_filing_deadline",
                "last_touch",
            ],
            "dates": ["date_of_service", "timely_filing_deadline", "last_touch"],
            "fixture_age_minutes": 180,
        },
        "economics": {  # Anka's monthly fee revenue, FTE and cost per client
            "file": "supaboard/economics.json",
            "allowed": [
                "client",
                "month",
                "revenue_usd",
                "fte",
                "cost_usd",
                "fee_pct_of_collections",
                "query_id",
            ],
            "fixture_age_minutes": 180,
        },
        "workload": {  # daily inflow, work done and backlog by client and work type
            "file": "supaboard/workload.json",
            "allowed": [
                "date",
                "client",
                "work_type",
                "inflow",
                "completed",
                "backlog",
                "oldest_days",
                "tat_days",
                "per_fte_day",
                "query_id",
            ],
            "dates": ["date"],
            "fixture_age_minutes": 60,
        },
        "latest_metrics": {
            "file": "supaboard/metrics.json",
            "allowed": [],
        },  # latest per client + metric
    }

    def read(self, dataset: str, **filters: Any):
        if dataset == "latest_metrics":
            return latest(super().read("metrics", **filters))
        return super().read(dataset, **filters)

    def _fixture(self, dataset: str):
        rows, as_of = super()._fixture(dataset)
        if dataset != "metrics":
            return rows, as_of
        for row in rows:
            self._derive(row)
        return rows, None  # fixture rows carry their own as_of

    def _derive(self, row: dict) -> None:
        """Fields computed in code: client_metric key, and off_target using the metric's direction."""
        row["client_metric"] = f"{row['client']}:{row['metric']}"
        row["metric_label"] = row["metric"].replace("_", " ")
        metric = self.cfg.metrics.get(row["metric"])
        better = metric.better if metric else "higher"
        actual, target = row.get("actual"), row.get("target")
        if actual is None or target is None:
            row["off_target"] = None
        else:
            row["off_target"] = actual < target if better == "higher" else actual > target

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
