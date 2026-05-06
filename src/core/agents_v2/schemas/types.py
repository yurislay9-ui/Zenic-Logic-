"""All shared data types for v18 single-responsibility agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ────────────────────────────── Base Types ──────────────────────────────

@dataclass
class AgentResult:
    """Universal result wrapper for all agents."""
    success: bool
    data: Any = None
    source: str = "deterministic"  # "deterministic", "cached", "fallback"
    duration_ms: float = 0.0
    confidence: float = 0.0
    error: str = ""


@dataclass
class AgentMessage:
    """Typed message for inter-agent communication."""
    sender: str
    recipient: str
    message_type: str  # "request", "response", "error", "verdict_needed"
    payload: Dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    timestamp: float = 0.0
    trace_id: str = ""


# ────────────────────────────── Layer 1: Understanding ──────────────────────────────

@dataclass
class LanguageResult:
    """A48 BilingualRouter output."""
    lang: str = "en"
    text: str = ""
    confidence: float = 1.0
    source: str = "deterministic"


@dataclass
class IntentResult:
    """A01 IntentClassifier output."""
    operation: str = "SEARCH"      # CREATE|REFACTOR|DELETE|SEARCH|ANALYZE|EXPLAIN|DEBUG|OPTIMIZE
    goal: str = "FEATURE_ADD"      # COMPLEXITY_REDUCTION|MODERN_PATTERN|BUG_FIX|FEATURE_ADD|SECURITY_HARDEN|PERFORMANCE|READABILITY
    confidence: float = 0.0
    source: str = "deterministic"
    evidence: Dict[str, float] = field(default_factory=dict)


@dataclass
class EntityResult:
    """A02 EntityExtractor output."""
    files: List[str] = field(default_factory=list)
    langs: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    code_blocks: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class TargetResult:
    """A03 TargetResolver output."""
    target_file: str = ""
    language: str = "python"
    scope: str = "new_module"  # "new_module", "existing_file", "project"
    source: str = "deterministic"


@dataclass
class CriticalityResult:
    """A04 CriticalityScorer output."""
    level: int = 1                # 1=FAST_STANDARD, 2=DEEP_MODERATE, 3=SURGICAL_CRITICAL
    path: str = "fast_standard"
    reason: str = ""
    confidence: float = 0.0
    adjustments: Dict[str, Any] = field(default_factory=dict)
    source: str = "deterministic"


# ────────────────────────────── Layer 2: Memory & Context ──────────────────────────────

@dataclass
class MemoryEntries:
    """A05 MemoryCollector output."""
    working: List[Dict[str, Any]] = field(default_factory=list)
    long_term: List[Dict[str, Any]] = field(default_factory=list)
    episodic: List[Dict[str, Any]] = field(default_factory=list)
    procedural: List[Dict[str, Any]] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class ScoredEntry:
    """A single scored memory entry."""
    content: str = ""
    importance: float = 0.0
    recency: float = 0.0
    relevance: float = 0.0
    combined_score: float = 0.0
    source_type: str = ""  # "working", "long_term", "episodic", "procedural"


@dataclass
class ScoredEntries:
    """A06 RelevanceScorer output."""
    entries: List[ScoredEntry] = field(default_factory=list)
    deduplicated: bool = False
    source: str = "deterministic"


@dataclass
class CompressedContext:
    """A07 ContextCompressor output."""
    text: str = ""
    ratio: float = 1.0
    tokens_used: int = 0
    budget: int = 500
    design_system_preserved: bool = False
    source: str = "deterministic"


@dataclass
class PrefetchResult:
    """A08 ContextPrefetcher output."""
    prefetched: List[Dict[str, Any]] = field(default_factory=list)
    hints: List[str] = field(default_factory=list)
    source: str = "deterministic"


# ────────────────────────────── Layer 3: Business ──────────────────────────────

@dataclass
class BusinessData:
    """Input for business operation agents."""
    type: str = ""   # invoice|inventory|crm|task|report|notification|analytics|custom
    data: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class InvoiceResult:
    """A09 InvoiceProcessor output."""
    totals: Dict[str, float] = field(default_factory=dict)
    tax: float = 0.0
    discounts: float = 0.0
    valid: bool = True
    source: str = "deterministic"


@dataclass
class InventoryResult:
    """A10 InventoryManager output."""
    levels: Dict[str, int] = field(default_factory=dict)
    alerts: List[str] = field(default_factory=list)
    reorder: List[str] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class CRMResult:
    """A11 CRMPipeline output."""
    stages: List[Dict[str, Any]] = field(default_factory=list)
    conversions: Dict[str, float] = field(default_factory=dict)
    forecasts: Dict[str, Any] = field(default_factory=dict)
    source: str = "deterministic"


@dataclass
class TaskResult:
    """A12 TaskScheduler output."""
    schedule: List[Dict[str, Any]] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    priorities: Dict[str, int] = field(default_factory=dict)
    source: str = "deterministic"


@dataclass
class ReportResult:
    """A13 ReportGenerator output."""
    content: str = ""
    format: str = "text"
    charts: List[str] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class NotificationResult:
    """A14 NotificationDispatcher output."""
    sent: bool = False
    channel: str = ""
    status: str = "pending"
    source: str = "deterministic"


@dataclass
class AnalyticsResult:
    """A15 DataAnalyzer output."""
    metrics: Dict[str, float] = field(default_factory=dict)
    trends: List[str] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class RoutedOperation:
    """A16 OperationRouter output."""
    target_agent: str = ""
    transformed_input: Dict[str, Any] = field(default_factory=dict)
    source: str = "deterministic"


# ────────────────────────────── Layer 4: Code ──────────────────────────────

@dataclass
class CodeRequest:
    """Input for code operation agents."""
    task: str = "generate"  # generate|refactor|optimize|fix|scaffold
    requirements: str = ""
    language: str = "python"
    existing_code: str = ""
    constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CodeResult:
    """A17-A22 code agents output."""
    code: str = ""
    language: str = "python"
    files: List[Dict[str, str]] = field(default_factory=list)  # [{path, content}]
    changes: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    fixes: List[str] = field(default_factory=list)
    injected_patterns: List[str] = field(default_factory=list)
    audit_entries: List[str] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class ScaffoldResult:
    """A21 ProjectScaffolder output."""
    files: List[Dict[str, str]] = field(default_factory=list)
    structure: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    source: str = "deterministic"


# ────────────────────────────── Layer 5: Validation ──────────────────────────────

@dataclass
class ValidationIssue:
    """A single validation finding."""
    severity: str = "info"  # error|warning|info
    code: str = ""
    message: str = ""
    line: int = 0
    suggestion: str = ""


@dataclass
class SecurityResult:
    """A23 SecurityScanner output."""
    safe: bool = True
    threats: List[ValidationIssue] = field(default_factory=list)
    risk_score: float = 0.0
    source: str = "deterministic"


@dataclass
class SyntaxResult:
    """A24 SyntaxValidator output."""
    valid: bool = True
    errors: List[ValidationIssue] = field(default_factory=list)
    line_numbers: List[int] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class ChainResult:
    """A25 ChainValidator output."""
    valid: bool = True
    incompatibilities: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class ConfigResult:
    """A26 ConfigValidator output."""
    valid: bool = True
    issues: List[ValidationIssue] = field(default_factory=list)
    defaults_applied: List[str] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class RiskResult:
    """A27 RiskCalculator output."""
    score: float = 0.0
    level: str = "low"  # low|medium|high|critical
    recommendations: List[str] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class FixSuggestions:
    """A28 FixSuggester output."""
    suggestions: List[str] = field(default_factory=list)
    priorities: List[str] = field(default_factory=list)
    auto_fixable: List[str] = field(default_factory=list)
    source: str = "deterministic"


# ────────────────────────────── Layer 6: Automation ──────────────────────────────

@dataclass
class AutoDescription:
    """Input for automation agents."""
    description: str = ""
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TriggerSpec:
    """A29 TriggerInferrer output."""
    type: str = "manual"  # manual|schedule|event|webhook
    config: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    source: str = "deterministic"


@dataclass
class ActionSpec:
    """A30 ActionInferrer output."""
    type: str = "log"  # email|http|db|file|webhook|notification|transform|schedule|log
    config: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    source: str = "deterministic"


@dataclass
class ScheduleSpec:
    """A31 ScheduleParser output."""
    type: str = "manual"  # manual|interval|cron
    cron: str = ""
    interval_seconds: int = 0
    description: str = ""
    source: str = "deterministic"


@dataclass
class ConditionResult:
    """A32 ConditionExtractor output."""
    conditions: List[str] = field(default_factory=list)
    logic_tree: Dict[str, Any] = field(default_factory=dict)
    source: str = "deterministic"


@dataclass
class NameResult:
    """A33 AutomationNamer output."""
    name: str = ""
    slug: str = ""
    source: str = "deterministic"


@dataclass
class WorkflowSpec:
    """A34 WorkflowSerializer output."""
    yaml: str = ""
    json_spec: str = ""
    executable: Dict[str, Any] = field(default_factory=dict)
    source: str = "deterministic"


# ────────────────────────────── Layer 7: Reasoning ──────────────────────────────

@dataclass
class ProblemType:
    """A35 ProblemDetector output."""
    type: str = "general"  # api|auth|database|invoice|inventory|crm|automation|general
    subtype: str = ""
    complexity: float = 0.5  # 0.0-1.0
    source: str = "deterministic"


@dataclass
class ReasoningStep:
    """A single reasoning step."""
    step_number: int = 0
    description: str = ""
    conclusion: str = ""
    confidence: float = 0.0


@dataclass
class ReasoningResult:
    """A37 TemplateReasoner output."""
    answer: str = ""
    template_used: str = ""
    confidence: float = 0.0
    steps: List[ReasoningStep] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class ConfidenceResult:
    """A38 ConfidenceEstimator output."""
    score: float = 0.0
    factors: List[str] = field(default_factory=list)
    recommendation: str = "proceed"  # proceed|caution|reject
    source: str = "deterministic"


@dataclass
class DecomposedSteps:
    """A36 StepDecomposer output."""
    steps: List[ReasoningStep] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    order: List[int] = field(default_factory=list)
    source: str = "deterministic"


@dataclass
class Conclusion:
    """A39 ConclusionExtractor output."""
    text: str = ""
    supported_by: List[str] = field(default_factory=list)
    strength: float = 0.0  # 0.0-1.0
    source: str = "deterministic"


# ────────────────────────────── Layer 8: Verdict ──────────────────────────────

class Verdict(str, Enum):
    """The only things the AI can output."""
    YES = "YES"
    NO = "NO"


class EvidenceType(str, Enum):
    """Types of evidence."""
    AST_VALIDATION = "AST_VALIDATION"
    PATTERN_MATCH = "PATTERN_MATCH"
    SECURITY_CHECK = "SECURITY_CHECK"
    TYPE_SAFETY = "TYPE_SAFETY"
    SYNTAX_VALID = "SYNTAX_VALID"
    SEMANTIC_SIMILARITY = "SEMANTIC_SIMILARITY"
    CACHE_HIT = "CACHE_HIT"
    REGEX_MATCH = "REGEX_MATCH"
    KEYWORD_CLASSIFY = "KEYWORD_CLASSIFY"
    STRUCTURAL_MATCH = "STRUCTURAL_MATCH"
    RULE_ENGINE = "RULE_ENGINE"
    SANDBOX_PASS = "SANDBOX_PASS"


@dataclass
class Evidence:
    """A piece of evidence for or against a decision."""
    evidence_type: EvidenceType = EvidenceType.KEYWORD_CLASSIFY
    favors: str = "YES"  # "YES" or "NO"
    weight: float = 0.5
    source: str = ""
    detail: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConsensusResult:
    """A42 ConsensusResolver output."""
    verdict: Verdict = Verdict.NO
    confidence: float = 0.0
    score: float = 0.0
    evidence_for: List[Evidence] = field(default_factory=list)
    evidence_against: List[Evidence] = field(default_factory=list)
    needs_llm: bool = False
    signals_count: int = 0
    unanimous: bool = False
    source: str = "deterministic"


@dataclass
class VerdictInput:
    """A43 VerdictEngine input."""
    question: str = ""
    evidence_for: List[Evidence] = field(default_factory=list)
    evidence_against: List[Evidence] = field(default_factory=list)
    consensus_score: float = 0.0
    context: str = ""
    max_retries: int = 3


@dataclass
class VerdictOutput:
    """A43 VerdictEngine output."""
    verdict: Verdict = Verdict.NO
    confidence: float = 0.0
    source: str = "deterministic"  # "deterministic", "llm_consensus", "fallback_no_model", "fallback_circuit_open"
    evidence_summary: str = ""
    llm_used: bool = False
    llm_raw_response: str = ""
    retry_count: int = 0
    duration_ms: float = 0.0


@dataclass
class PipelineResult:
    """A40 DeterministicPipeline output."""
    classify: Any = None
    extract: Any = None
    pattern: Any = None
    fill: Any = None
    generate: Any = None
    explain: Any = None
    subtask: Any = None
    source: str = "deterministic"


# ────────────────────────────── Layer 9: Infrastructure ──────────────────────────────

# NOTE: CircuitState is defined in resilience/circuit_breaker.py — single source of truth.
# It is re-exported via schemas/__init__.py for convenience.


@dataclass
class HealthSnapshot:
    """A45 HealthMonitor output."""
    healthy: bool = True
    success_rates: Dict[str, float] = field(default_factory=dict)
    latencies: Dict[str, float] = field(default_factory=dict)
    circuit_breaker_states: Dict[str, str] = field(default_factory=dict)
    timestamp: float = 0.0
    source: str = "deterministic"


# NOTE: AuditEntry is defined in resilience/audit_logger.py — single source of truth.
# It is re-exported via schemas/__init__.py for convenience.
