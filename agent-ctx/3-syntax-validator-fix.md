# Task 3 - Syntax Validator Bug Fix

## Summary
Fixed two critical bugs in `src/core/agents_v2/validation/syntax_validator.py`:

### Bug F-01a: `_function_returns_on_all_paths` Always Returns True
- **Root cause**: Method computed `has_return` but unconditionally returned `True`, making the return-path check dead code.
- **Fix**: Implemented proper heuristic:
  1. No return statements → void function → True (OK)
  2. Last statement is a `Return` → True (OK)
  3. Last statement is `if/else` where both branches return → True (OK)
  4. Otherwise → False (warning: may not return on all paths)

### Bug F-01b: `fallback()` Fail-Open Posture
- **Root cause**: `fallback()` returned `valid=True` — degraded validation lets bad code through.
- **Fix**: Changed to `valid=False` (fail-closed) with a `validation_degraded` warning.
- Updated class docstring accordingly.
