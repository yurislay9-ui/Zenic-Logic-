# Task 7 — Fix F-05: BaseAgent.run() Records Fallback as CB Failure (Death Spiral)

## Summary
Fixed the death spiral bug in `BaseAgent.run()` where fallback results were incorrectly counted as circuit breaker failures, causing premature CB trips and cascading failures.

## File Changed
- `/home/z/my-project/Zenic-Logic-/src/core/agents_v2/resilience/base_agent.py` (lines 145-161)

## Bug Description
The original code treated `source == "fallback"` the same as `source == "error"`, recording both as CB failures. Since fallback is a successful recovery mechanism (the agent produced a valid result), counting it as a failure created a death spiral:

1. `execute()` fails → fallback runs → CB records failure
2. CB failure count grows → CB opens prematurely
3. CB open → all calls go to `circuit_open_fallback` → more "failures"
4. CB stays open forever (death spiral)

Similarly, `circuit_open_fallback` and `bulkhead_fallback` are caused by the resilience mechanisms themselves, not by the agent failing — they should not be recorded as CB failures either.

## Fix Applied
Replaced the two-category logic (success vs. failure) with three categories:

1. **Success** (`source == "deterministic"`) → `record_success()` + `success = True`
2. **Degraded success** (`source` is "fallback", "circuit_open_fallback", "bulkhead_fallback") → **no CB recording at all** + `success = True`
3. **Hard failure** (`source == "error"`) → `record_failure()` + `success = False`

By not recording degraded successes as either CB success or failure, we prevent the death spiral while still ensuring that genuine hard failures (where even fallback couldn't recover) properly increment the CB failure counter.
