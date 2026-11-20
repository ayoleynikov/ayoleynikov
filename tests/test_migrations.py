"""Alembic migration smoke tests (no live database required)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_initial_revision() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    scripts = ScriptDirectory.from_config(cfg)
    revisions = list(scripts.walk_revisions())
    assert revisions, "Expected at least one Alembic revision"
    heads = scripts.get_heads()
    assert len(heads) == 1
    assert heads[0] == "20261120_0001"


def test_initial_migration_module_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "alembic" / "versions" / "20261120_0001_core_tenant_tables.py"
    spec = importlib.util.spec_from_file_location("pulse_migration_0001", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "20261120_0001"
    assert callable(module.upgrade)
    assert callable(module.downgrade)
