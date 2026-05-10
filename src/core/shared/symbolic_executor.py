"""
Symbolic Executor — Lightweight stub.

The full symbolic executor (2,158 lines across 8 files) was removed as
dead code. It was never used externally and added unnecessary complexity.
This stub provides the same interface but returns passthrough results.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SymbolicExecutor:
    """Lightweight symbolic executor stub.

    Provides the same interface as the original but performs no
    symbolic execution. The full implementation was removed because:
    - It depended on Z3 which is never available on ARM/Termux
    - It added ~5-10s latency per validation
    - It never produced actionable symbolic analysis results
    """

    def __init__(self, k_path_limit: int = 10, max_depth: int = 20):
        self.k_path_limit = k_path_limit
        self.max_depth = max_depth

    def execute(self, code: str, language: str = "python") -> Dict[str, Any]:
        """Symbolic execution — returns passthrough results."""
        return {
            "status": "skipped",
            "paths": [],
            "violations": [],
            "source": "stub",
        }
