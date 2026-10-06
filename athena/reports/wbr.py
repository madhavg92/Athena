"""Weekly client report builder (R5). Built in M8.1."""

from __future__ import annotations

from athena.app import App
from athena.core.config import Rule


def run_rule(app: App, rule: Rule):
    from athena.core.scheduler import RuleRun

    return RuleRun(rule_id=rule.id, ran=False, reason="report builder not built yet")
