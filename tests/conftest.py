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
