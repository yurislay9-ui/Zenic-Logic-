"""Shared imports and constants for model_mgr_parts."""

import os
import time
import threading
import logging
import platform
from typing import Optional, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# === Configuration from environment ===
IDLE_TIMEOUT_S = int(os.environ.get("TITAN_MODEL_IDLE_TIMEOUT", "300"))  # 5 min default
RAM_BUDGET_MB = int(os.environ.get("TITAN_RAM_BUDGET_MB", "3072"))  # Max RAM for models
ENABLE_AUTO_UNLOAD = os.environ.get("TITAN_AUTO_UNLOAD", "1") == "1"
ENABLE_LAZY_LOAD = os.environ.get("TITAN_LAZY_LOAD", "1") == "1"
