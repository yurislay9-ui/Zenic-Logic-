"""
TITAN OMNISCALE X - Agent Schemas (Pydantic)

Esquemas de entrada/salida para cada agente.
Validación automática de respuestas del LLM.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


# ============================================================
#  INTENT AGENT SCHEMAS
# ============================================================

@dataclass
class IntentInput:
    """Input para IntentAgent."""
    message: str = ""
    context: str = ""


@dataclass
class IntentOutput:
    """Output de IntentAgent."""
    operation: str = "SEARCH"       # CREATE|REFACTOR|DELETE|SEARCH|ANALYZE|EXPLAIN|DEBUG|OPTIMIZE
    goal: str = "FEATURE_ADD"       # COMPLEXITY_REDUCTION|MODERN_PATTERN|BUG_FIX|FEATURE_ADD|SECURITY_HARDEN|PERFORMANCE|READABILITY
    target: str = ""
    language: str = "python"
    entities: Dict[str, Any] = field(default_factory=dict)
    template_type: str = "generic"
    criticality: str = "standard"   # standard|moderate|critical
    confidence: float = 0.0
    source: str = "fallback"        # "llm" or "fallback"


# ============================================================
#  REASONING AGENT SCHEMAS
# ============================================================

@dataclass
class ReasoningInput:
    """Input para ReasoningAgent."""
    query: str = ""
    mode: str = "step_by_step"  # step_by_step|self_reflect|with_context
    context: str = ""
    max_steps: int = 5


@dataclass
class ReasoningStep:
    """Un paso de razonamiento."""
    step_number: int = 0
    description: str = ""
    conclusion: str = ""


@dataclass
class ReasoningOutput:
    """Output de ReasoningAgent."""
    answer: str = ""
    confidence: float = 0.0
    mode: str = "step_by_step"
    steps: List[ReasoningStep] = field(default_factory=list)
    refinements: int = 0
    context_used: List[str] = field(default_factory=list)
    memory_hits: int = 0
    source: str = "fallback"
    total_duration_ms: int = 0


# ============================================================
#  BUSINESS LOGIC AGENT SCHEMAS
# ============================================================

@dataclass
class BusinessInput:
    """Input para BusinessLogicAgent."""
    operation_type: str = ""    # invoice|inventory|crm|task|report|notification|analytics|custom
    data: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class BusinessOutput:
    """Output de BusinessLogicAgent."""
    success: bool = False
    data: Dict[str, Any] = field(default_factory=dict)
    side_effects: List[str] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    source: str = "fallback"


# ============================================================
#  CODE AGENT SCHEMAS
# ============================================================

@dataclass
class CodeInput:
    """Input para CodeAgent."""
    task: str = "generate"      # generate|transform|scaffold|optimize|fix
    requirements: str = ""
    language: str = "python"
    existing_code: str = ""
    constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FileSpec:
    """Especificación de un archivo generado."""
    path: str = ""
    content: str = ""
    language: str = ""


@dataclass
class CodeOutput:
    """Output de CodeAgent."""
    code: str = ""
    language: str = "python"
    files: List[FileSpec] = field(default_factory=list)
    test_code: str = ""
    explanation: str = ""
    source: str = "fallback"


# ============================================================
#  AUTOMATION AGENT SCHEMAS
# ============================================================

@dataclass
class AutomationInput:
    """Input para AutomationAgent."""
    description: str = ""
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TriggerSpec:
    """Especificación de un trigger."""
    type: str = "manual"        # manual|schedule|event|webhook
    config: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class ActionSpec:
    """Especificación de una acción."""
    type: str = "log"           # email|http|db|file|webhook|notification|transform|schedule|log
    config: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class ScheduleSpec:
    """Especificación de programación."""
    type: str = "manual"        # manual|interval|cron|once
    interval_seconds: int = 0
    cron_expression: str = ""
    description: str = ""


@dataclass
class AutomationOutput:
    """Output de AutomationAgent."""
    name: str = "unnamed_automation"
    triggers: List[TriggerSpec] = field(default_factory=list)
    actions: List[ActionSpec] = field(default_factory=list)
    schedule: ScheduleSpec = field(default_factory=ScheduleSpec)
    conditions: List[str] = field(default_factory=list)
    description: str = ""
    source: str = "fallback"


# ============================================================
#  VALIDATION AGENT SCHEMAS
# ============================================================

@dataclass
class ValidationInput:
    """Input para ValidationAgent."""
    target: str = "code"        # code|chain|config
    content: str = ""
    rules: List[str] = field(default_factory=list)
    language: str = "python"


@dataclass
class ValidationIssue:
    """Un problema encontrado por la validación."""
    severity: str = "warning"   # error|warning|info
    code: str = ""
    message: str = ""
    line: int = 0
    suggestion: str = ""


@dataclass
class ValidationOutput:
    """Output de ValidationAgent."""
    is_valid: bool = True
    issues: List[ValidationIssue] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    risk_score: float = 0.0
    source: str = "fallback"
