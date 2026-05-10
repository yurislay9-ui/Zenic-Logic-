"""
GenerativeMixin — LLM-powered generative tasks with structured output.

Extends MiniAIEngine beyond the Binary Arbiter (YES/NO) pattern to support
actual code generation, text completion, and code continuation using Qwen3-0.6B.

Design principles:
  - Uses /no_think suffix (saves 50-100 tokens on ARM)
  - Temperature 0.1 for code (deterministic), 0.15 for text
  - Max 1500 tokens for code, 600 for text
  - Falls back gracefully to None if LLM fails
  - Works with VerdictMixin as validation gate (generate → validate)
"""

import logging
from typing import Optional

from ._imports import MAX_TOKENS_CODE_GENERATE, TEMPERATURE

logger = logging.getLogger(__name__)

# ── System prompts optimized for Qwen3-0.6B ──
# Short, direct prompts work best with small models.
# Avoid complex instructions — 0.6B models struggle with multi-step directions.

CODE_GEN_SYSTEM = (
    "You are a code generator. Output ONLY code inside ```{language} blocks. "
    "No explanations. No comments about what you are doing. Just code."
)

TEXT_GEN_SYSTEM = (
    "You are a helpful assistant. Respond concisely and directly."
)

CODE_COMPLETE_SYSTEM = (
    "You are a code completer. Continue the code from where it stops. "
    "Output ONLY the continuation code, no explanations."
)


class GenerativeMixin:
    """Mixin providing LLM-powered generative capabilities.

    Methods:
      - generate_code(prompt, language): Generate code from description
      - generate_text(prompt): Generate text response
      - complete_code(code, language): Complete partial code
    """

    def generate_code(self, prompt: str, language: str = "python",
                      max_tokens: int = MAX_TOKENS_CODE_GENERATE) -> Optional[str]:
        """Generate code from a natural language prompt using Qwen3-0.6B.

        The prompt should be concise (< 800 chars) for best results with 0.6B models.
        Returns the generated code string, or None if generation fails.

        Usage with VerdictMixin as validation gate:
            raw_code = engine.generate_code("Create a FastAPI auth endpoint", "python")
            if raw_code:
                verdict = engine.verdict(
                    question="Is this generated code safe and correct?",
                    context=raw_code[:200],
                    evidence_for=f"Language: {language}, length: {len(raw_code)}",
                )
                if verdict["verdict"] == "YES":
                    return CodeOutput(code=raw_code, language=language, source="llm")
        """
        if not self.is_loaded:
            logger.debug("GenerativeMixin: Model not loaded, cannot generate code")
            return None

        system_prompt = CODE_GEN_SYSTEM.replace("{language}", language)

        try:
            raw = self._call_llm(
                system_prompt=system_prompt,
                user_prompt=prompt,
                max_tokens=max_tokens,
            )
            if not raw:
                return None

            # Extract code from markdown fences if present
            code = self._extract_code_block(raw, language)
            if code:
                logger.info("GenerativeMixin: Generated %d chars of %s code", len(code), language)
                return code

            # If no code block found, return raw response (may be partial)
            if len(raw.strip()) > 20:
                logger.info("GenerativeMixin: Generated %d chars (no fence)", len(raw))
                return raw.strip()

            return None

        except Exception as e:
            logger.warning("GenerativeMixin: Code generation failed: %s", e)
            return None

    def generate_text(self, prompt: str, max_tokens: int = 600) -> Optional[str]:
        """Generate a text response using Qwen3-0.6B.

        Returns the generated text, or None if generation fails.
        Uses slightly higher temperature (0.15) for more natural text.
        """
        if not self.is_loaded:
            logger.debug("GenerativeMixin: Model not loaded, cannot generate text")
            return None

        try:
            return self._call_llm(
                system_prompt=TEXT_GEN_SYSTEM,
                user_prompt=prompt,
                max_tokens=max_tokens,
            )
        except Exception as e:
            logger.warning("GenerativeMixin: Text generation failed: %s", e)
            return None

    def complete_code(self, code: str, language: str = "python",
                      max_tokens: int = MAX_TOKENS_CODE_GENERATE) -> Optional[str]:
        """Continue/complete partial code using Qwen3-0.6B.

        Takes a code snippet and generates the continuation.
        Returns the continuation only (not the original code), or None.
        """
        if not self.is_loaded:
            logger.debug("GenerativeMixin: Model not loaded, cannot complete code")
            return None

        prompt = f"Continue this {language} code:\n```\n{code}\n```\nContinue from here:"

        try:
            raw = self._call_llm(
                system_prompt=CODE_COMPLETE_SYSTEM,
                user_prompt=prompt,
                max_tokens=max_tokens,
            )
            if not raw:
                return None

            continuation = self._extract_code_block(raw, language) or raw.strip()
            if continuation and len(continuation) > 5:
                logger.info("GenerativeMixin: Completed %d chars of %s code", len(continuation), language)
                return continuation

            return None

        except Exception as e:
            logger.warning("GenerativeMixin: Code completion failed: %s", e)
            return None

    @staticmethod
    def _extract_code_block(text: str, language: str = "") -> Optional[str]:
        """Extract code from markdown fence blocks.

        Handles:
          ```python\ncode\n```
          ```\ncode\n```
          code without fences (returns None — caller decides)
        """
        import re

        # Try to match fenced code block with optional language tag
        pattern = rf'```(?:{re.escape(language)})?\s*\n(.*?)```'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Try generic fence
        match = re.search(r'```\s*\n(.*?)```', text, re.DOTALL)
        if match:
            return match.group(1).strip()

        return None
