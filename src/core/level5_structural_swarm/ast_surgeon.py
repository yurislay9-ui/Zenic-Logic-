"""
TITAN OMNISCALE X - AST Surgeon (Pure Python)

Cirujano de AST basado en regex. Sin tree-sitter.
Compatible con Android.
"""
import re
import logging

logger = logging.getLogger(__name__)


class ASTSurgeon:
    def mutate_node(self, code, target_name, new_snippet, lang):
        """Reemplaza una funcion por nombre usando regex."""
        try:
            # Buscar definicion de funcion por nombre
            if lang == "python":
                pattern = rf'(def\s+{re.escape(target_name)}\s*\([^)]*\)[^:]*:.*?)(?=\ndef\s|\nclass\s|\Z)'
            elif lang == "kotlin":
                pattern = rf'(fun\s+{re.escape(target_name)}\s*\([^)]*\)[^{{]*\{{.*?\}})'
            elif lang == "go":
                pattern = rf'(func\s+{re.escape(target_name)}\s*\([^)]*\)[^{{]*\{{.*?\}})'
            else:
                pattern = rf'(function\s+{re.escape(target_name)}\s*\([^)]*\)[^{{]*\{{.*?\}})'

            match = re.search(pattern, code, re.DOTALL)
            if match:
                return code[:match.start()] + new_snippet + code[match.end():]
        except Exception as e:
            logger.debug("AST mutate fallback: %s", e)

        return code + "\n" + new_snippet
