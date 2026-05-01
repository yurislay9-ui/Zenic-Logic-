"""
TITAN OMNISCALE X - Data Types & Payloads v13

Operation types, goal types, criticality levels, route paths,
and data payloads for communication between pipeline levels.
"""


# ============================================================
#  OPERACIONES Y OBJETIVOS
# ============================================================

class OperationType:
    CREATE = "CREATE"
    REFACTOR = "REFACTOR"
    DELETE = "DELETE"
    SEARCH = "SEARCH"
    ANALYZE = "ANALYZE"
    EXPLAIN = "EXPLAIN"
    DEBUG = "DEBUG"
    OPTIMIZE = "OPTIMIZE"


class GoalType:
    COMPLEXITY_REDUCTION = "COMPLEXITY_REDUCTION"
    MODERN_PATTERN = "MODERN_PATTERN"
    BUG_FIX = "BUG_FIX"
    FEATURE_ADD = "FEATURE_ADD"
    SECURITY_HARDEN = "SECURITY_HARDEN"
    PERFORMANCE = "PERFORMANCE"
    READABILITY = "READABILITY"


class CriticalityLevel:
    FAST_STANDARD = 1
    DEEP_MODERATE = 2
    SURGICAL_CRITICAL = 3


class RoutePath:
    FAST_PATH = "FAST_PATH_REGEX"
    DEEP_PATH = "DEEP_PATH_CONSTRAINT"
    SURGICAL_PATH = "SURGICAL_PATH_FULL"


# ============================================================
#  PAYLOADS DE COMUNICACION ENTRE NIVELES
# ============================================================

class IntentPayload:
    def __init__(self, op=OperationType.SEARCH, target="unknown",
                 goal=GoalType.FEATURE_ADD, scrap_query="", confidence=0.0,
                 language="python", raw_code="", context=""):
        self.op = op
        self.target = target
        self.goal = goal
        self.scrap_query = scrap_query
        self.confidence = confidence
        self.language = language
        self.raw_code = raw_code
        self.context = context


class RoutingPayload:
    def __init__(self, intent=None, criticality=CriticalityLevel.FAST_STANDARD,
                 route=RoutePath.FAST_PATH, reason=""):
        self.intent = intent or IntentPayload()
        self.criticality = criticality
        self.route = route
        self.reason = reason


class PlanStep:
    def __init__(self, step_id=0, action="ANALYZE_CODE", target_node_name="",
                 source="LOCAL_GRAPH", constraints=None):
        self.step_id = step_id
        self.action = action
        self.target_node_name = target_node_name
        self.source = source
        self.constraints = constraints or {}


class ExecutionPlan:
    def __init__(self, plan_id="", steps=None, solver_status="HEURISTIC_FALLBACK",
                 solver_proof=None, mcts_simulations=0, mcts_depth_reached=0):
        self.plan_id = plan_id
        self.steps = steps or []
        self.solver_status = solver_status
        self.solver_proof = solver_proof  # Resultado real del solver (Z3 o AC-3)
        self.mcts_simulations = mcts_simulations
        self.mcts_depth_reached = mcts_depth_reached


class SandboxResult:
    def __init__(self, status="PASS", error_message="", error_node=None,
                 warnings=None, metrics=None, paths_explored=0, paths_pruned=0):
        self.status = status
        self.error_message = error_message
        self.error_node = error_node
        self.warnings = warnings or []
        self.metrics = metrics or {}
        self.paths_explored = paths_explored
        self.paths_pruned = paths_pruned


class MerkleNode:
    def __init__(self, file_path="", hash_sha256="", parent_hash="",
                 timestamp=0, operation=""):
        self.file_path = file_path
        self.hash_sha256 = hash_sha256
        self.parent_hash = parent_hash
        self.timestamp = timestamp
        self.operation = operation


class ChatMessage:
    def __init__(self, role="user", content=""):
        self.role = role
        self.content = content


class ChatRequest:
    def __init__(self, model="titan-omniscale-x", messages=None, temperature=0.1,
                 max_tokens=2000, stream=False):
        self.model = model
        self.messages = messages or []
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stream = stream
