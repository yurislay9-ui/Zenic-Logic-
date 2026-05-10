"""
TITAN OMNISCALE X - Orchestration Patterns (Facade Module)

Re-exports active orchestration pattern components.

Pattern Catalog:
- EventBus: Observer/Pub-Sub pattern for decoupled event-driven communication
- Mediator: Centralized request/response dispatcher for agent coordination

Usage::

    from src.core.patterns.orchestration import EventBus, Event, EventHandler
    from src.core.patterns.orchestration import Mediator, Request, Response

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
No external dependencies beyond Python stdlib.
"""

# ============================================================
#  EVENT BUS - Observer/Pub-Sub Pattern
# ============================================================

from .event_bus import (
    Event,
    EventBus,
    EventHandler,
)

# ============================================================
#  MEDIATOR - Agent Coordination Pattern
# ============================================================

from .mediator import (
    Mediator,
    Request,
    RequestHandler,
    Response,
)

# ============================================================
#  PUBLIC API
# ============================================================

__all__ = [
    # Event Bus
    "EventBus",
    "EventHandler",
    "Event",
    # Mediator
    "Mediator",
    "Request",
    "Response",
    "RequestHandler",
]
