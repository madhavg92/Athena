import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from athena.core.db import Base, Database, Receipt, database_url

ROOT = Path(__file__).resolve().parents[2]
TABLES = set(Base.metadata.tables)


def upgrade(url: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")


def test_database_url_normalises_postgres() -> None:
    assert database_url("postgres://u@h/db") == "postgresql+psycopg://u@h/db"
    assert database_url("postgresql://u@h/db") == "postgresql+psycopg://u@h/db"
    assert database_url("sqlite://") == "sqlite://"


def test_sqlite_migration_matches_models(tmp_path, monkeypatch) -> None:
    url = f"sqlite:///{tmp_path}/m.db"
    upgrade(url, monkeypatch)
    insp = inspect(create_engine(url))
    assert TABLES <= set(insp.get_table_names())
    for table in TABLES:
        assert {c["name"] for c in insp.get_columns(table)} == set(
            Base.metadata.tables[table].columns.keys()
        )


def test_postgres_sql_renders(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://athena@localhost/athena")
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head", sql=True)
    out = capsys.readouterr().out
    assert "CREATE TABLE receipts" in out and "JSON" in out and "TIMESTAMP WITH TIME ZONE" in out


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def postgres():
    tmp_path = Path(tempfile.mkdtemp(prefix="athena-pg-"))
    bindir = Path("/usr/lib/postgresql/16/bin")
    if not (bindir / "initdb").exists() or (os.geteuid() == 0 and not shutil.which("runuser")):
        pytest.skip("no local Postgres")
    data = tmp_path / "pg"
    port = _free_port()
    run_as = ["runuser", "-u", "nobody", "--"] if os.geteuid() == 0 else []
    if run_as:
        tmp_path.chmod(0o777)
    init = subprocess.run(
        [*run_as, str(bindir / "initdb"), "-D", str(data), "-U", "athena", "--auth=trust"],
        capture_output=True,
    )
    if init.returncode != 0:
        pytest.skip("initdb failed in this environment")
    proc = subprocess.Popen(
        [
            *run_as,
            str(bindir / "postgres"),
            "-D",
            str(data),
            "-p",
            str(port),
            "-k",
            str(tmp_path),
            "-c",
            "listen_addresses=127.0.0.1",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"postgresql://athena@127.0.0.1:{port}/postgres"
    for _ in range(50):
        try:
            create_engine(database_url(url)).connect().close()
            break
        except Exception:
            time.sleep(0.2)
    yield url
    proc.terminate()
    proc.wait(10)
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_postgres_upgrade_and_use(postgres, monkeypatch) -> None:
    upgrade(postgres, monkeypatch)
    db = Database(postgres)
    assert TABLES <= set(inspect(db.engine).get_table_names())
    with db.session() as s:
        s.add(
            Receipt(
                actor="a", action_type="answer", mode="live", status="sent", sources=[{"name": "x"}]
            )
        )
    with db.session() as s:
        assert s.query(Receipt).one().sources == [{"name": "x"}]
