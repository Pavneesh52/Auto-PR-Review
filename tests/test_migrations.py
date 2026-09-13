"""Tests that the ORM models and Alembic migrations agree.

Drift between the two is invisible until a deploy fails, so it's worth
asserting directly. The migrations are executed against a stubbed
`alembic.op` so no database is required.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from pr_review_agent.db.models import Base, ReviewRow

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _load_migrations(
    monkeypatch: pytest.MonkeyPatch, *filenames: str
) -> tuple[list[Any], dict[str, Any]]:
    """Load migration modules that all share one recording alembic.op stub.

    Sharing the stub is what lets a test observe the net effect of running
    several migrations in sequence.
    """
    recorded: dict[str, Any] = {"tables": [], "indexes": [], "unique": {}}

    fake_op = types.SimpleNamespace()

    def create_table(name: str, *args: Any, **kwargs: Any) -> None:
        recorded["tables"].append(name)

    def create_index(name: str, table: str, *args: Any, **kwargs: Any) -> None:
        recorded["indexes"].append(name)
        recorded["unique"][name] = kwargs.get("unique", False)

    def drop_index(name: str, *args: Any, **kwargs: Any) -> None:
        recorded["unique"].pop(name, None)

    fake_op.create_table = create_table
    fake_op.create_index = create_index
    fake_op.drop_index = drop_index
    fake_op.drop_table = lambda *a, **k: None
    fake_op.execute = lambda *a, **k: None

    try:
        import alembic
    except ImportError:  # pragma: no cover - alembic is a dev dependency
        alembic = types.ModuleType("alembic")
        sys.modules["alembic"] = alembic

    monkeypatch.setattr(alembic, "op", fake_op, raising=False)

    modules: list[Any] = []
    for filename in filenames:
        spec = importlib.util.spec_from_file_location(
            f"migration_{filename}", VERSIONS_DIR / filename
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)

    return modules, recorded


def test_migration_chain_is_linked(monkeypatch):
    (m1, m2), _ = _load_migrations(monkeypatch, "001_initial.py", "002_review_history.py")
    assert m1.down_revision is None
    assert m2.down_revision == m1.revision == "001_initial"


def test_migrations_create_exactly_the_model_tables(monkeypatch):
    (m1,), recorded = _load_migrations(monkeypatch, "001_initial.py")
    m1.upgrade()

    assert set(recorded["tables"]) == set(Base.metadata.tables)


def test_migrations_create_exactly_the_model_indexes(monkeypatch):
    (m1,), recorded = _load_migrations(monkeypatch, "001_initial.py")
    m1.upgrade()

    model_indexes = {
        index.name for table in Base.metadata.tables.values() for index in table.indexes
    }
    # 002 replaces ix_reviews_repo_pr in place, so the set is still complete
    assert set(recorded["indexes"]) == model_indexes


def test_net_index_state_matches_models(monkeypatch):
    """After 001 + 002 the index must be non-unique, matching the ORM.

    A unique (repo, PR) index meant the second push for a PR raised an
    IntegrityError and the review was silently dropped.
    """
    (m1, m2), recorded = _load_migrations(monkeypatch, "001_initial.py", "002_review_history.py")

    m1.upgrade()
    assert recorded["unique"]["ix_reviews_repo_pr"] is True  # original constraint

    m2.upgrade()
    model_unique = {i.name: i.unique for i in ReviewRow.__table__.indexes}
    assert recorded["unique"]["ix_reviews_repo_pr"] is False
    assert model_unique["ix_reviews_repo_pr"] is False


def test_migration_002_downgrade_restores_uniqueness(monkeypatch):
    (m1, m2), recorded = _load_migrations(monkeypatch, "001_initial.py", "002_review_history.py")

    m1.upgrade()
    m2.upgrade()
    assert recorded["unique"]["ix_reviews_repo_pr"] is False

    m2.downgrade()
    assert recorded["unique"]["ix_reviews_repo_pr"] is True
