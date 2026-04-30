from tree_sitter_languages import get_parser, get_language

# Mapa de queries tree-sitter por lenguaje
LANGUAGE_QUERIES = {
    "python": "(function_definition name: (identifier) @name) (class_definition name: (identifier) @name)",
    "kotlin": "(function_declaration name: (simple_identifier) @name) (class_declaration name: (identifier) @name)",
    "go": "(function_declaration name: (identifier) @name) (method_declaration name: (field_identifier) @name) (type_declaration name: (type_identifier) @name)",
    "javascript": "(function_declaration name: (identifier) @name) (class_declaration name: (identifier) @name) (arrow_function) @name",
}


class ASTSurgeon:
    def mutate_node(self, code: str, target_name: str, new_snippet: str, lang: str) -> str:
        parser = get_parser(lang)
        tree = parser.parse(code.encode())
        lang_obj = get_language(lang)
        query_str = LANGUAGE_QUERIES.get(lang, LANGUAGE_QUERIES["python"])
        try:
            query = lang_obj.query(query_str)
            for n, _ in query.captures(tree.root_node):
                if target_name in n.text.decode() and n.parent:
                    encoded = code.encode()
                    return encoded[:n.parent.start_byte].decode(errors="replace") + new_snippet + encoded[n.parent.end_byte:].decode(errors="replace")
        except Exception:
            # Fallback: reemplazo por texto si tree-sitter no soporta la query
            pass
        return code + "\n" + new_snippet
