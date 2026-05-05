"""
Unit tests for local_engine.py — TitanEngine, SimpleParser, SimpleRouter (legacy).

Tests the legacy pure-Python engine components:
  - SimpleParser: keyword-based intent parsing
  - SimpleRouter: criticality-based routing
  - SimplePlanner: execution plan generation
  - SimpleCache: SQLite theorem caching
  - SimpleLedger: Merkle ledger for snapshots/rollback/commit
  - SimpleSandbox: Python code validation via compile()
  - TitanEngine: full pipeline (parse → cache → route → plan → execute → validate → commit/rollback)
"""

from .test_local_parts import *
