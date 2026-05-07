# Task: Phase 7 Best Practices Fixes — Work Record

## Summary

All Phase 7 best practices fixes have been successfully implemented. This includes:

### New Shared Utility Modules Created (5 files)

1. **`src/core/shared/retry.py`** — Eliminates DRY-1 (retry pattern duplicated 7+ times)
   - `with_retry()`: Execute a callable with retry and exponential backoff
   - `with_retry_or_false()`: Convenience wrapper returning True/False
   - Constants: `DEFAULT_MAX_RETRIES=3`, `DEFAULT_BASE_DELAY=0.1`

2. **`src/core/shared/ast_utils.py`** — Eliminates DRY-2 (cyclomatic complexity duplicated 2 times)
   - `compute_cyclomatic_complexity()`: McCabe cyclomatic complexity
   - `extract_function_calls()`: Unique function call names from AST
   - `extract_class_connections()`: Inheritance and method connections

3. **`src/core/shared/db_utils.py`** — Eliminates DRY-3 (SQL LIKE escaping) and DRY-9 (tenant purge)
   - `escape_sql_like()`: Escape SQL LIKE wildcards to prevent injection
   - `purge_tenant_rows()`: Delete all rows for a specific tenant

4. **`src/core/shared/tenant_utils.py`** — Eliminates DRY-8 (tenant ID resolution duplicated 3 times)
   - `resolve_tenant_id()`: Resolve tenant ID from TenantContext with fallback
   - `ANONYMOUS_TENANT = "__anonymous__"`: Shared constant

5. **`src/core/shared/z3_parts/z3_context.py`** — Eliminates DRY-7 (gc.collect() after Z3 operations)
   - `z3_session()`: Context manager for Z3 solver sessions with automatic cleanup

### Engine Files Updated (12 files)

6a. **`level3_graph_ast/engine.py`** — Full refactoring
   - Replaced inline retry loops with `with_retry` in `_store_node`, `_store_nodes_batch`
   - Replaced `_detect_language` mapping with `EXT_LANG_MAP` from constants
   - Replaced `_cyclomatic_complexity`, `_extract_calls`, `_extract_class_connections` with shared utility wrappers
   - Replaced SQL LIKE escaping with `escape_sql_like`
   - Replaced tenant resolution with `resolve_tenant_id()`
   - Replaced `purge_tenant_data` with `purge_tenant_rows`
   - Added docstrings to `scan_code`, `_detect_language`, `_parse_python`, `_parse_regex`, `analyze_structure`

6b. **`level2_macro_router/router.py`**
   - Replaced inline retry loop with `with_retry` in `_check_ast_criticality`
   - Replaced SQL LIKE escaping with `escape_sql_like`
   - Extracted `_CRITICAL_COMPLEXITY_THRESHOLD = 15`

6c. **`level7_merkle_ledger/ledger.py`**
   - Replaced tenant resolution with `resolve_tenant_id()`
   - Replaced inline retry loop with `with_retry` in `_record_operation`
   - Replaced `purge_tenant_ledger` with `purge_tenant_rows`
   - Extracted `_BACKUP_HASH_LENGTH = 16`
   - Added docstrings to `_hash_content`, `_merkle_root`

6d. **`level8_theorem_cache/cache.py`**
   - Replaced tenant resolution with `resolve_tenant_id()`
   - Replaced inline retry loop with `with_retry` in `save`
   - Replaced `purge_tenant_cache` with `purge_tenant_rows`
   - Extracted constants: `_DEFAULT_MAX_ENTRIES=500`, `_CODE_HASH_LENGTH=16`, `_EVICTION_THRESHOLD=0.9`, `_EVICTION_HIT_PROTECTION=50`
   - Added docstrings to `_hash`, `get_stats`, `clear`

6e. **`z3_parts/solver_core.py`**
   - Replaced inline retry loop with `with_retry` in `_z3_solve`
   - Extracted constants: `_MAX_SORT_COUNTER=100_000`, `_TIMESTAMP_MODULO=1_000_000`, `_Z3_SOLVE_MAX_ATTEMPTS=2`, `_Z3_RETRY_BASE_DELAY=0.3`

6f. **`z3_parts/invariants.py`**
   - Replaced manual encoding map reset with `self._reset_encoding()` calls
   - Extracted constants: `_INV_ENUM_THRESHOLD=5000`, `_MAX_VIOLATION_CONSTRAINTS=50`, `_NUMERIC_DOMAIN_INT_THRESHOLD=50`, `_BOUNDED_SAMPLE_COUNT=200`, `_BOUNDED_TIMEOUT_DIVISOR=50`

6g. **`z3_parts/solver_encoding.py`**
   - Extracted constants: `_DEFAULT_MAX_SAMPLES=20`, `_REAL_DECIMAL_PRECISION=6`

6h. **`sandbox_parts/_manager.py`**
   - Extracted constants: `_DEFAULT_TTL_SECONDS=3600`, `_CLEANUP_INTERVAL_SECONDS=60`, `_CLEANUP_OLDEST_COUNT=2`

6i. **`semantic_parts/_mixin_embed.py`**
   - Extracted `_EVICTION_DIVISOR = 5`
   - Added `_normalize_embedding()` static method to deduplicate normalization pattern

6j. **`semantic_parts/_mixin_classify.py`**
   - Extracted `_KEYWORD_CONFIDENCE_DIVISOR = 10.0`, `_MAX_FALLBACK_CONFIDENCE = 0.5`

6k. **`semantic_parts/_mixin_search.py`**
   - Extracted `_DEFAULT_SEARCH_TOP_K = 5`, `_DEFAULT_SEARCH_THRESHOLD = 0.5`, `_DEFAULT_SIMILAR_THRESHOLD = 0.7`

6l. **`planner_parts/mcts.py`**
   - Extracted constants: `_MCTS_BASE_REWARD=0.1`, `_MCTS_DEPTH_REWARD=0.1`, `_MCTS_VALIDATION_REWARD=0.2`, `_MCTS_COMPLETENESS_BONUS=0.3`, `_MCTS_SHALLOW_PENALTY=0.1`

### Additional Updates

- **`z3_parts/__init__.py`** — Added `z3_session` to exports

### Verification

All files pass:
- `python -m py_compile` syntax checks
- Import resolution tests
- Functional tests for `escape_sql_like`, `compute_cyclomatic_complexity`, and `with_retry`
