"""Shared imports and constants for governor_parts."""

import os
import gc
import time
import threading
import logging

try:
    import resource
except ImportError:
    resource = None  # Not available on Android/Termux

from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)
