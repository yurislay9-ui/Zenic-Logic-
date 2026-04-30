from pydantic import BaseModel, Field
from typing import Literal, Optional
from enum import Enum

class OperationType(str, Enum):
    CREATE = "CREATE"
    REFACTOR = "REFACTOR"
    DELETE = "DELETE"
    SEARCH = "SEARCH"

class GoalType(str, Enum):
    COMPLEXITY_REDUCTION = "COMPLEXITY_REDUCTION"
    MODERN_PATTERN = "MODERN_PATTERN"
    BUG_FIX = "BUG_FIX"
    FEATURE_ADD = "FEATURE_ADD"

class CriticalityLevel(int, Enum):
    FAST_STANDARD = 1
    DEEP_MODERATE = 2
    SURGICAL_CRITICAL = 3

class RoutePath(str, Enum):
    FAST_PATH = "FAST_PATH_REGEX"
    DEEP_PATH = "DEEP_PATH_CONSTRAINT"

class IntentPayload(BaseModel):
    op: OperationType
    target: str = "unknown"
    goal: GoalType
    scrap_query: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

class RoutingPayload(BaseModel):
    intent: IntentPayload
    criticality: CriticalityLevel
    route: RoutePath
    reason: str = ""

class PlanStep(BaseModel):
    step_id: int
    action: Literal["SCRAPE_GITHUB", "REPLACE_AST_NODE", "INSERT_AST_NODE", "DELETE_AST_NODE"]
    target_node_name: str
    source: Literal["LOCAL_GRAPH", "GITHUB_SCRAPE"] = "LOCAL_GRAPH"
    constraints: dict = Field(default_factory=dict)

class ExecutionPlan(BaseModel):
    plan_id: str
    steps: list[PlanStep]
    solver_status: Literal["PROVEN", "TIMEOUT", "HEURISTIC_FALLBACK"]

class SandboxResult(BaseModel):
    status: Literal["PASS", "FAIL_SYNTAX", "FAIL_DEPENDENCY", "TIMEOUT"]
    error_message: str = ""
    error_node: Optional[str] = None

class MerkleNode(BaseModel):
    file_path: str
    hash_sha256: str

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str

class ChatRequest(BaseModel):
    model: str = "titan-omniscale-x"
    messages: list[ChatMessage]
    temperature: Optional[float] = 0.1
