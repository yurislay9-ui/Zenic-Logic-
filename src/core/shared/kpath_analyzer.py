"""
K-Path Dependency Analyzer — Lightweight stub.

The full K-Path analyzer was removed as dead code (never produced
meaningful results on ARM/Termux with the 0.6B model). This stub
provides the same API as a passthrough — it accepts code but
returns no path analysis results, allowing the sandbox to function
without symbolic execution overhead.

S03a: Added measure_dependency_depth() and estimate_code_k_paths()
methods that callers expect (python_validation.py, tests).
"""

import ast
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class KPathAnalyzer:
    """Lightweight K-Path analyzer stub.

    Provides the same interface as the original but returns minimal results.
    The full implementation was removed because:
    - It added ~2-5s latency per validation
    - It never produced actionable results on ARM/Termux
    - The 0.6B model couldn't provide meaningful path analysis

    S03a: measure_dependency_depth() queries the SQLite DB for real
    dependency data. estimate_code_k_paths() uses AST/regex to
    count branches (lightweight, no LLM needed).
    """

    def __init__(self, k_limit: int = 10):
        self.k_limit = k_limit

    def analyze(self, code: str, language: str = "python") -> Dict[str, Any]:
        """Analyze code paths — returns empty results (passthrough)."""
        return {
            "paths_explored": 0,
            "paths_pruned": 0,
            "k_limit": self.k_limit,
            "source": "stub",
        }

    def measure_dependency_depth(self, func_name: str) -> Dict[str, Any]:
        """Measure the dependency depth of a function via the project DB.

        Queries the SQLite database (if available) for stored AST
        connections and computes the BFS depth from the target function.

        Returns:
            Dict with keys:
              - depth: int (0 if function not found or no DB)
              - nodes_affected: int
              - exceeds_limit: bool (depth > k_limit)
              - affected_nodes: list of str
        """
        result: Dict[str, Any] = {
            "depth": 0,
            "nodes_affected": 0,
            "exceeds_limit": False,
            "affected_nodes": [],
        }

        try:
            from src.core.shared.db_initializer import get_connection
            conn = get_connection()
            if conn is None:
                return result

            try:
                row = conn.execute(
                    "SELECT connections FROM ast_nodes WHERE name=? LIMIT 1",
                    (func_name,)
                ).fetchone()

                if row is None:
                    return result

                # Parse connections from the DB column
                # Format can be:
                #   1. JSON list of strings: ["call:func_b", "call:func_c"]
                #   2. JSON list of dicts: [{"caller":"func_a","callee":"func_b"}]
                #   3. Colon-separated text: "func_a:func_b\nfunc_b:func_c"
                import json
                connections_raw = row[0] if row[0] else "[]"
                connections = []
                try:
                    parsed = json.loads(connections_raw) if isinstance(connections_raw, str) else connections_raw
                    if isinstance(parsed, list):
                        for item in parsed:
                            if isinstance(item, dict):
                                connections.append(item)
                            elif isinstance(item, str):
                                # Format: "type:name" or just "name"
                                if ":" in item:
                                    parts = item.split(":", 1)
                                    connections.append({"type": parts[0].strip(), "callee": parts[1].strip()})
                                else:
                                    connections.append({"callee": item.strip()})
                    elif isinstance(parsed, str):
                        for line in parsed.split("\n"):
                            line = line.strip()
                            if ":" in line:
                                parts = line.split(":", 1)
                                connections.append({"type": parts[0].strip(), "callee": parts[1].strip()})
                except (json.JSONDecodeError, TypeError):
                    for line in str(connections_raw).split("\n"):
                        line = line.strip()
                        if ":" in line:
                            parts = line.split(":", 1)
                            connections.append({"type": parts[0].strip(), "callee": parts[1].strip()})

                # Also query all nodes in the DB to build a full graph
                all_rows = conn.execute(
                    "SELECT name, connections FROM ast_nodes"
                ).fetchall()
                all_connections = list(connections)  # Start with the target's connections
                for r in all_rows:
                    node_name = r[0]
                    node_conns_raw = r[1] if r[1] else "[]"
                    try:
                        node_parsed = json.loads(node_conns_raw) if isinstance(node_conns_raw, str) else node_conns_raw
                        if isinstance(node_parsed, list):
                            for item in node_parsed:
                                if isinstance(item, dict):
                                    all_connections.append({"caller": node_name, **item})
                                elif isinstance(item, str):
                                    if ":" in item:
                                        parts = item.split(":", 1)
                                        all_connections.append({"caller": node_name, "type": parts[0].strip(), "callee": parts[1].strip()})
                                    else:
                                        all_connections.append({"caller": node_name, "callee": item.strip()})
                    except (json.JSONDecodeError, TypeError):
                        pass

                # BFS from func_name to find dependency depth
                visited = {func_name}
                current_level = [func_name]
                depth = 0
                all_affected = [func_name]
                hit_limit = False

                while current_level:
                    next_level = []
                    for node in current_level:
                        for conn in all_connections:
                            # A node connects to its callees
                            caller = conn.get("caller", "")
                            callee = conn.get("callee", "")
                            if caller == node and callee and callee not in visited:
                                visited.add(callee)
                                next_level.append(callee)
                                all_affected.append(callee)
                    if next_level:
                        depth += 1
                        if depth > self.k_limit:
                            hit_limit = True
                            break
                    current_level = next_level

                result["depth"] = depth
                result["nodes_affected"] = len(all_affected)  # Include root (matches test expectations)
                result["exceeds_limit"] = hit_limit or depth > self.k_limit
                result["affected_nodes"] = all_affected  # Include root
            finally:
                conn.close()

        except Exception as e:
            logger.debug("KPathAnalyzer.measure_dependency_depth: DB error: %s", e)
            result["error"] = str(e)

        return result

    def estimate_code_k_paths(self, code: str, language: str = "python") -> int:
        """Estimate the number of k-paths (execution paths) in code.

        Uses AST for Python (accurate branch counting) and regex
        for other languages (approximate).

        Returns:
            int: Estimated number of paths (capped at 1000)
        """
        if not code or not code.strip():
            return 1

        if language == "python":
            return self._estimate_python_paths(code)
        else:
            return self._estimate_regex_paths(code, language)

    def _estimate_python_paths(self, code: str) -> int:
        """Count branches in Python code using AST."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return 1

        branches = 0
        for node in ast.walk(tree):
            # Each if/elif adds a branch
            if isinstance(node, ast.If):
                branches += 1
            # While loops add a branch (enter or skip)
            elif isinstance(node, ast.While):
                branches += 1
            # For loops add a branch (enter or skip)
            elif isinstance(node, ast.For):
                branches += 1
            # Except handlers add a branch
            elif isinstance(node, ast.ExceptHandler):
                branches += 1
            # Boolean operators (and/or) add branches
            elif isinstance(node, ast.BoolOp):
                branches += len(node.values) - 1

        # Paths = 2^branches, capped at 1000
        paths = 2 ** branches if branches > 0 else 1
        return min(paths, 1000)

    def _estimate_regex_paths(self, code: str, language: str) -> int:
        """Count branches in non-Python code using regex patterns."""
        # Common branch patterns across languages
        branch_patterns = [
            r'\bif\b',              # if statements
            r'\belse\b',            # else clauses
            r'\belif\b',            # elif clauses
            r'\bswitch\b',          # switch statements
            r'\bcase\b',            # case clauses
            r'\bcatch\b',           # exception handlers
            r'\?\s*',               # ternary operators
            r'\|\|',                # logical OR
            r'&&',                  # logical AND
        ]

        branches = 0
        for pattern in branch_patterns:
            matches = re.findall(pattern, code)
            branches += len(matches)

        # Rough estimation: 2^branches, capped
        paths = 2 ** min(branches, 10) if branches > 0 else 1
        return min(paths, 1000)
