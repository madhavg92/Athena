import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config_copy(tmp_path: Path) -> Path:
    """A writable copy of the config directories."""
    for name in ("rules", "personas", "context"):
        shutil.copytree(ROOT / name, tmp_path / name)
    return tmp_path


@pytest.fixture
def db():
    from athena.core.db import Database

    return Database("sqlite://")


@pytest.fixture
def cfg():
    from athena.core.config import load_config

    return load_config(ROOT)


@pytest.fixture
def anchor():
    from athena.connectors.base import fixture_anchor

    return fixture_anchor()


@pytest.fixture
def app(cfg, db, anchor):
    from athena.app import build

    return build(cfg=cfg, db=db, clock=lambda: anchor, run_mode="fixture")
