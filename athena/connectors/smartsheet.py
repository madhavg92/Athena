"""Smartsheet connector (tasks). Live: Smartsheet API 2.0, read only (gate G1)."""

from __future__ import annotations

from typing import Any

from athena.connectors.base import Connector, NotConfigured
from athena.connectors.http import ReadOnlyClient

API = "https://api.smartsheet.com/2.0"


class SmartsheetConnector(Connector):
    NAME = "smartsheet"
    DATASETS = {
        "tasks": {
            "file": "smartsheet/tasks.json",
            "allowed": [
                "task_id",
                "client",
                "title",
                "owner",
                "due",
                "status",
                "last_update",
                "sheet_id",
                "row_id",
                "link",
            ],
            "free_text": ["title"],
            "times": ["due", "last_update"],
            "link": "link",
        },
        "task_history": {  # row history of the task sheets (live: Smartsheet cell history, G1)
            "file": "smartsheet/task_history.json",
            "allowed": ["task_id", "client", "time", "change", "old", "new", "by"],
            "times": ["time"],
            "maybe_times": ["old", "new"],
        },
        "team": {  # the resource sheet: who works on each client (live: G1)
            "file": "smartsheet/team.json",
            "allowed": [
                "client",
                "member",
                "role",
                "fte",
                "on_leave_today",
                "leave_until",
                "open_items",
                "utilisation_pct",
                "also_trained",
                "signed_off",
                "sign_off_due",
                "on_notice_until",
            ],
            "dates": ["leave_until", "sign_off_due", "on_notice_until"],
        },
        "attendance": {  # today's roster: who logged in, planned leave, unplanned absence (live: G1)
            "file": "smartsheet/attendance.json",
            "allowed": ["date", "client", "member", "role", "status", "logged_in_at"],
            "dates": ["date"],
            "times": ["logged_in_at"],
        },
        "blockers": {  # the hub's blocked-work log: logins, waiting on client, clearinghouse (live: G1)
            "file": "smartsheet/blockers.json",
            "allowed": [
                "blocker_id",
                "client",
                "kind",
                "summary",
                "waiting_on",
                "people_blocked",
                "items_held",
                "amount_usd",
                "opened_at",
                "expires_at",
                "due",
                "status",
                "closed_at",
                "owner",
            ],
            "free_text": ["summary"],
            "times": ["opened_at", "expires_at", "due", "closed_at"],
        },
        "quality": {  # audit findings: internal audits and errors the client found (live: G1)
            "file": "smartsheet/quality.json",
            "allowed": [
                "finding_id",
                "client",
                "found_by",
                "summary",
                "severity",
                "opened_at",
                "due",
                "status",
                "closed_at",
                "owner",
            ],
            "free_text": ["summary"],
            "times": ["opened_at", "due", "closed_at"],
        },
    }

    def _fixture(self, dataset: str):
        rows, as_of = super()._fixture(dataset)
        if dataset != "tasks":
            return rows, as_of
        for row in rows:
            row["link"] = (
                f"https://app.smartsheet.com/sheets/{row['sheet_id']}?rowId={row['row_id']}"
            )
        return rows, as_of

    def _client(self) -> ReadOnlyClient:
        if self.http is None:
            (token,) = self._env("SMARTSHEET_TOKEN")
            self.http = ReadOnlyClient(API, headers={"Authorization": f"Bearer {token}"})
        return self.http

    def _live(self, dataset: str, client: str | None = None, **_: Any):
        if dataset != "tasks":
            raise NotConfigured(
                f"smartsheet.{dataset}: live reader not built yet; needs the sheet layout (G1)"
            )
        sheets = self.cfg.smartsheet_map.sheets
        if not sheets:
            raise NotConfigured("smartsheet: no sheet IDs in context/smartsheet_map.yaml (G1)")
        cols = self.cfg.smartsheet_map.columns
        http = self._client()
        rows: list[dict] = []
        for key, sheet_id in sheets.items():
            if client and key != client:
                continue
            sheet = http.get(f"{API}/sheets/{sheet_id}", params={"include": "rowPermalink"}).json()
            by_id = {c["id"]: c["title"] for c in sheet.get("columns", [])}
            wanted = {
                cols.task: "title",
                cols.owner: "owner",
                cols.due: "due",
                cols.status: "status",
                cols.last_update: "last_update",
            }
            missing = [title for title in wanted if title not in by_id.values()]
            if missing:
                raise NotConfigured(
                    f"smartsheet: sheet for {key} has no column(s) {', '.join(missing)} (G1)"
                )
            for r in sheet.get("rows", []):
                row: dict[str, Any] = {
                    "client": key,
                    "sheet_id": sheet_id,
                    "row_id": r["id"],
                    "task_id": str(r["id"]),
                }
                for cell in r.get("cells", []):
                    title = by_id.get(cell.get("columnId"))
                    if title in wanted:
                        value = cell.get("value")
                        if isinstance(value, dict):  # contact cells
                            value = value.get("email") or value.get("name")
                        row[wanted[title]] = value
                if not row.get("last_update"):
                    row["last_update"] = r.get("modifiedAt")
                row["link"] = r.get("permalink")
                rows.append(row)
        return rows, self.clock()
