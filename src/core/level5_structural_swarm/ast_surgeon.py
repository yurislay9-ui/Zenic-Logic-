import re
import logging

logger = logging.getLogger(__name__)

# Importación condicional: tree-sitter-languages puede no estar en Android
try:
    from tree_sitter_languages import get_parser, get_language
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

# Mapa de queries tree-sitter por lenguaje
LANGUAGE_QUERIES = {
    "python": "(function_definition name: (identifier) @name) (class_definition name: (identifier) @name)",
    "kotlin": "(function_declaration name: (simple_identifier) @name) (class_declaration name: (identifier) @name)",
    "go": "(function_declaration name: (identifier) @name) (method_declaration name: (field_identifier) @name) (type_declaration name: (type_identifier) @name)",
    "javascript": "(function_declaration name: (identifier) @name) (class_declaration name: (identifier) @name)",
}


class ASTSurgeon:
    def mutate_node(self, code: str, target_name: str, new_snippet: str, lang: str) -> str:
        if not HAS_TREE_SITTER:
            return self._text_fallback_replace(code, target_name, new_snippet)

        try:
            parser = get_parser(lang)
            tree = parser.parse(code.encode())
            lang_obj = get_language(lang)
            query_str = LANGUAGE_QUERIES.get(lang, LANGUAGE_QUERIES["python"])
            query = lang_obj.query(query_str)
            for n, _ in query.captures(tree.root_node):
                if target_name in n.text.decode() and n.parent:
                    encoded = code.encode()
                    return encoded[:n.parent.start_byte].decode(errors="replace") + new_snippet + encoded[n.parent.end_byte:].decode(errors="replace")
        except Exception as e:
            logger.debug("AST mutate fallback: %s", e)
            return self._text_fallback_replace(code, target_name, new_snippet)

        return code + "\n" + new_snippet

    def _text_fallback_replace(self, code: str, target_name: str, new_snippet: str) -> str:
        """Reemplazo por texto cuando tree-sitter no está disponible."""
        # Buscar la definición de la función por nombre y reemplazarla
        pattern = rf'(def\s+{re.escape(target_name)}\s*\([^)]*\)[^:]*:.*?)(?=\ndef\s|\nclass\s|\Z)'
        match = re.search(pattern, code, re.DOTALL)
        if match:
            return code[:match.start()] + new_snippet + code[match.end():]
        return code + "\n" + new_snippet
