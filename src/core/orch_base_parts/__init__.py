"""
BaseOrchestrator — facade re-exporting all sub-modules.

Backward-compatible: ``from src.core.orchestrator_base import BaseOrchestrator``
still works exactly as before.
"""

from ._init_mixin import InitMixin
from ._api_mixin import APIMixin
from ._phase7_mixin import Phase7Mixin
from ._phase8_mixin import Phase8Mixin
from ._compat_mixin import CompatMixin
from ._imports import (
    logger, Path,
    initialize_databases,
    SemanticParser, MacroRouter, GraphASTEngine, APAPlanner,
    GitHubScrapAgent, ASTSurgeon, ReflexionSandbox,
    MerkleLedger, TheoremCache,
    get_isolation_manager,
    AbortiveProtocol, PartialReasoningManager,
    CodeGenerator, CodeTransformer, AnalysisUtils,
    ThinkingEngine, AppGenerator,
    AutomationEngine, SchemaDesigner,
    ExecutorRegistry, get_default_registry, LogicBuilder, AuthService,
    ReasoningEngine,
    ChainValidator, ChainExecutor, RecoveryAction,
    AgentRunner,
    SurgicalAgent, ReasoningAgent, BusinessLogicAgent,
    CodeAgent, AutomationAgent, ValidationAgent,
)


class BaseOrchestrator(InitMixin, APIMixin, Phase7Mixin, Phase8Mixin, CompatMixin):
    """
    Shared base for TitanOrchestrator and DAGOrchestrator.

    Contains all initialization, public API, backward-compat delegation,
    and shared properties that were previously duplicated between the two
    orchestrator implementations.
    """


__all__ = [
    "BaseOrchestrator",
    # Re-export all imports for backward compatibility
    "logger", "Path",
    "initialize_databases",
    "SemanticParser", "MacroRouter", "GraphASTEngine", "APAPlanner",
    "GitHubScrapAgent", "ASTSurgeon", "ReflexionSandbox",
    "MerkleLedger", "TheoremCache",
    "get_isolation_manager",
    "AbortiveProtocol", "PartialReasoningManager",
    "CodeGenerator", "CodeTransformer", "AnalysisUtils",
    "ThinkingEngine", "AppGenerator",
    "AutomationEngine", "SchemaDesigner",
    "ExecutorRegistry", "get_default_registry", "LogicBuilder", "AuthService",
    "ReasoningEngine",
    "ChainValidator", "ChainExecutor", "RecoveryAction",
    "AgentRunner",
    "SurgicalAgent", "ReasoningAgent", "BusinessLogicAgent",
    "CodeAgent", "AutomationAgent", "ValidationAgent",
]
