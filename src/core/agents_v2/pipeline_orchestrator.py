"""
V18 Pipeline Orchestrator — Connects all single-responsibility agents.

.. deprecated::
    This module is NOT wired into the main execution path.
    The ``DAGOrchestrator`` and ``UnifiedDAGOrchestrator`` handle request
    processing.  This class is retained for future v18 pipeline activation
    but should not be imported or used in production code paths.

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
from typing import Any

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
from .automation import (
    TriggerInferrer,
    ActionInferrer,
    ScheduleParser,
    ConditionExtractor,
    AutomationNamer,
    WorkflowSerializer,
)
from .reasoning import (
    ProblemDetector,
    StepDecomposer,
    TemplateReasoner,
    ConfidenceEstimator,
    ConclusionExtractor,
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
    WorkflowSpec, ProblemType, ReasoningResult, ConfidenceResult, DecomposedSteps, Conclusion,
    TriggerSpec, ActionSpec, ScheduleSpec, ConditionResult, NameResult,
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

    def __init__(self, mini_ai=None, smart_memory=None, semantic_engine=None) -> None:
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
        self._context_prefetcher.wire(smart_memory=smart_memory, semantic_engine=semantic_engine)

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

        # ── Phase 3: Execute — Automation ──
        self._trigger_inferrer = TriggerInferrer(**self._ik)
        self._action_inferrer = ActionInferrer(**self._ik)
        self._schedule_parser = ScheduleParser(**self._ik)
        self._condition_extractor = ConditionExtractor(**self._ik)
        self._automation_namer = AutomationNamer(**self._ik)
        self._workflow_serializer = WorkflowSerializer(**self._ik)

        # ── Phase 3: Execute — Reasoning ──
        self._problem_detector = ProblemDetector(**self._ik)
        self._step_decomposer = StepDecomposer(**self._ik)
        self._template_reasoner = TemplateReasoner(**self._ik)
        self._confidence_estimator = ConfidenceEstimator(**self._ik)
        self._conclusion_extractor = ConclusionExtractor(**self._ik)

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
        self._context_prefetcher.wire(smart_memory=smart_memory, semantic_engine=self._semantic_engine)

    def wire_semantic_engine(self, semantic_engine) -> None:
        """Connect SemanticEngine for relevance scoring."""
        self._semantic_engine = semantic_engine
        self._memory_collector.wire(self._smart_memory, semantic_engine)
        self._relevance_scorer.wire(semantic_engine)
        self._context_prefetcher.wire(smart_memory=self._smart_memory, semantic_engine=semantic_engine)

    # ══════════════════════════════════════════════════════════
    #  MAIN PIPELINE
    # ══════════════════════════════════════════════════════════

    async def execute(self, message: str, code: str = "",
                      language: str = "python") -> dict[str, Any]:
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

        # Determine if this is a code operation, business operation, automation, or reasoning
        operation = intent_result.operation if intent_result else "SEARCH"
        goal = intent_result.goal if intent_result else "FEATURE_ADD"
        
        # Check for automation/reasoning intent from message keywords
        is_automation = self._is_automation_intent(message, intent_result)
        is_reasoning = self._is_reasoning_intent(message, intent_result)

        if operation in ("CREATE", "OPTIMIZE", "REFACTOR", "DEBUG") and not is_automation:
            # ── Code operation path ──
            execution_result, execution_type = self._execute_code_operation(
                operation, goal, message, code, language, criticality_result
            )
        elif is_automation:
            # ── Automation path ──
            execution_result, execution_type = self._execute_automation_operation(
                message, intent_result
            )
        elif is_reasoning:
            # ── Reasoning path ──
            execution_result, execution_type = self._execute_reasoning_operation(
                message, intent_result
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
        # Collect all validation issues for FixSuggester
        all_issues = []
        if security_result and isinstance(security_result, SecurityResult):
            all_issues.extend(security_result.threats)
        if syntax_result and isinstance(syntax_result, SyntaxResult):
            all_issues.extend(syntax_result.errors)
        
        fix_result = self._run_agent(self._fix_suggester, {
            "issues": all_issues,
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
        # Infer business type from message keywords (not hardcoded "custom")
        biz_type = self._infer_business_type(message)
        
        # Route to the correct agent
        route = self._run_agent(self._operation_router, {
            "type": biz_type,
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
    #  AUTOMATION OPERATION EXECUTION
    # ══════════════════════════════════════════════════════════

    def _execute_automation_operation(
        self,
        message: str,
        intent_result: Any,
    ) -> tuple:
        """Execute an automation workflow: infer trigger → action → schedule → conditions → name → serialize."""
        # Step 1: Infer trigger type
        trigger_result = self._run_agent(self._trigger_inferrer, message)
        
        # Step 2: Infer action type
        action_result = self._run_agent(self._action_inferrer, {
            "description": message,
            "trigger_type": trigger_result.type if trigger_result else "manual",
        })
        
        # Step 3: Parse schedule (if applicable)
        schedule_result = self._run_agent(self._schedule_parser, {
            "description": message,
            "trigger_type": trigger_result.type if trigger_result else "manual",
        })
        
        # Step 4: Extract conditions
        condition_result = self._run_agent(self._condition_extractor, {
            "description": message,
        })
        
        # Step 5: Generate name
        name_result = self._run_agent(self._automation_namer, {
            "description": message,
            "trigger_type": trigger_result.type if trigger_result else "manual",
            "action_type": action_result.type if action_result else "log",
        })
        
        # Step 6: Serialize workflow
        workflow_result = self._run_agent(self._workflow_serializer, {
            "name": name_result.name if name_result else "unnamed_workflow",
            "slug": name_result.slug if name_result else "unnamed_workflow",
            "trigger": trigger_result,
            "action": action_result,
            "schedule": schedule_result,
            "conditions": condition_result.conditions if condition_result else [],
        })
        
        return workflow_result, "automation"

    # ══════════════════════════════════════════════════════════
    #  REASONING OPERATION EXECUTION
    # ══════════════════════════════════════════════════════════

    def _execute_reasoning_operation(
        self,
        message: str,
        intent_result: Any,
    ) -> tuple:
        """Execute a reasoning pipeline: detect problem → decompose → reason → confidence → conclusion."""
        # Step 1: Detect problem type
        problem_result = self._run_agent(self._problem_detector, message)
        
        # Step 2: Decompose into steps
        steps_result = self._run_agent(self._step_decomposer, {
            "query": message,
            "problem_type": problem_result.type if problem_result else "general",
            "complexity": problem_result.complexity if problem_result else 0.5,
        })
        
        # Step 3: Apply template reasoning
        reasoning_result = self._run_agent(self._template_reasoner, {
            "query": message,
            "problem_type": problem_result.type if problem_result else "general",
            "steps": steps_result.steps if steps_result else [],
        })
        
        # Step 4: Estimate confidence
        confidence_result = self._run_agent(self._confidence_estimator, {
            "reasoning_result": reasoning_result,
            "problem_type": problem_result.type if problem_result else "general",
        })
        
        # Step 5: Extract conclusion
        conclusion_result = self._run_agent(self._conclusion_extractor, {
            "reasoning_result": reasoning_result,
            "confidence_score": confidence_result.score if confidence_result else 0.0,
        })
        
        return conclusion_result, "reasoning"

    # ══════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _is_automation_intent(message: str, intent_result: Any) -> bool:
        """Detect if the user wants an automation/workflow."""
        automation_keywords = [
            "automate", "automation", "workflow", "trigger", "schedule",
            "cron", "webhook", "automatizar", "automatización", "flujo",
            "programar", "tarea programada", "notificación automática",
        ]
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in automation_keywords):
            return True
        # Also check if the intent goal is related to automation
        if intent_result and isinstance(intent_result, IntentResult):
            if intent_result.operation == "CREATE" and "automat" in message.lower():
                return True
        return False

    @staticmethod
    def _is_reasoning_intent(message: str, intent_result: Any) -> bool:
        """Detect if the user needs reasoning/problem-solving."""
        reasoning_keywords = [
            "why does", "explain why", "how to solve", "what causes",
            "root cause", "investigate", "troubleshoot", "reasoning",
            "por qué", "como resolver", "causa raíz", "investigar",
            "analyze problem", "problem solve", "decompose",
        ]
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in reasoning_keywords):
            return True
        # Check if operation is ANALYZE with high complexity
        if intent_result and isinstance(intent_result, IntentResult):
            if intent_result.operation == "ANALYZE" and intent_result.confidence > 0.5:
                return False  # ANALYZE goes to business by default
        return False

    @staticmethod
    def _infer_business_type(message: str) -> str:
        """Infer business operation type from message keywords."""
        msg_lower = message.lower()
        type_keywords = {
            "invoice": ["invoice", "factura", "billing", "cobro", "pago", "receipt"],
            "inventory": ["inventory", "inventario", "stock", "almacen", "product", "producto"],
            "crm": ["crm", "cliente", "customer", "ventas", "sales", "lead", "pipeline"],
            "task": ["task", "tarea", "scheduling", "calendar", "agenda", "appointment"],
            "report": ["report", "reporte", "informe", "dashboard", "resumen", "summary"],
            "notification": ["notification", "notificacion", "alert", "alerta", "notify", "aviso"],
            "analytics": ["analytics", "analisis", "analysis", "statistics", "stats", "metric"],
        }
        for biz_type, keywords in type_keywords.items():
            if any(kw in msg_lower for kw in keywords):
                return biz_type
        return "custom"

    def _run_agent(self, agent, input_data: Any) -> Any:
        """Run an agent and extract the data from the result envelope."""
        result = agent.run(input_data)
        if isinstance(result, dict):
            return result.get("data")
        return result

    def get_system_status(self) -> dict[str, Any]:
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
                "understanding": 5,   # A48, A01-A04
                "memory": 4,          # A05-A08
                "business": 8,        # A09-A16
                "code_ops": 6,        # A17-A22
                "validation": 4,      # A23-A28
                "automation": 6,      # A29-A34
                "reasoning": 5,       # A35-A39
                "verdict": 3,         # A40-A43
                "infrastructure": 4,  # A44-A47 (wired externally)
                "total": 45,          # 45 directly wired + 3 infrastructure = 48
            },
        }
