"""
TITAN OMNISCALE X - Reference Resolver (Anaphora / Ellipsis)

Resolves vague references in follow-up messages to concrete values
from the conversation state. This enables interactions like:

  User: "Crea un endpoint de login"        → CREATE/login/python
  User: "Ahora haz lo mismo pero en Kotlin" → CREATE/login/kotlin
  User: "Y en Go?"                         → CREATE/login/go
  User: "Ahora refactorízalo"              → REFACTOR/login/go

Without this resolver, SurgicalAgent treats each message in isolation
and classifies "lo mismo" as SEARCH with target="unknown".

Architecture:
  - Pure functions: no LLM calls, no I/O, no side effects
  - Pattern-based: regex + keyword matching for known anaphoric expressions
  - Language-aware: handles Spanish + English references
  - Conservative: only resolves when confidence is high

Supported patterns (ES/EN):
  - "lo mismo" / "the same"                 → inherit operation + target
  - "lo mismo pero en Kotlin"               → inherit op + target, change lang
  - "hazlo de nuevo" / "do it again"        → inherit operation + target + lang
  - "ahora en Go" / "now in Go"             → inherit op + target, change lang
  - "también en Kotlin" / "also in Kotlin"   → inherit op + target, change lang
  - "otro endpoint" / "another endpoint"    → inherit op, new target
  - "refactorízalo" / "refactor it"         → change op, inherit target
  - Language-switch only: "en Kotlin"        → inherit everything, change lang
"""

import re
import logging
from typing import Optional, Tuple

from .conversation_state import ConversationState

logger = logging.getLogger(__name__)

# ── Known programming languages (lowercase) ─────────────────────
_KNOWN_LANGUAGES = frozenset({
    "python", "py", "kotlin", "kt", "go", "golang",
    "javascript", "js", "typescript", "ts", "java",
    "rust", "rs", "c", "cpp", "c++", "csharp", "c#", "cs",
    "ruby", "rb", "php", "swift", "dart", "scala",
    "html", "css", "sql", "shell", "bash", "sh",
    "r", "lua", "perl", "elixir", "erlang", "haskell",
})

# Normalized language map (alias → canonical)
_LANG_NORMALIZE = {
    "py": "python", "kt": "kotlin", "golang": "go",
    "js": "javascript", "ts": "typescript",
    "rs": "rust", "rb": "ruby", "cs": "csharp",
    "c#": "csharp", "c++": "cpp", "sh": "shell",
}

# ── Anaphoric patterns (ES + EN) ───────────────────────────────
# Each pattern returns a tuple: (inherit_operation, inherit_target, force_lang)

# Pattern: "lo mismo" / "lo mismo pero en X"
_RE_LO_MISMO = re.compile(
    r"\b(lo mismo|la misma|los mismos|las mismas)\b",
    re.IGNORECASE,
)

# Pattern: "the same" / "same thing"
_RE_THE_SAME = re.compile(
    r"\b(the same|same thing|same as|do the same)\b",
    re.IGNORECASE,
)

# Pattern: "hazlo de nuevo" / "do it again" / "again"
_RE_AGAIN = re.compile(
    r"\b(hazlo de nuevo|otra vez|de nuevo|hacerlo de nuevo|"
    r"do it again|once more|again)\b",
    re.IGNORECASE,
)

# Pattern: "también en X" / "also in X" / "now in X" / "en X"
_RE_LANG_SWITCH = re.compile(
    r"\b(tambi[eé]n en|ahora en|tambi[eé]n con|ahora con|"
    r"also in|now in|in|using|con)\s+"
    r"([a-z+#]+)\b",
    re.IGNORECASE,
)

# Pattern: Language at end of message: "en Kotlin", "in Go"
_RE_LANG_AT_END = re.compile(
    r"\b(en|in)\s+([a-z+#]+)\s*[.!]?\s*$",
    re.IGNORECASE,
)

# Pattern: "refactorízalo" / "refactor it" / "optimízalo" / "optimize it"
_RE_OP_CHANGE = re.compile(
    r"\b(refactor[ií]zalo|refactor[ií]salo|refactor[ií]zarla|refactor[ií]sarla|refactor it|"
    r"optim[ií]zalo|optim[ií]salo|optim[ií]zarla|optim[ií]sarla|optimize it|"
    r"arr[eé]glalo|fix it|mejor[aá]lo|improve it|"
    r"expl[ií]calo|explain it|anal[ií]zalo|analyze it|"
    r"dep[uú]ralo|debug it|elim[ií]nalo|delete it)\b",
    re.IGNORECASE,
)

# Map from matched op-change to operation (includes accented variants)
_OP_CHANGE_MAP = {
    "refactorizalo": "REFACTOR", "refactorízalo": "REFACTOR",
    "refactorizarla": "REFACTOR", "refactorízarla": "REFACTOR",
    "refactorisalo": "REFACTOR", "refactorísalo": "REFACTOR",
    "refactorisarla": "REFACTOR", "refactorísarla": "REFACTOR",
    "refactor it": "REFACTOR",
    "optimizalo": "OPTIMIZE", "optimízalo": "OPTIMIZE",
    "optimizarla": "OPTIMIZE", "optimízarla": "OPTIMIZE",
    "optimisalo": "OPTIMIZE", "optimísalo": "OPTIMIZE",
    "optimisarla": "OPTIMIZE", "optimísarla": "OPTIMIZE",
    "optimize it": "OPTIMIZE",
    "arreglalo": "DEBUG", "arreglalo": "DEBUG", "fix it": "DEBUG",
    "mejoralo": "OPTIMIZE", "mejóralo": "OPTIMIZE", "improve it": "OPTIMIZE",
    "explicalo": "EXPLAIN", "explícalo": "EXPLAIN", "explain it": "EXPLAIN",
    "analizalo": "ANALYZE", "analízalo": "ANALYZE", "analyze it": "ANALYZE",
    "depuralo": "DEBUG", "depúralo": "DEBUG", "debug it": "DEBUG",
    "eliminalo": "DELETE", "elimínalo": "DELETE", "delete it": "DELETE",
}


def _extract_language(text: str) -> Optional[str]:
    """Extract a programming language mentioned in the text.

    Checks language-switch patterns first, then falls back to
    scanning for known language names anywhere in the text.
    """
    # 1. Try "en/ahora/también in/using X" patterns
    for pattern in (_RE_LANG_SWITCH, _RE_LANG_AT_END):
        m = pattern.search(text)
        if m:
            lang_raw = m.group(2).lower().strip()
            if lang_raw in _KNOWN_LANGUAGES:
                return _LANG_NORMALIZE.get(lang_raw, lang_raw)

    # 2. Scan for any known language word in the message
    words = set(re.findall(r'[a-z+#]+', text.lower()))
    found = words & _KNOWN_LANGUAGES
    if found:
        # Pick the most specific one (longest match, e.g. "typescript" > "ts")
        best = max(found, key=len)
        return _LANG_NORMALIZE.get(best, best)

    return None


def _detect_op_change(text: str) -> Optional[str]:
    """Detect an operation change request (refactor/optimize/debug/explain)."""
    m = _RE_OP_CHANGE.search(text)
    if m:
        key = m.group(1).lower()
        return _OP_CHANGE_MAP.get(key)
    return None


def resolve_references(
    message: str,
    state: ConversationState,
) -> Tuple[str, Optional[str], Optional[str], str]:
    """Resolve anaphoric references in a follow-up message.

    This is the main entry point. It examines the user's message
    and the ConversationState to produce a resolved message.

    Args:
        message: The user's current message.
        state: The ConversationState from the previous turn.

    Returns:
        Tuple of:
          - enriched_message: The original message with context appended
          - resolved_target: The target to use (or None to let SurgicalAgent decide)
          - resolved_language: The language to use (or None)
          - resolution_source: How the resolution was done ("none"/"anaphora"/"lang_switch"/"op_change")
    """
    if not state.is_fresh() or not state.has_context():
        return message, None, None, "none"

    msg_lower = message.lower().strip()
    resolved_target = None
    resolved_language = None
    resolution_source = "none"
    context_hints = []

    # ── Check 1: "lo mismo" / "the same" → inherit op + target ──
    if _RE_LO_MISMO.search(msg_lower) or _RE_THE_SAME.search(msg_lower):
        resolved_target = state.last_target
        context_hints.append(f"same_as_prev={state.last_target}")
        resolution_source = "anaphora"
        # Also check if they want a different language
        lang = _extract_language(message)
        if lang:
            resolved_language = lang
            context_hints.append(f"lang_switch={lang}")

    # ── Check 2: "hazlo de nuevo" / "do it again" → inherit everything ──
    elif _RE_AGAIN.search(msg_lower):
        resolved_target = state.last_target
        resolved_language = state.last_language
        context_hints.append(f"repeat_prev={state.last_target}/{state.last_language}")
        resolution_source = "anaphora"

    # ── Check 3: Operation change ("refactorízalo") → inherit target, change op ──
    elif _detect_op_change(msg_lower):
        resolved_target = state.last_target
        lang = _extract_language(message)
        if lang:
            resolved_language = lang
        else:
            resolved_language = state.last_language
        context_hints.append(f"op_change_target={state.last_target}")
        resolution_source = "op_change"

    # ── Check 4: Language switch ("ahora en Kotlin", "en Go") ──
    elif _extract_language(message):
        lang = _extract_language(message)
        # Only resolve if the language is DIFFERENT from the last one
        # (same language = probably not a follow-up, just a new request in that lang)
        if lang != state.last_language:
            resolved_target = state.last_target
            resolved_language = lang
            context_hints.append(f"lang_switch={state.last_target}:{state.last_language}→{lang}")
            resolution_source = "lang_switch"
        elif state.last_target and len(message.split()) <= 6:
            # Short message in same language: "en python" → probably referring to previous
            resolved_target = state.last_target
            resolved_language = state.last_language
            resolution_source = "lang_switch"

    # ── Build enriched message ──
    if context_hints:
        enriched = f"{message} [resolved: {', '.join(context_hints)}]"
        logger.info(
            "ReferenceResolver: resolved '%s' → target='%s' lang='%s' (source=%s)",
            message[:60], resolved_target, resolved_language, resolution_source,
        )
    else:
        enriched = message

    return enriched, resolved_target, resolved_language, resolution_source
