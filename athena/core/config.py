"""Config models and loader. All YAML config is validated here at startup."""

from __future__ import annotations

import os
import re
from datetime import time
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from athena.core.durations import Duration

THRESHOLD_OPS = {
    "eq", "ne", "lt", "lte", "gt", "gte",
    "lt_field", "gt_field",
    "before", "after", "within", "older_than",
    "is_null", "not_null",
}  # fmt: skip

ActionType = Literal["answer", "notify", "draft", "write"]
Delivery = Literal["now", "digest"]
Mode = Literal["shadow", "live"]


class ConfigError(Exception):
    """A config file is invalid. The message names the file, the field and the reason."""


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_tz(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown time zone {value!r}") from exc
    return value


# ---------- rules ----------


class CronTrigger(Strict):
    cron: str
    tz: str = "Asia/Kolkata"

    @field_validator("cron")
    @classmethod
    def _cron(cls, value: str) -> str:
        if len(value.split()) != 5 or not croniter.is_valid(value):
            raise ValueError(f"invalid 5-field cron {value!r}")
        return value

    _tz = field_validator("tz")(classmethod(lambda cls, v: _check_tz(v)))


class QuestionTrigger(Strict):
    question: Literal["any", "brief"]


class Condition(Strict):
    field: str
    op: str
    value: Any = None

    @field_validator("op")
    @classmethod
    def _op(cls, value: str) -> str:
        if value not in THRESHOLD_OPS:
            raise ValueError(f"unknown op {value!r}; allowed: {', '.join(sorted(THRESHOLD_OPS))}")
        return value


class ThresholdCheck(Strict):
    type: Literal["threshold"]
    key: str
    severities: dict[str, list[Condition]] = Field(min_length=1)


class CalendarExpected(Strict):
    cron: str
    key: str
    tz: str = "Asia/Kolkata"


class AbsenceCheck(Strict):
    type: Literal["absence"]
    key: str = "item_key"
    expected: list[dict[str, Any]] | CalendarExpected
    arrived_source: str
    match_key: str
    grace: Duration
    severity: str = "missing"


Check = Annotated[ThresholdCheck | AbsenceCheck, Field(discriminator="type")]


class LadderStep(Strict):
    after: Duration
    to: str


class MessageSpec(Strict):
    writer: Literal["model", "template"] = "template"
    template: str


class BuilderSpec(Strict):
    type: Literal["wbr"]
    template: str
    period: Literal["last_week"] = "last_week"


class Rule(Strict):
    id: str
    name: str
    trigger: CronTrigger | QuestionTrigger
    action: ActionType
    source: str | None = None
    check: Check | None = None
    data_max_age: Duration
    owner: str | None = None
    ladder: list[LadderStep] = []
    renudge_after: Duration | None = None
    close_when: dict[str, Any] | None = None
    message: MessageSpec | None = None
    delivery: Delivery = "digest"
    phase: Literal[1, 2, 3] = 1
    mode: Mode = "shadow"
    max_wrong_rate: float | None = Field(default=None, ge=0, le=1)
    # ask rules
    tools: list[str] = []
    max_tool_calls: int = Field(default=8, ge=1, le=8)
    template: str | None = None
    sections: list[str] = []
    # digest rules
    include_open_alerts: list[str] = []
    include_standing: bool = False  # start the digest with the standing list items that need you
    empty_message: str | None = None
    # draft rules
    clients: list[str] = []
    builder: BuilderSpec | None = None
    notify: str | None = None

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        if not re.fullmatch(r"R\d+", value):
            raise ValueError(f"rule id {value!r} must look like R<number>")
        return value

    @field_validator("action")
    @classmethod
    def _action(cls, value: str) -> str:
        if value == "write":
            raise ValueError("action 'write' is disabled in releases 1 and 2")
        return value

    @model_validator(mode="after")
    def _shape(self) -> Rule:
        if isinstance(self.trigger, CronTrigger) and self.action == "notify":
            if self.source is None or self.check is None:
                raise ValueError("a scheduled notify rule needs 'source' and 'check'")
            if not self.ladder:
                raise ValueError("a scheduled notify rule needs a 'ladder'")
        if self.action == "draft" and self.builder is None:
            raise ValueError("a draft rule needs a 'builder'")
        return self

    @property
    def is_question(self) -> bool:
        return isinstance(self.trigger, QuestionTrigger)


# ---------- personas and people ----------

_SCOPE = re.compile(r"^clients where (\w+) = me$")
_HOURS = re.compile(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$")


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


class WorkHours(BaseModel):
    start: time
    end: time

    @classmethod
    def parse(cls, value: str) -> WorkHours:
        match = _HOURS.match(value)
        if not match:
            raise ValueError(f"invalid work_hours {value!r}; use HH:MM-HH:MM")
        h1, m1, h2, m2 = (int(x) for x in match.groups())
        return cls(start=time(h1, m1), end=time(h2, m2))

    def contains(self, moment: time) -> bool:
        if self.start <= self.end:
            return self.start <= moment < self.end
        return moment >= self.start or moment < self.end  # wraps midnight


class Persona(Strict):
    persona: str
    scope: str
    rules: list[str]
    sources: list[str]
    sharepoint_sites: str
    work_hours: str
    digest_time: str
    tz: str = "Asia/Kolkata"
    must_not: list[str] = []

    @field_validator("scope")
    @classmethod
    def _scope(cls, value: str) -> str:
        if not _SCOPE.match(value):
            raise ValueError(f"scope {value!r} must look like 'clients where <role> = me'")
        return value

    @field_validator("work_hours")
    @classmethod
    def _hours(cls, value: str) -> str:
        WorkHours.parse(value)
        return value

    @field_validator("digest_time")
    @classmethod
    def _digest(cls, value: str) -> str:
        if not re.fullmatch(r"\d{2}:\d{2}", value):
            raise ValueError(f"invalid digest_time {value!r}; use HH:MM")
        return value

    _tz = field_validator("tz")(classmethod(lambda cls, v: _check_tz(v)))

    @property
    def scope_role(self) -> str:
        match = _SCOPE.match(self.scope)
        assert match
        return match.group(1)


class Person(Strict):
    name: str
    persona: str
    work_hours: str | None = None
    tz: str | None = None


class Client(BaseModel):
    """A client. Fixed fields plus one email for each owner-map role (hub_leader, dm_am, ...)."""

    model_config = ConfigDict(extra="allow")
    name: str
    hub: str

    def role(self, role: str) -> str | None:
        value = (self.model_extra or {}).get(role)
        return value if isinstance(value, str) else None

    @property
    def roles(self) -> dict[str, str]:
        return {k: v for k, v in (self.model_extra or {}).items() if isinstance(v, str)}


class OwnerMap(Strict):
    people: dict[str, Person]
    clients: dict[str, Client]


class Allowlist(Strict):
    sharepoint_sites: dict[str, list[str]]
    internal_email_domains: list[str]


class Metric(Strict):
    meaning: str
    source: str
    field: str
    owner: str
    better: Literal["higher", "lower"] = "higher"


class ModelSpec(Strict):
    kind: Literal["stub", "openai_compatible"]
    base_url_env: str | None = None
    api_key_env: str | None = None
    model: str | None = None
    price_per_mtok_in: float = 0.0
    price_per_mtok_out: float = 0.0
    contract_covers_data: Literal["yes", "no", "unknown"] = "unknown"


class Models(Strict):
    default: str
    models: dict[str, ModelSpec]

    @model_validator(mode="after")
    def _default(self) -> Models:
        if self.default not in self.models:
            raise ValueError(f"default model {self.default!r} is not in 'models'")
        return self


class SmartsheetColumns(Strict):
    task: str
    owner: str
    due: str
    status: str
    last_update: str


class SmartsheetMap(Strict):
    columns: SmartsheetColumns
    sheets: dict[str, int]


# ---------- loader ----------


class AthenaConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    root: Path
    rules: dict[str, Rule]
    personas: dict[str, Persona]
    owner_map: OwnerMap
    allowlist: Allowlist
    metrics: dict[str, Metric]
    models: Models
    smartsheet_map: SmartsheetMap
    glossary: dict[str, str]

    @property
    def internal_domains(self) -> list[str]:
        env = os.environ.get("INTERNAL_EMAIL_DOMAINS")
        if os.environ.get("ATHENA_MODE") == "live" and env:
            return [d.strip().lower() for d in env.split(",") if d.strip()]
        return [d.lower() for d in self.allowlist.internal_email_domains]

    def person(self, email: str) -> Person | None:
        return self.owner_map.people.get(email.lower())

    def persona_of(self, email: str) -> Persona | None:
        person = self.person(email)
        return self.personas.get(person.persona) if person else None

    def scope_of(self, email: str) -> list[str]:
        """Client keys in the scope of a person."""
        persona = self.persona_of(email)
        if persona is None:
            return []
        role = persona.scope_role
        email = email.lower()
        return [
            key
            for key, c in self.owner_map.clients.items()
            if (c.role(role) or "").lower() == email
        ]

    def work_hours_of(self, email: str) -> tuple[WorkHours, str]:
        person = self.person(email)
        persona = self.persona_of(email)
        hours = (person.work_hours if person else None) or (
            persona.work_hours if persona else "00:00-23:59"
        )
        tz = (person.tz if person else None) or (
            persona.tz if persona else os.environ.get("DEFAULT_TZ", "Asia/Kolkata")
        )
        return WorkHours.parse(hours), tz

    def client_by_name(self, text: str) -> str | None:
        """Find a client key mentioned in free text by key or name."""
        low = text.lower()
        for key, client in self.owner_map.clients.items():
            if client.name.lower() in low or key.lower() in low:
                return key
        return None


def _fmt_error(path: str, exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"] if not str(p).startswith("function-"))
        lines.append(f"{path}: {loc or '(root)'}: {err['msg']}")
    return "\n".join(lines)


def _read_yaml(root: Path, rel: str) -> Any:
    path = root / rel
    if not path.exists():
        raise ConfigError(f"{rel}: (file): file not found")
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{rel}: (file): invalid YAML: {exc}") from exc


def _parse(model: type[BaseModel], data: Any, rel: str) -> Any:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_fmt_error(rel, exc)) from exc


def default_root() -> Path:
    env = os.environ.get("ATHENA_HOME")
    if env:
        return Path(env)
    here = Path.cwd()
    for candidate in (here, *here.parents):
        if (candidate / "rules").is_dir() and (candidate / "context").is_dir():
            return candidate
    return Path(__file__).resolve().parents[2]


def load_config(root: Path | None = None) -> AthenaConfig:
    root = Path(root) if root else default_root()
    errors: list[str] = []

    def guarded(fn):  # collect all errors, not only the first
        try:
            return fn()
        except ConfigError as exc:
            errors.append(str(exc))
            return None

    rules: dict[str, Rule] = {}
    for path in sorted((root / "rules").glob("*.yaml")):
        rel = f"rules/{path.name}"
        rule = guarded(lambda rel=rel: _parse(Rule, _read_yaml(root, rel), rel))
        if rule is None:
            continue
        if rule.id != path.stem:
            errors.append(f"{rel}: id: rule id {rule.id!r} does not match the file name")
        rules[rule.id] = rule

    personas: dict[str, Persona] = {}
    for path in sorted((root / "personas").glob("*.yaml")):
        rel = f"personas/{path.name}"
        persona = guarded(lambda rel=rel: _parse(Persona, _read_yaml(root, rel), rel))
        if persona is not None:
            personas[persona.persona] = persona

    def single(model, rel):
        return guarded(lambda: _parse(model, _read_yaml(root, rel), rel))

    owner_map = single(OwnerMap, "context/owner_map.yaml")
    allowlist = single(Allowlist, "context/allowlist.yaml")
    models = single(Models, "context/models.yaml")
    smartsheet_map = single(SmartsheetMap, "context/smartsheet_map.yaml")
    metrics_raw = guarded(lambda: _read_yaml(root, "context/metrics.yaml")) or {}
    metrics = {}
    for name, data in metrics_raw.items():
        metric = guarded(lambda d=data, n=name: _parse(Metric, d, f"context/metrics.yaml#{n}"))
        if metric is not None:
            metrics[name] = metric
    glossary = guarded(lambda: _read_yaml(root, "context/glossary.yaml")) or {}

    if errors:
        raise ConfigError("\n".join(errors))

    cfg = AthenaConfig(
        root=root,
        rules=rules,
        personas=personas,
        owner_map=owner_map,
        allowlist=allowlist,
        metrics=metrics,
        models=models,
        smartsheet_map=smartsheet_map,
        glossary={str(k): str(v) for k, v in glossary.items()},
    )
    _cross_check(cfg)
    return cfg


def _cross_check(cfg: AthenaConfig) -> None:
    errors: list[str] = []
    people = cfg.owner_map.people
    for email, person in people.items():
        if email != email.lower():
            errors.append(f"context/owner_map.yaml: people.{email}: emails must be lower case")
        if person.persona not in cfg.personas:
            errors.append(
                f"context/owner_map.yaml: people.{email}.persona: unknown persona {person.persona!r}"
            )
        if person.work_hours:
            try:
                WorkHours.parse(person.work_hours)
            except ValueError as exc:
                errors.append(f"context/owner_map.yaml: people.{email}.work_hours: {exc}")
    for key, client in cfg.owner_map.clients.items():
        for role, email in client.roles.items():
            if email.lower() not in people:
                errors.append(
                    f"context/owner_map.yaml: clients.{key}.{role}: {email!r} is not in 'people'"
                )
    roles = {r for c in cfg.owner_map.clients.values() for r in c.roles}
    for persona in cfg.personas.values():
        rel = f"personas/{persona.persona}.yaml"
        for rule_id in persona.rules:
            if rule_id not in cfg.rules:
                errors.append(f"{rel}: rules: unknown rule {rule_id!r}")
        if persona.sharepoint_sites not in cfg.allowlist.sharepoint_sites:
            errors.append(
                f"{rel}: sharepoint_sites: unknown site group {persona.sharepoint_sites!r}"
            )
        if persona.scope_role not in roles:
            errors.append(f"{rel}: scope: unknown role {persona.scope_role!r}")
    for rule in cfg.rules.values():
        rel = f"rules/{rule.id}.yaml"
        for i, step in enumerate(rule.ladder):
            if step.to not in roles:
                errors.append(f"{rel}: ladder.{i}.to: unknown owner-map role {step.to!r}")
        for ref in (rule.owner, rule.notify):
            if ref and not (ref.startswith("owner_map.client.") and ref.split(".")[-1] in roles):
                errors.append(f"{rel}: owner: {ref!r} must be owner_map.client.<role>")
        for client in rule.clients:
            if client not in cfg.owner_map.clients:
                errors.append(f"{rel}: clients: unknown client {client!r}")
        for other in rule.include_open_alerts:
            if other not in cfg.rules:
                errors.append(f"{rel}: include_open_alerts: unknown rule {other!r}")
    for name, metric in cfg.metrics.items():
        if metric.owner not in people:
            errors.append(
                f"context/metrics.yaml: {name}.owner: {metric.owner!r} is not in 'people'"
            )
    for key in cfg.smartsheet_map.sheets:
        if key not in cfg.owner_map.clients:
            errors.append(f"context/smartsheet_map.yaml: sheets.{key}: unknown client")
    if errors:
        raise ConfigError("\n".join(errors))


@lru_cache(maxsize=4)
def get_config(root: str | None = None) -> AthenaConfig:
    return load_config(Path(root) if root else None)
