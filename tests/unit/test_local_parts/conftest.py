"""Shared fixtures for local engine tests."""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.core.local_engine import (
    SimpleParser,
    SimpleRouter,
    SimplePlanner,
    SimpleCache,
    SimpleLedger,
    SimpleSandbox,
    TitanEngine,
    INTENT_KEYWORDS,
    GOAL_KEYWORDS,
    CRITICAL_PATTERNS,
    get_data_dir,
    get_db_path,
)
from src.core.shared.contracts import OperationType, GoalType


@pytest.fixture
def parser():
    return SimpleParser()


@pytest.fixture
def router():
    return SimpleRouter()


@pytest.fixture
def planner():
    return SimplePlanner()


@pytest.fixture
def sandbox():
    return SimpleSandbox()


@pytest.fixture
def ledger():
    """Ledger with a temp backup directory."""
    with patch("src.core.local_engine.get_data_dir") as mock_dir:
        import tempfile
        tmp = tempfile.mkdtemp(prefix="titan_test_ledger_")
        mock_dir.return_value = Path(tmp) / "db"
        (Path(tmp) / "db").mkdir(parents=True, exist_ok=True)
        led = SimpleLedger()
        led.bk_dir = Path(tmp) / "backups"
        led.bk_dir.mkdir(exist_ok=True)
        yield led
