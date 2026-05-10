"""
Shared imports and constants for surgical_agent_parts.
"""

import logging
from typing import Dict, List

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import IntentInput, IntentOutput
from src.core.agents.prompts import AgentPrompts
from src.core.agents.intent_shared import (
    VALID_OPERATIONS, VALID_GOALS, VALID_LANGUAGES,
    OP_KEYWORDS, GOAL_KEYWORDS,
    EXT_LANG_MAP, FENCE_LANG_MAP,
)

logger = logging.getLogger(__name__)

# ── Compact keyword maps for surgical routing (EN + ES) ──
# Uses the shared OP_KEYWORDS/GOAL_KEYWORDS as base, with compact aliases

OP_KW: Dict[str, List[str]] = OP_KEYWORDS
GOAL_KW: Dict[str, List[str]] = GOAL_KEYWORDS

CRIT_KW: Dict[str, List[str]] = {
    "critical": ["auth","login","password","token","jwt","secret","crypto","ssl","permiso"],
    "moderate": ["database","db","migration","config","base de datos","migracion"],
}

# Extension/language maps — now imported from intent_shared
EXT_LANG = EXT_LANG_MAP
FENCE_LANG = FENCE_LANG_MAP
