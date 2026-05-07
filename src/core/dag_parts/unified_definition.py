"""
Unified DAG Definition — Merges DAG v16 + Pipeline v18 into a single graph.

Maps all 42+ agents as DAG nodes with parallel group annotations,
conditional routing, and backward compatibility with DAG v16.

Architecture:
  CACHE_CHECK → BILINGUAL_ROUTE → INTENT_CLASSIFY → [ENTITY_EXTRACT ∥ TARGET_RESOLVE]
  → CRITICALITY_SCORE → [MEMORY_COLLECT ∥ SEMANTIC_PREP]
  → RELEVANCE_SCORE → CONTEXT_COMPRESS → CONTEXT_PREFETCH
  → AST_ANALYZE → THEOREM_CACHE → ROUTE_DECISION
  → {CODE_PATH | BIZ_PATH | AUTO_PATH | REASON_PATH}
  → SECURITY_SCAN → SYNTAX_VALIDATE → RISK_CALC → FIX_SUGGEST
  → EVIDENCE_COLLECT → CONSENSUS_RESOLVE → VERDICT
  → SANDBOX → LEDGER_COMMIT/ROLLBACK → THEOREM_SAVE → MEMORY_SAVE → DONE

Parallel Groups:
  1. INTENT_PARALLEL:   ENTITY_EXTRACT ∥ TARGET_RESOLVE
  2. CONTEXT_PARALLEL:  MEMORY_COLLECT ∥ SEMANTIC_PREP
  3. EXECUTE_PARALLEL:  CODE_PATH ∥ BIZ_PATH ∥ AUTO_PATH ∥ REASON_PATH
     (Only 1 active based on routing; others are skipped)

Sequential Pipelines (within execution paths):
  - CODE_PIPELINE:  CODE_GENERATE/REFACTOR/OPTIMIZE/FIX/SCAFFOLD → DEFENSIVE_INJECT
  - BIZ_PIPELINE:   OP_ROUTE → {INVOICE|INVENTORY|CRM|TASK|REPORT|NOTIFICATION|ANALYTICS}
  - AUTO_PIPELINE:  TRIGGER → ACTION → SCHEDULE → CONDITION → AUTO_NAME → WORKFLOW_SERIAL
  - REASON_PIPELINE: PROBLEM_DETECT → STEP_DECOMPOSE → TEMPLATE_REASON → CONFIDENCE → CONCLUSION
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ═══════════════════════════════════════════════════════════════
#  ENUMS & DATACLASSES
# ═══════════════════════════════════════════════════════════════

class ExecutionMode(Enum):
    """How a node (or group of nodes) should be executed."""
    SEQUENTIAL = "sequential"       # Standard: run one after another
    PARALLEL = "parallel"           # All nodes in group run concurrently
    CONDITIONAL = "conditional"     # Only one path is taken based on routing


@dataclass
class UnifiedDAGNode:
    """A node in the unified DAG representing a single agent or composite step.

    Attributes:
        name: Unique node identifier (matches PIPELINE_DAG key for v16 compat).
        agent_id: Pipeline v18 agent identifier (e.g., "A01").
        exec_method: Method name on the orchestrator to invoke.
        execution_mode: Whether this node runs sequentially, in parallel, or conditionally.
        transitions: Mapping of result keys to next node names.
        default_next: Fallback next node if result not in transitions.
        criticality_skip: Criticality levels that should skip this node.
        max_retries: Maximum retry count for correction loops.
        timeout_ms: Per-node execution timeout in milliseconds.
        parallel_group: Name of the parallel group this node belongs to.
        requires_memory_bus: Whether this node uses SharedMemoryBus for I/O.
        description: Human-readable description of the node's purpose.
    """
    name: str
    agent_id: str = ""
    exec_method: str = ""
    execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    transitions: Dict[str, str] = field(default_factory=dict)
    default_next: str = ""
    criticality_skip: List[int] = field(default_factory=list)
    max_retries: int = 1
    timeout_ms: float = 5000.0
    parallel_group: str = ""
    requires_memory_bus: bool = True
    description: str = ""


@dataclass
class ParallelGroup:
    """A group of nodes that can execute concurrently.

    Attributes:
        name: Unique group identifier.
        nodes: List of node names in this group.
        merge_node: Node that receives merged results from all parallel nodes.
        timeout_ms: Group-level timeout in milliseconds.
        cancel_on_error: If True, cancel sibling nodes when one fails.
    """
    name: str
    nodes: List[str] = field(default_factory=list)
    merge_node: str = ""
    timeout_ms: float = 10000.0
    cancel_on_error: bool = False


# ═══════════════════════════════════════════════════════════════
#  UNIFIED PIPELINE DAG — All 47+ Nodes
# ═══════════════════════════════════════════════════════════════

UNIFIED_PIPELINE_DAG: Dict[str, UnifiedDAGNode] = {
    # ───────────────────────────────────────────────────────────
    #  CACHE & ROUTING ENTRY
    # ───────────────────────────────────────────────────────────
    "CACHE_CHECK": UnifiedDAGNode(
        name="CACHE_CHECK",
        exec_method="_exec_cache_check",
        transitions={"hit": "DONE", "miss": "BILINGUAL_ROUTE"},
        default_next="BILINGUAL_ROUTE",
        timeout_ms=2000.0,
        description="Check SmartMemory cache for exact/semantic match",
    ),
    "BILINGUAL_ROUTE": UnifiedDAGNode(
        name="BILINGUAL_ROUTE",
        agent_id="A48",
        exec_method="_exec_bilingual_route",
        transitions={"*": "INTENT_CLASSIFY"},
        default_next="INTENT_CLASSIFY",
        timeout_ms=1500.0,
        description="Detect language (en/es) and normalize input for downstream agents",
    ),

    # ───────────────────────────────────────────────────────────
    #  PHASE 1: UNDERSTAND
    # ───────────────────────────────────────────────────────────
    "INTENT_CLASSIFY": UnifiedDAGNode(
        name="INTENT_CLASSIFY",
        agent_id="A01",
        exec_method="_exec_intent_classify",
        transitions={"*": "INTENT_PARALLEL_GATE"},
        default_next="INTENT_PARALLEL_GATE",
        timeout_ms=3000.0,
        description="Classify user intent (operation + goal) via SurgicalAgent F2",
    ),
    "INTENT_PARALLEL_GATE": UnifiedDAGNode(
        name="INTENT_PARALLEL_GATE",
        exec_method="_exec_parallel_gate",
        transitions={"*": "CRITICALITY_SCORE"},
        default_next="CRITICALITY_SCORE",
        execution_mode=ExecutionMode.PARALLEL,
        parallel_group="INTENT_PARALLEL",
        timeout_ms=5000.0,
        description="Gate node: launches ENTITY_EXTRACT ∥ TARGET_RESOLVE in parallel",
    ),
    "ENTITY_EXTRACT": UnifiedDAGNode(
        name="ENTITY_EXTRACT",
        agent_id="A02",
        exec_method="_exec_entity_extract",
        transitions={"*": "CRITICALITY_SCORE"},
        default_next="CRITICALITY_SCORE",
        parallel_group="INTENT_PARALLEL",
        timeout_ms=3000.0,
        description="Extract files, langs, functions, frameworks from user message",
    ),
    "TARGET_RESOLVE": UnifiedDAGNode(
        name="TARGET_RESOLVE",
        agent_id="A03",
        exec_method="_exec_target_resolve",
        transitions={"*": "CRITICALITY_SCORE"},
        default_next="CRITICALITY_SCORE",
        parallel_group="INTENT_PARALLEL",
        timeout_ms=3000.0,
        description="Resolve target file, language, scope from entity results",
    ),
    "CRITICALITY_SCORE": UnifiedDAGNode(
        name="CRITICALITY_SCORE",
        agent_id="A04",
        exec_method="_exec_criticality_score",
        transitions={"*": "CONTEXT_PARALLEL_GATE"},
        default_next="CONTEXT_PARALLEL_GATE",
        timeout_ms=3000.0,
        description="Score criticality level (1=FAST, 2=DEEP, 3=SURGICAL) with adjustments",
    ),

    # ───────────────────────────────────────────────────────────
    #  PHASE 2: CONTEXT (with parallelism)
    # ───────────────────────────────────────────────────────────
    "CONTEXT_PARALLEL_GATE": UnifiedDAGNode(
        name="CONTEXT_PARALLEL_GATE",
        exec_method="_exec_parallel_gate",
        transitions={"*": "RELEVANCE_SCORE"},
        default_next="RELEVANCE_SCORE",
        execution_mode=ExecutionMode.PARALLEL,
        parallel_group="CONTEXT_PARALLEL",
        timeout_ms=8000.0,
        description="Gate node: launches MEMORY_COLLECT ∥ SEMANTIC_PREP in parallel",
    ),
    "MEMORY_COLLECT": UnifiedDAGNode(
        name="MEMORY_COLLECT",
        agent_id="A05",
        exec_method="_exec_memory_collect",
        transitions={"*": "RELEVANCE_SCORE"},
        default_next="RELEVANCE_SCORE",
        parallel_group="CONTEXT_PARALLEL",
        timeout_ms=5000.0,
        description="Collect working/long-term/episodic/procedural memory entries",
    ),
    "SEMANTIC_PREP": UnifiedDAGNode(
        name="SEMANTIC_PREP",
        exec_method="_exec_semantic_prep",
        transitions={"*": "RELEVANCE_SCORE"},
        default_next="RELEVANCE_SCORE",
        parallel_group="CONTEXT_PARALLEL",
        timeout_ms=5000.0,
        description="Prepare semantic embeddings and similarity indexes for context",
    ),
    "RELEVANCE_SCORE": UnifiedDAGNode(
        name="RELEVANCE_SCORE",
        agent_id="A06",
        exec_method="_exec_relevance_score",
        transitions={"*": "CONTEXT_COMPRESS"},
        default_next="CONTEXT_COMPRESS",
        timeout_ms=3000.0,
        description="Score and rank memory entries by relevance to intent",
    ),
    "CONTEXT_COMPRESS": UnifiedDAGNode(
        name="CONTEXT_COMPRESS",
        agent_id="A07",
        exec_method="_exec_context_compress",
        transitions={"*": "CONTEXT_PREFETCH"},
        default_next="CONTEXT_PREFETCH",
        timeout_ms=3000.0,
        description="Compress scored context into token-budget-aware representation",
    ),
    "CONTEXT_PREFETCH": UnifiedDAGNode(
        name="CONTEXT_PREFETCH",
        agent_id="A08",
        exec_method="_exec_context_prefetch",
        transitions={"*": "AST_ANALYZE"},
        default_next="AST_ANALYZE",
        timeout_ms=4000.0,
        description="Prefetch related context entries and generate hints for downstream",
    ),

    # ───────────────────────────────────────────────────────────
    #  DAG v16 COMPAT: AST, THEOREM, ROUTING
    # ───────────────────────────────────────────────────────────
    "AST_ANALYZE": UnifiedDAGNode(
        name="AST_ANALYZE",
        exec_method="_exec_ast_analyze",
        transitions={"*": "THEOREM_CACHE"},
        default_next="THEOREM_CACHE",
        timeout_ms=3000.0,
        description="Analyze code structure via GraphAST engine (v16 compat)",
    ),
    "THEOREM_CACHE": UnifiedDAGNode(
        name="THEOREM_CACHE",
        exec_method="_exec_theorem_cache",
        transitions={"hit": "DONE", "miss": "ROUTE"},
        default_next="ROUTE",
        timeout_ms=2000.0,
        description="Check theorem cache for proven solutions (v16 compat)",
    ),
    "ROUTE": UnifiedDAGNode(
        name="ROUTE",
        exec_method="_exec_route",
        transitions={"*": "ROUTE_DECISION"},
        default_next="ROUTE_DECISION",
        timeout_ms=2000.0,
        description="Macro Router (MoE) — determines route and initial criticality",
    ),
    "ROUTE_DECISION": UnifiedDAGNode(
        name="ROUTE_DECISION",
        exec_method="_exec_route_decision",
        transitions={
            "code": "PLAN",
            "biz": "OP_ROUTE",
            "auto": "TRIGGER",
            "reason": "PROBLEM_DETECT",
            "high_crit": "SOLVER_VERIFY",
            "visual": "VISUAL_BYPASS",
            "abortive": "ABORTIVE",
        },
        default_next="PLAN",
        execution_mode=ExecutionMode.CONDITIONAL,
        timeout_ms=2000.0,
        description="Decide execution path (code/biz/auto/reason) based on intent + routing",
    ),

    # ───────────────────────────────────────────────────────────
    #  DAG v16 COMPAT: PLAN, SOLVER, ABORTIVE
    # ───────────────────────────────────────────────────────────
    "PLAN": UnifiedDAGNode(
        name="PLAN",
        exec_method="_exec_plan",
        transitions={
            "abortive": "ABORTIVE",
            "low_crit": "CODE_GENERATE",
            "standard": "CODE_GENERATE",
            "high_crit": "SOLVER_VERIFY",
            "generate": "CODE_GENERATE",
            "refactor": "CODE_REFACTOR",
            "optimize": "CODE_OPTIMIZE",
            "fix": "CODE_FIX",
            "scaffold": "CODE_SCAFFOLD",
            "visual": "VISUAL_BYPASS",
        },
        default_next="CODE_GENERATE",
        max_retries=2,
        timeout_ms=5000.0,
        description="APA Planner with criticality routing (v16 compat)",
    ),
    "SOLVER_VERIFY": UnifiedDAGNode(
        name="SOLVER_VERIFY",
        exec_method="_exec_solver_verify",
        transitions={
            "pass": "CODE_GENERATE",
            "fail": "ABORTIVE",
            "fail_timeout": "ABORTIVE",
        },
        default_next="ABORTIVE",
        max_retries=2,
        timeout_ms=10000.0,
        description="Z3 solver verification for high-criticality paths (v16 compat)",
    ),
    "ABORTIVE": UnifiedDAGNode(
        name="ABORTIVE",
        exec_method="_exec_abortive",
        transitions={"*": "DONE"},
        default_next="DONE",
        timeout_ms=3000.0,
        description="Abortive protocol — decompose into subtasks (v16 compat)",
    ),

    # ───────────────────────────────────────────────────────────
    #  PHASE 3A: CODE EXECUTION PATH
    # ───────────────────────────────────────────────────────────
    "CODE_GENERATE": UnifiedDAGNode(
        name="CODE_GENERATE",
        agent_id="A17",
        exec_method="_exec_code_generate",
        transitions={"*": "DEFENSIVE_INJECT"},
        default_next="DEFENSIVE_INJECT",
        timeout_ms=15000.0,
        description="Generate code from requirements using CodeAgent",
    ),
    "CODE_REFACTOR": UnifiedDAGNode(
        name="CODE_REFACTOR",
        agent_id="A18",
        exec_method="_exec_code_refactor",
        transitions={"*": "DEFENSIVE_INJECT"},
        default_next="DEFENSIVE_INJECT",
        timeout_ms=15000.0,
        description="Refactor existing code based on requirements",
    ),
    "CODE_OPTIMIZE": UnifiedDAGNode(
        name="CODE_OPTIMIZE",
        agent_id="A19",
        exec_method="_exec_code_optimize",
        transitions={"*": "DEFENSIVE_INJECT"},
        default_next="DEFENSIVE_INJECT",
        timeout_ms=15000.0,
        description="Optimize existing code for performance/readability",
    ),
    "CODE_FIX": UnifiedDAGNode(
        name="CODE_FIX",
        agent_id="A20",
        exec_method="_exec_code_fix",
        transitions={"*": "DEFENSIVE_INJECT"},
        default_next="DEFENSIVE_INJECT",
        timeout_ms=15000.0,
        description="Fix bugs/issues in existing code",
    ),
    "CODE_SCAFFOLD": UnifiedDAGNode(
        name="CODE_SCAFFOLD",
        agent_id="A21",
        exec_method="_exec_code_scaffold",
        transitions={"*": "DEFENSIVE_INJECT"},
        default_next="DEFENSIVE_INJECT",
        timeout_ms=20000.0,
        description="Scaffold a new project structure from requirements",
    ),
    "DEFENSIVE_INJECT": UnifiedDAGNode(
        name="DEFENSIVE_INJECT",
        agent_id="A22",
        exec_method="_exec_defensive_inject",
        transitions={"*": "SECURITY_SCAN"},
        default_next="SECURITY_SCAN",
        timeout_ms=5000.0,
        description="Inject defensive patterns (error handling, logging, validation)",
    ),

    # ───────────────────────────────────────────────────────────
    #  PHASE 3B: BUSINESS EXECUTION PATH
    # ───────────────────────────────────────────────────────────
    "OP_ROUTE": UnifiedDAGNode(
        name="OP_ROUTE",
        agent_id="A16",
        exec_method="_exec_op_route",
        transitions={
            "invoice": "INVOICE",
            "inventory": "INVENTORY",
            "crm": "CRM",
            "task": "TASK",
            "report": "REPORT",
            "notification": "NOTIFICATION",
            "analytics": "ANALYTICS",
            "custom": "ANALYTICS",
        },
        default_next="ANALYTICS",
        execution_mode=ExecutionMode.CONDITIONAL,
        timeout_ms=2000.0,
        description="Route business operation to the correct domain agent",
    ),
    "INVOICE": UnifiedDAGNode(
        name="INVOICE",
        agent_id="A09",
        exec_method="_exec_invoice",
        transitions={"*": "SECURITY_SCAN"},
        default_next="SECURITY_SCAN",
        timeout_ms=5000.0,
        description="Process invoice calculations, tax, discounts",
    ),
    "INVENTORY": UnifiedDAGNode(
        name="INVENTORY",
        agent_id="A10",
        exec_method="_exec_inventory",
        transitions={"*": "SECURITY_SCAN"},
        default_next="SECURITY_SCAN",
        timeout_ms=5000.0,
        description="Manage inventory levels, alerts, reorder points",
    ),
    "CRM": UnifiedDAGNode(
        name="CRM",
        agent_id="A11",
        exec_method="_exec_crm",
        transitions={"*": "SECURITY_SCAN"},
        default_next="SECURITY_SCAN",
        timeout_ms=5000.0,
        description="Process CRM pipeline stages, conversions, forecasts",
    ),
    "TASK": UnifiedDAGNode(
        name="TASK",
        agent_id="A12",
        exec_method="_exec_task",
        transitions={"*": "SECURITY_SCAN"},
        default_next="SECURITY_SCAN",
        timeout_ms=5000.0,
        description="Schedule tasks, detect conflicts, assign priorities",
    ),
    "REPORT": UnifiedDAGNode(
        name="REPORT",
        agent_id="A13",
        exec_method="_exec_report",
        transitions={"*": "SECURITY_SCAN"},
        default_next="SECURITY_SCAN",
        timeout_ms=5000.0,
        description="Generate reports, dashboards, summaries",
    ),
    "NOTIFICATION": UnifiedDAGNode(
        name="NOTIFICATION",
        agent_id="A14",
        exec_method="_exec_notification",
        transitions={"*": "SECURITY_SCAN"},
        default_next="SECURITY_SCAN",
        timeout_ms=3000.0,
        description="Dispatch notifications via configured channels",
    ),
    "ANALYTICS": UnifiedDAGNode(
        name="ANALYTICS",
        agent_id="A15",
        exec_method="_exec_analytics",
        transitions={"*": "SECURITY_SCAN"},
        default_next="SECURITY_SCAN",
        timeout_ms=5000.0,
        description="Compute analytics metrics, trends, insights",
    ),

    # ───────────────────────────────────────────────────────────
    #  PHASE 3C: AUTOMATION EXECUTION PATH
    # ───────────────────────────────────────────────────────────
    "TRIGGER": UnifiedDAGNode(
        name="TRIGGER",
        agent_id="A29",
        exec_method="_exec_trigger",
        transitions={"*": "ACTION"},
        default_next="ACTION",
        timeout_ms=3000.0,
        description="Infer trigger type (manual/schedule/event/webhook)",
    ),
    "ACTION": UnifiedDAGNode(
        name="ACTION",
        agent_id="A30",
        exec_method="_exec_action",
        transitions={"*": "SCHEDULE"},
        default_next="SCHEDULE",
        timeout_ms=3000.0,
        description="Infer action type (email/http/db/file/webhook/notification/log)",
    ),
    "SCHEDULE": UnifiedDAGNode(
        name="SCHEDULE",
        agent_id="A31",
        exec_method="_exec_schedule",
        transitions={"*": "CONDITION"},
        default_next="CONDITION",
        timeout_ms=3000.0,
        description="Parse schedule (manual/interval/cron/once)",
    ),
    "CONDITION": UnifiedDAGNode(
        name="CONDITION",
        agent_id="A32",
        exec_method="_exec_condition",
        transitions={"*": "AUTO_NAME"},
        default_next="AUTO_NAME",
        timeout_ms=3000.0,
        description="Extract conditions and build logic tree",
    ),
    "AUTO_NAME": UnifiedDAGNode(
        name="AUTO_NAME",
        agent_id="A33",
        exec_method="_exec_auto_name",
        transitions={"*": "WORKFLOW_SERIAL"},
        default_next="WORKFLOW_SERIAL",
        timeout_ms=2000.0,
        description="Generate workflow name and slug",
    ),
    "WORKFLOW_SERIAL": UnifiedDAGNode(
        name="WORKFLOW_SERIAL",
        agent_id="A34",
        exec_method="_exec_workflow_serial",
        transitions={"*": "SECURITY_SCAN"},
        default_next="SECURITY_SCAN",
        timeout_ms=3000.0,
        description="Serialize workflow spec to YAML/JSON/executable",
    ),

    # ───────────────────────────────────────────────────────────
    #  PHASE 3D: REASONING EXECUTION PATH
    # ───────────────────────────────────────────────────────────
    "PROBLEM_DETECT": UnifiedDAGNode(
        name="PROBLEM_DETECT",
        agent_id="A35",
        exec_method="_exec_problem_detect",
        transitions={"*": "STEP_DECOMPOSE"},
        default_next="STEP_DECOMPOSE",
        timeout_ms=3000.0,
        description="Detect problem type and estimate complexity",
    ),
    "STEP_DECOMPOSE": UnifiedDAGNode(
        name="STEP_DECOMPOSE",
        agent_id="A36",
        exec_method="_exec_step_decompose",
        transitions={"*": "TEMPLATE_REASON"},
        default_next="TEMPLATE_REASON",
        timeout_ms=5000.0,
        description="Decompose problem into ordered reasoning steps",
    ),
    "TEMPLATE_REASON": UnifiedDAGNode(
        name="TEMPLATE_REASON",
        agent_id="A37",
        exec_method="_exec_template_reason",
        transitions={"*": "CONFIDENCE"},
        default_next="CONFIDENCE",
        timeout_ms=8000.0,
        description="Apply template-based reasoning to steps",
    ),
    "CONFIDENCE": UnifiedDAGNode(
        name="CONFIDENCE",
        agent_id="A38",
        exec_method="_exec_confidence",
        transitions={"*": "CONCLUSION"},
        default_next="CONCLUSION",
        timeout_ms=3000.0,
        description="Estimate confidence score and recommendation",
    ),
    "CONCLUSION": UnifiedDAGNode(
        name="CONCLUSION",
        agent_id="A39",
        exec_method="_exec_conclusion",
        transitions={"*": "SECURITY_SCAN"},
        default_next="SECURITY_SCAN",
        timeout_ms=3000.0,
        description="Extract final conclusion with supporting evidence",
    ),

    # ───────────────────────────────────────────────────────────
    #  PHASE 4: VALIDATE
    # ───────────────────────────────────────────────────────────
    "SECURITY_SCAN": UnifiedDAGNode(
        name="SECURITY_SCAN",
        agent_id="A23",
        exec_method="_exec_security_scan",
        transitions={"*": "SYNTAX_VALIDATE"},
        default_next="SYNTAX_VALIDATE",
        timeout_ms=5000.0,
        description="Scan code for security vulnerabilities and threats",
    ),
    "SYNTAX_VALIDATE": UnifiedDAGNode(
        name="SYNTAX_VALIDATE",
        agent_id="A24",
        exec_method="_exec_syntax_validate",
        transitions={"*": "RISK_CALC"},
        default_next="RISK_CALC",
        timeout_ms=3000.0,
        description="Validate syntax and detect structural errors",
    ),
    "RISK_CALC": UnifiedDAGNode(
        name="RISK_CALC",
        agent_id="A27",
        exec_method="_exec_risk_calc",
        transitions={"*": "FIX_SUGGEST"},
        default_next="FIX_SUGGEST",
        timeout_ms=3000.0,
        description="Calculate aggregate risk score from security + syntax results",
    ),
    "FIX_SUGGEST": UnifiedDAGNode(
        name="FIX_SUGGEST",
        agent_id="A28",
        exec_method="_exec_fix_suggest",
        transitions={"*": "EVIDENCE_COLLECT"},
        default_next="EVIDENCE_COLLECT",
        timeout_ms=3000.0,
        description="Suggest fixes for detected issues, prioritize auto-fixable ones",
    ),

    # ───────────────────────────────────────────────────────────
    #  PHASE 5: VERDICT
    # ───────────────────────────────────────────────────────────
    "EVIDENCE_COLLECT": UnifiedDAGNode(
        name="EVIDENCE_COLLECT",
        agent_id="A41",
        exec_method="_exec_evidence_collect",
        transitions={"*": "CONSENSUS_RESOLVE"},
        default_next="CONSENSUS_RESOLVE",
        timeout_ms=5000.0,
        description="Collect evidence for/against the generated output",
    ),
    "CONSENSUS_RESOLVE": UnifiedDAGNode(
        name="CONSENSUS_RESOLVE",
        agent_id="A42",
        exec_method="_exec_consensus_resolve",
        transitions={"*": "VERDICT"},
        default_next="VERDICT",
        timeout_ms=5000.0,
        description="Resolve consensus from collected evidence; flag if AI arbitration needed",
    ),
    "VERDICT": UnifiedDAGNode(
        name="VERDICT",
        agent_id="A43",
        exec_method="_exec_verdict",
        transitions={
            "approved": "SANDBOX",
            "rejected": "LEDGER_ROLLBACK",
            "needs_review": "SANDBOX",
        },
        default_next="SANDBOX",
        timeout_ms=8000.0,
        max_retries=3,
        description="Render final verdict (deterministic or AI-arbitrated)",
    ),

    # ───────────────────────────────────────────────────────────
    #  PHASE 6: SANDBOX, LEDGER, MEMORY (v16 compat)
    # ───────────────────────────────────────────────────────────
    "VISUAL_BYPASS": UnifiedDAGNode(
        name="VISUAL_BYPASS",
        exec_method="_exec_visual_bypass",
        transitions={
            "success": "MEMORY_SAVE",
            "fallback": "PLAN",
        },
        default_next="PLAN",
        criticality_skip=[3],
        max_retries=1,
        timeout_ms=10000.0,
        description="Visual bypass: generate UI code without Z3/AC-3 solver (v16 compat)",
    ),
    "SANDBOX": UnifiedDAGNode(
        name="SANDBOX",
        exec_method="_exec_sandbox",
        transitions={
            "PASS": "LEDGER_COMMIT",
            "FAIL_K_PATH": "PARTIAL_REASONING",
            "FAIL": "LEDGER_ROLLBACK",
        },
        default_next="LEDGER_ROLLBACK",
        timeout_ms=30000.0,
        description="Execute code in isolated sandbox for validation (v16 compat)",
    ),
    "PARTIAL_REASONING": UnifiedDAGNode(
        name="PARTIAL_REASONING",
        exec_method="_exec_partial_reasoning",
        transitions={"*": "DONE"},
        default_next="DONE",
        timeout_ms=5000.0,
        description="Build partial reasoning response for K-Path failure (v16 compat)",
    ),
    "LEDGER_COMMIT": UnifiedDAGNode(
        name="LEDGER_COMMIT",
        exec_method="_exec_ledger_commit",
        transitions={"*": "THEOREM_SAVE"},
        default_next="THEOREM_SAVE",
        timeout_ms=3000.0,
        description="Commit validated code to Merkle ledger (v16 compat)",
    ),
    "LEDGER_ROLLBACK": UnifiedDAGNode(
        name="LEDGER_ROLLBACK",
        exec_method="_exec_ledger_rollback",
        transitions={"*": "DONE"},
        default_next="DONE",
        timeout_ms=3000.0,
        description="Rollback failed code from Merkle ledger (v16 compat)",
    ),
    "THEOREM_SAVE": UnifiedDAGNode(
        name="THEOREM_SAVE",
        exec_method="_exec_theorem_save",
        transitions={"*": "MEMORY_SAVE"},
        default_next="MEMORY_SAVE",
        timeout_ms=2000.0,
        description="Save proven solution to theorem cache (v16 compat)",
    ),
    "MEMORY_SAVE": UnifiedDAGNode(
        name="MEMORY_SAVE",
        exec_method="_exec_memory_save",
        transitions={"*": "DONE"},
        default_next="DONE",
        timeout_ms=3000.0,
        description="Save to SmartMemory for learning and cache (v16 compat)",
    ),
    "DONE": UnifiedDAGNode(
        name="DONE",
        exec_method="_exec_done",
        transitions={},
        default_next="",
        timeout_ms=1000.0,
        description="Terminal node: build and return final response",
    ),
}


# ═══════════════════════════════════════════════════════════════
#  PARALLEL GROUPS
# ═══════════════════════════════════════════════════════════════

PARALLEL_GROUPS: Dict[str, ParallelGroup] = {
    "INTENT_PARALLEL": ParallelGroup(
        name="INTENT_PARALLEL",
        nodes=["ENTITY_EXTRACT", "TARGET_RESOLVE"],
        merge_node="CRITICALITY_SCORE",
        timeout_ms=5000.0,
        cancel_on_error=False,
    ),
    "CONTEXT_PARALLEL": ParallelGroup(
        name="CONTEXT_PARALLEL",
        nodes=["MEMORY_COLLECT", "SEMANTIC_PREP"],
        merge_node="RELEVANCE_SCORE",
        timeout_ms=8000.0,
        cancel_on_error=False,
    ),
    "EXECUTE_PARALLEL": ParallelGroup(
        name="EXECUTE_PARALLEL",
        nodes=["CODE_GENERATE", "OP_ROUTE", "TRIGGER", "PROBLEM_DETECT"],
        merge_node="SECURITY_SCAN",
        timeout_ms=20000.0,
        cancel_on_error=True,
    ),
}


# ═══════════════════════════════════════════════════════════════
#  EXECUTION PATH DEFINITIONS
# ═══════════════════════════════════════════════════════════════

CODE_PIPELINE: List[str] = [
    "CODE_GENERATE", "CODE_REFACTOR", "CODE_OPTIMIZE",
    "CODE_FIX", "CODE_SCAFFOLD",
]

CODE_TO_DEFENSIVE: Dict[str, str] = {
    "CODE_GENERATE": "DEFENSIVE_INJECT",
    "CODE_REFACTOR": "DEFENSIVE_INJECT",
    "CODE_OPTIMIZE": "DEFENSIVE_INJECT",
    "CODE_FIX": "DEFENSIVE_INJECT",
    "CODE_SCAFFOLD": "DEFENSIVE_INJECT",
}

BIZ_PIPELINE: Dict[str, str] = {
    "OP_ROUTE": "INVOICE",  # default, but OP_ROUTE transitions determine actual target
}

BIZ_AGENTS: List[str] = [
    "INVOICE", "INVENTORY", "CRM", "TASK",
    "REPORT", "NOTIFICATION", "ANALYTICS",
]

AUTO_PIPELINE: List[str] = [
    "TRIGGER", "ACTION", "SCHEDULE",
    "CONDITION", "AUTO_NAME", "WORKFLOW_SERIAL",
]

REASON_PIPELINE: List[str] = [
    "PROBLEM_DETECT", "STEP_DECOMPOSE", "TEMPLATE_REASON",
    "CONFIDENCE", "CONCLUSION",
]


# ═══════════════════════════════════════════════════════════════
#  ROUTING MAP — Intent → Execution Path
# ═══════════════════════════════════════════════════════════════

INTENT_TO_CODE_OP: Dict[str, str] = {
    "CREATE": "CODE_GENERATE",
    "REFACTOR": "CODE_REFACTOR",
    "OPTIMIZE": "CODE_OPTIMIZE",
    "DEBUG": "CODE_FIX",
}

INTENT_TO_BIZ_TYPE: Dict[str, str] = {
    "SEARCH": "analytics",
    "ANALYZE": "analytics",
}


# ═══════════════════════════════════════════════════════════════
#  BACKWARD COMPAT: DAG v16 nodes that map to unified nodes
# ═══════════════════════════════════════════════════════════════

V16_TO_UNIFIED_NODE_MAP: Dict[str, str] = {
    "CACHE_CHECK": "CACHE_CHECK",
    "INTENT": "INTENT_CLASSIFY",
    "CONTEXT_PREPARE": "CONTEXT_COMPRESS",
    "AST_ANALYZE": "AST_ANALYZE",
    "THEOREM_CACHE": "THEOREM_CACHE",
    "ROUTE": "ROUTE",
    "CRITICALITY_ROUTE": "CRITICALITY_SCORE",
    "PLAN": "PLAN",
    "SOLVER_VERIFY": "SOLVER_VERIFY",
    "EXECUTE_STEPS": "CODE_GENERATE",
    "VALIDATE": "SYNTAX_VALIDATE",
    "ABORTIVE": "ABORTIVE",
    "SANDBOX": "SANDBOX",
    "PARTIAL_REASONING": "PARTIAL_REASONING",
    "LEDGER_COMMIT": "LEDGER_COMMIT",
    "LEDGER_ROLLBACK": "LEDGER_ROLLBACK",
    "THEOREM_SAVE": "THEOREM_SAVE",
    "MEMORY_SAVE": "MEMORY_SAVE",
    "DONE": "DONE",
    "VISUAL_BYPASS": "VISUAL_BYPASS",
}


# ═══════════════════════════════════════════════════════════════
#  NODE COUNTS (for reporting)
# ═══════════════════════════════════════════════════════════════

def count_unified_nodes() -> Dict[str, int]:
    """Return a breakdown of unified DAG node counts by section."""
    sections = {
        "cache_entry": 2,      # CACHE_CHECK, BILINGUAL_ROUTE
        "understand": 5,       # INTENT_CLASSIFY + INTENT_PARALLEL_GATE + ENTITY_EXTRACT + TARGET_RESOLVE + CRITICALITY_SCORE
        "context": 6,          # CONTEXT_PARALLEL_GATE + MEMORY_COLLECT + SEMANTIC_PREP + RELEVANCE_SCORE + CONTEXT_COMPRESS + CONTEXT_PREFETCH
        "v16_compat": 5,       # AST_ANALYZE, THEOREM_CACHE, ROUTE, ROUTE_DECISION, PLAN
        "v16_solver": 2,       # SOLVER_VERIFY, ABORTIVE
        "code_path": 6,        # CODE_GENERATE through DEFENSIVE_INJECT
        "biz_path": 8,         # OP_ROUTE + 7 business agents
        "auto_path": 6,        # TRIGGER through WORKFLOW_SERIAL
        "reason_path": 5,      # PROBLEM_DETECT through CONCLUSION
        "validate": 4,         # SECURITY_SCAN, SYNTAX_VALIDATE, RISK_CALC, FIX_SUGGEST
        "verdict": 3,          # EVIDENCE_COLLECT, CONSENSUS_RESOLVE, VERDICT
        "ledger": 5,           # SANDBOX, PARTIAL_REASONING, LEDGER_COMMIT/ROLLBACK, THEOREM_SAVE, MEMORY_SAVE
        "terminal": 2,         # VISUAL_BYPASS, DONE
    }
    sections["total"] = sum(sections.values())
    return sections
