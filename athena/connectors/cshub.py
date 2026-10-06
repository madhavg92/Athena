"""CS Hub connector (tickets, health). Live API waits for gate G3.

Live interface (to implement when G3 gives read access):
    GET {CSHUB_BASE_URL}/tickets?client=<key>&status=<status>
    GET {CSHUB_BASE_URL}/health?client=<key>
"""

from __future__ import annotations

from typing import Any

from athena.connectors.base import Connector, NotConfigured


class CSHubConnector(Connector):
    NAME = "cs_hub"
    DATASETS = {
        "tickets": {
            "file": "cshub/tickets.json",
            "allowed": [
                "ticket_id",
                "client",
                "subject",
                "status",
                "priority",
                "opened_at",
                "last_reply_at",
                "assignee",
            ],
            "free_text": ["subject"],
            "times": ["opened_at", "last_reply_at"],
            "fixture_age_minutes": 10,
        },
        "activity": {  # meetings, escalations, commitments and notes (no email or chat content)
            "file": "cshub/activity.json",
            "allowed": ["client", "time", "type", "summary", "owner"],
            "free_text": ["summary"],
            "times": ["time"],
        },
        "health": {
            "file": "cshub/health.json",
            "allowed": ["client", "health_score", "trend"],
        },
    }

    def _live(self, dataset: str, **filters: Any):
        self._env("CSHUB_BASE_URL", "CSHUB_API_KEY")
        raise NotConfigured("cs_hub: live API not implemented; waiting for read access (G3)")
