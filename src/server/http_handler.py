"""
TITAN OMNISCALE X v16 - Unified HTTP Handler

Handler HTTP compatible con la API de OpenAI. Unifica la logica
que antes estaba duplicada entre main.py (Kivy) y main_headless.py (Termux).
"""

from .http_parts import *  # noqa: F401,F403
from .http_parts import TitanHTTPHandler  # explicit

__all__ = ["TitanHTTPHandler"]
