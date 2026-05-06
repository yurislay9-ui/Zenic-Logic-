"""
V18 Pipeline Orchestrator — Connects all single-responsibility agents.

6-Phase Pipeline (FULLY WIRED):
  Phase 1: UNDERSTAND  (A48 → A01 → A02 → A03 → A04)
  Phase 2: CONTEXT     (A05 → A06 → A07 → A08)
  Phase 3: EXECUTE     (A16 → A09-A15/A17-A22 → A22 DefensiveInjector)
  Phase 4: VALIDATE    (A23 → A24 → A27 → A28)
  Phase 5: VERDICT     (A41 → A42 → A43 if needed)
  Phase 6: AUDIT       (A45 → A46 → A47)

All phases are deterministic except Phase 5 when AI arbitration is needed.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .understanding import (
    IntentClassifier,
    EntityExtractor,
    TargetResolver,
    CriticalityScorer,
    BilingualRouter,
)
from .memory import (
    MemoryCollector,
    RelevanceScorer,
    ContextCompressor,
    ContextPrefetcher,
)
from .business import (
    InvoiceProcessor,
    InventoryManager,
    CRMPipeline,
    TaskScheduler,
    ReportGenerator,
    NotificationDispatcher,
    DataAnalyzer,
    OperationRouter,
)
from .code_ops import (
    CodeGenerator,
    CodeRefactorer,
    CodeOptimizer,
    CodeFixer,
    ProjectScaffolder,
    DefensiveInjector,
)
from .validation import (
    SecurityScanner,
    SyntaxValidator,
    RiskCalculator,
    FixSuggester,
)
from .verdict import (
    VerdictEngineV18,
    EvidenceCollectorV18,
    ConsensusResolverV18,
)
from .schemas import (
    Verdict, VerdictOutput, ConsensusResult, Evidence,
    IntentResult, EntityResult, TargetResult, CriticalityResult,
    LanguageResult, SecurityResult, SyntaxResult, RiskResult,
)
from .resilience import (
    CircuitBreakerManager,
    BulkheadManager,
    GlobalHealthMonitor,
    AuditLogger,
)


class PipelineOrchestrator:
    """
    V18 Pipeline Orchestrator — Fully Wired.

    Orchestrates the 6-phase pipeline with all single-responsibility agents.
    Every phase is deterministic except Phase 5 (verdict) when AI is needed.

    Architecture:
        Phase 1: UNDERSTAND — Classify intent, extract entities, resolve target, score criticality
        Phase 2: CONTEXT — Collect memory, score relevance, compress, prefetch
        Phase 3: EXECUTE — Route to domain agent, execute, inject defensive patterns
        Phase 4: VALIDATE — Security scan, syntax validate, calculate risk, suggest fixes
        Phase 5: VERDICT — Collect evidence, resolve consensus, AI arbiter if needed
        Phase 6: AUDIT — Health monitor, audit log, circuit breaker management
    """

    def __init__(self, mini_ai=None, smart_memory=None, semantic_engine=None):
        # ── Shared infrastructure ──
        self._cb_manager = CircuitBreakerManager()
        self._bulkhead_manager = BulkheadManager()
        self._health_monitor = GlobalHealthMonitor()
        self._audit_logger = AuditLogger()
        self._mini_ai = mini_ai
        self._smart_memory = smart_memory
        self._semantic_engine = semantic_engine

        # Common kwargs for all agents
        self._ik = dict(
            circuit_breaker_manager=self._cb_manager,
            bulkhead_manager=self._bulkhead_manager,
            health_monitor=self._health_monitor,
            audit_logger=self._audit_logger,
        )

        # ── Phase 1: Understanding ──
        self._bilingual_router = BilingualRouter(**self._ik)
        self._intent_classifier = IntentClassifier(**self._ik)
        self._entity_extractor = EntityExtractor(**self._ik)
        self._target_resolver = TargetResolver(**self._ik)
        self._criticality_scorer = CriticalityScorer(**self._ik)

        # ── Phase 2: Context ──
        self._memory_collector = MemoryCollector(**self._ik)
        self._relevance_scorer = RelevanceScorer(**self._ik)
        self._context_compressor = ContextCompressor(**self._ik)
        self._context_prefetcher = ContextPrefetcher(**self._ik)

        # Wire memory/semantic dependencies
        self._memory_collector.wire(smart_memory, semantic_engine)

        # ── Phase 3: Execute — Business ──
        self._operation_router = OperationRouter(**self._ik)
        self._invoice_processor = InvoiceProcessor(**self._ik)
        self._inventory_manager = InventoryManager(**self._ik)
        self._crm_pipeline = CRMPipeline(**self._ik)
        self._task_scheduler = TaskScheduler(**self._ik)
        self._report_generator = ReportGenerator(**self._ik)
        self._notification_dispatcher = NotificationDispatcher(**self._ik)
        self._data_analyzer = DataAnalyzer(**self._ik)

        # ── Phase 3: Execute — Code ──
        self._code_generator = CodeGenerator(**self._ik)
        self._code_refactorer = CodeRefactorer(**self._ik)
        self._code_optimizer = CodeOptimizer(**self._ik)
        self._code_fixer = CodeFixer(**self._ik)
        self._project_scaffolder = ProjectScaffolder(**self._ik)
        self._defensive_injector = DefensiveInjector(**self._ik)

        # ── Phase 4: Validate ──
        self._security_scanner = SecurityScanner(**self._ik)
        self._syntax_validator = SyntaxValidator(**self._ik)
        self._risk_calculator = RiskCalculator(**self._ik)
        self._fix_suggester = FixSuggester(**self._ik)

        # ── Phase 5: Verdict ──
        self._evidence_collector = EvidenceCollectorV18(**self._ik)
        self._consensus_resolver = ConsensusResolverV18(**self._ik)
        self._verdict_engine = VerdictEngineV18(mini_ai=mini_ai, **self._ik)

        # ── Business agent registry for routing ──
        self._business_agents = {
            "A09_InvoiceProcessor": self._invoice_processor,
            "A10_InventoryManager": self._inventory_manager,
            "A11_CRMPipeline": self._crm_pipeline,
            "A12_TaskScheduler": self._task_scheduler,
            "A13_ReportGenerator": self._report_generator,
            "A14_NotificationDispatcher": self._notification_dispatcher,
            "A15_DataAnalyzer": self._data_analyzer,
        }

    # ══════════════════════════════════════════════════════════
    #  WIRING METHODS
    # ══════════════════════════════════════════════════════════

    def wire_mini_ai(self, mini_ai) -> None:
        """Connect MiniAIEngine for verdict arbitration."""
        self._mini_ai = mini_ai
        self._verdict_engine.wire_mini_ai(mini_ai)

    def wire_smart_memory(self, smart_memory) -> None:
        """Connect SmartMemory for context pipeline."""
        self._smart_memory = smart_memory
        self._memory_collector.wire(smart_memory, self._semantic_engine)

    def wire_semantic_engine(self, semantic_engine) -> None:
        """Connect SemanticEngine for relevance scoring."""
        self._semantic_engine = semantic_engine
        self._memory_collector.wire(self._smart_memory, semantic_engine)
        self._relevance_scorer.wire(semantic_engine)

    # ══════════════════════════════════════════════════════════
    #  MAIN PIPELINE
    # ══════════════════════════════════════════════════════════

    async def execute(self, message: str, code: str = "",
                      language: str = "python") -> Dict[str, Any]:
        """
        Execute the full 6-phase pipeline.

        Returns a dict with all phase results + timing.
        """
        start_time = time.monotonic()
        phases = {}

        # ══════════════════════════════════════════════════════
        #  PHASE 1: UNDERSTAND
        # ══════════════════════════════════════════════════════
        phase_start = time.monotonic()

        lang_result = self._run_agent(self._bilingual_router, message)
        intent_result = self._run_agent(self._intent_classifier, message)
        entity_result = self._run_agent(self._entity_extractor, message)
        target_result = self._run_agent(self._target_resolver, {
            "entity_result": entity_result,
            "message": message,
        })
        criticality_result = self._run_agent(self._criticality_scorer, {
            "intent_result": intent_result,
            "target_result": target_result,
            "message": message,
        })

        phases["understand"] = (time.monotonic() - phase_start) * 1000

        # ══════════════════════════════════════════════════════
        #  PHASE 2: CONTEXT
        # ══════════════════════════════════════════════════════
        phase_start = time.monotonic()

        memory_entries = self._run_agent(self._memory_collector, {
            "intent_result": intent_result,
            "target_result": target_result,
        })
        scored_entries = self._run_agent(self._relevance_scorer, {
            "memory_entries": memory_entries,
            "intent_result": intent_result,
        })
        compressed_context = self._run_agent(self._context_compressor, {
            "scored_entries": scored_entries,
            "operation": intent_result.operation if intent_result else "SEARCH",
            "goal": intent_result.goal if intent_result else "FEATURE_ADD",
        })
        prefetch_result = self._run_agent(self._context_prefetcher, {
            "intent_result": intent_result,
            "memory_entries": memory_entries,
        })

        phases["context"] = (time.monotonic() - phase_start) * 1000

        # ══════════════════════════════════════════════════════
        #  PHASE 3: EXECUTE
        # ══════════════════════════════════════════════════════
        phase_start = time.monotonic()

        execution_result = None
        execution_type = "none"

        # Determine if this is a code operation or business operation
        operation = intent_result.operation if intent_result else "SEARCH"
        goal = intent_result.goal if intent_result else "FEATURE_ADD"

        if operation in ("CREATE", "OPTIMIZE", "REFACTOR", "DEBUG"):
            # ── Code operation path ──
            execution_result, execution_type = self._execute_code_operation(
                operation, goal, message, code, language, criticality_result
            )
        else:
            # ── Business operation path ──
            execution_result, execution_type = self._execute_business_operation(
                message, intent_result
            )

        # ── Defensive injection (if code was produced) ──
        defensive_result = None
        if execution_result and hasattr(execution_result, 'code') and execution_result.code:
            crit_level = criticality_result.level if criticality_result else 1
            adjustments = criticality_result.adjustments if criticality_result else {}
            defensive_result = self._run_agent(self._defensive_injector, {
                "code": execution_result.code,
                "language": language,
                "criticality_level": crit_level,
                "adjustments": adjustments,
            })

        phases["execute"] = (time.monotonic() - phase_start) * 1000

        # ══════════════════════════════════════════════════════
        #  PHASE 4: VALIDATE
        # ══════════════════════════════════════════════════════
        phase_start = time.monotonic()

        # Validate the final code (after defensive injection)
        code_to_validate = ""
        if defensive_result and hasattr(defensive_result, 'code'):
            code_to_validate = defensive_result.code
        elif execution_result and hasattr(execution_result, 'code'):
            code_to_validate = execution_result.code
        else:
            code_to_validate = code  # Fall back to input code

        security_result = self._run_agent(self._security_scanner, {
            "code": code_to_validate,
            "language": language,
        })
        syntax_result = self._run_agent(self._syntax_validator, {
            "code": code_to_validate,
            "language": language,
        })
        risk_result = self._run_agent(self._risk_calculator, {
            "security_result": security_result,
            "syntax_result": syntax_result,
        })
        fix_result = self._run_agent(self._fix_suggester, {
            "risk_result": risk_result,
        })

        phases["validate"] = (time.monotonic() - phase_start) * 1000

        # ══════════════════════════════════════════════════════
        #  PHASE 5: VERDICT
        # ══════════════════════════════════════════════════════
        phase_start = time.monotonic()

        # Collect evidence
        evidence = self._run_agent(self._evidence_collector, {
            "security_result": security_result,
            "syntax_result": syntax_result,
            "criticality_result": criticality_result,
            "intent_result": intent_result,
        })

        # Resolve consensus
        consensus = self._run_agent(self._consensus_resolver, evidence)

        # If AI arbitration needed, ask VerdictEngine
        if consensus and isinstance(consensus, ConsensusResult) and consensus.needs_llm:
            verdict_result = self._run_agent(self._verdict_engine, {
                "question": f"Should code for {operation}/{goal} be approved?",
                "consensus_result": consensus,
                "evidence_for": consensus.evidence_for,
                "evidence_against": consensus.evidence_against,
            })
        else:
            if isinstance(consensus, ConsensusResult):
                verdict_result = VerdictOutput(
                    verdict=consensus.verdict,
                    confidence=consensus.confidence,
                    source="deterministic_consensus",
                    llm_used=False,
                )
            else:
                verdict_result = VerdictOutput(
                    verdict=Verdict.NO,
                    confidence=0.1,
                    source="fallback",
                    llm_used=False,
                )

        phases["verdict"] = (time.monotonic() - phase_start) * 1000

        # ══════════════════════════════════════════════════════
        #  PHASE 6: AUDIT
        # ══════════════════════════════════════════════════════
        # (Already handled by each agent's BaseAgent.run())
        phases["audit"] = 0.0

        total_ms = (time.monotonic() - start_time) * 1000

        return {
            "verdict": verdict_result,
            "intent": intent_result,
            "criticality": criticality_result,
            "target": target_result,
            "compressed_context": compressed_context,
            "execution_type": execution_type,
            "execution_result": execution_result,
            "defensive_result": defensive_result,
            "security": security_result,
            "syntax": syntax_result,
            "risk": risk_result,
            "fix_suggestions": fix_result,
            "consensus": consensus,
            "evidence_count": len(evidence) if evidence else 0,
            "duration_ms": round(total_ms, 1),
            "phases": {k: round(v, 1) for k, v in phases.items()},
        }

    # ══════════════════════════════════════════════════════════
    #  CODE OPERATION EXECUTION
    # ══════════════════════════════════════════════════════════

    def _execute_code_operation(
        self,
        operation: str,
        goal: str,
        message: str,
        code: str,
        language: str,
        criticality_result: Any,
    ) -> tuple:
        """Execute a code operation based on intent."""
        if operation == "CREATE":
            if goal == "FEATURE_ADD" and "project" in message.lower():
                result = self._run_agent(self._project_scaffolder, {
                    "requirements": message,
                    "language": language,
                })
                return result, "scaffold"
            else:
                result = self._run_agent(self._code_generator, {
                    "requirements": message,
                    "language": language,
                })
                return result, "generate"

        elif operation == "REFACTOR":
            result = self._run_agent(self._code_refactorer, {
                "existing_code": code,
                "requirements": message,
                "language": language,
            })
            return result, "refactor"

        elif operation == "OPTIMIZE":
            result = self._run_agent(self._code_optimizer, {
                "existing_code": code,
                "language": language,
            })
            return result, "optimize"

        elif operation == "DEBUG":
            result = self._run_agent(self._code_fixer, {
                "existing_code": code,
                "language": language,
            })
            return result, "fix"

        else:
            # Default: generate
            result = self._run_agent(self._code_generator, {
                "requirements": message,
                "language": language,
            })
            return result, "generate"

    # ══════════════════════════════════════════════════════════
    #  BUSINESS OPERATION EXECUTION
    # ══════════════════════════════════════════════════════════

    def _execute_business_operation(
        self,
        message: str,
        intent_result: Any,
    ) -> tuple:
        """Execute a business operation by routing to the correct agent."""
        # Route to the correct agent
        route = self._run_agent(self._operation_router, {
            "type": "custom",  # Will be inferred from message
            "data": {"description": message},
            "context": {},
            "description": message,
        })

        if route and hasattr(route, 'target_agent'):
            agent = self._business_agents.get(route.target_agent)
            if agent:
                result = self._run_agent(agent, route.transformed_input.get("data", {}))
                return result, f"business:{route.target_agent}"

        # Fallback: data analyzer
        result = self._run_agent(self._data_analyzer, {
            "data": [message],
            "metrics": ["count"],
        })
        return result, "business:fallback"

    # ══════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════

    def _run_agent(self, agent, input_data: Any) -> Any:
        """Run an agent and extract the data from the result envelope."""
        result = agent.run(input_data)
        if isinstance(result, dict):
            return result.get("data")
        return result

    def get_system_status(self) -> Dict[str, Any]:
        """Get full system status."""
        return {
            "circuit_breakers": self._cb_manager.all_stats(),
            "bulkheads": self._bulkhead_manager.all_stats(),
            "health": self._health_monitor.system_health(),
            "audit": self._audit_logger.stats,
            "verdict_engine": self._verdict_engine.verdict_stats,
            "mini_ai_loaded": (
                self._mini_ai is not None
                and getattr(self._mini_ai, 'is_loaded', False)
            ),
            "agents_wired": {
                "understanding": 5,
                "memory": 4,
                "business": 8,
                "code_ops": 6,
                "validation": 4,
                "verdict": 3,
                "total": 30,
            },
        }
