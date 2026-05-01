"""
TITAN OMNISCALE X - AST Surgeon v13 (ast nativo + regex)

Cirujano de AST usando ast nativo para Python y regex para otros lenguajes.
Realiza mutaciones, inserciones y eliminaciones a nivel de funcion.
Sin dependencias externas. Compatible con Android.
"""

import ast
import re
import logging

logger = logging.getLogger(__name__)


class ASTSurgeon:
    """Cirujano de AST usando ast nativo para Python y regex para otros."""

    def mutate_node(self, code, target_name, new_snippet, lang="python"):
        if lang == "python":
            return self._mutate_python(code, target_name, new_snippet)
        return self._mutate_regex(code, target_name, new_snippet, lang)

    def _mutate_python(self, code, target_name, new_snippet):
        try:
            tree = ast.parse(code)
            lines = code.split('\n')
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == target_name:
                        start = node.lineno - 1
                        end = node.end_lineno
                        new_lines = new_snippet.split('\n')
                        lines[start:end] = new_lines
                        return '\n'.join(lines)
        except SyntaxError:
            pass
        return self._mutate_regex(code, target_name, new_snippet, "python")

    def _mutate_regex(self, code, target_name, new_snippet, lang):
        try:
            if lang == "python":
                pattern = rf'(def\s+{re.escape(target_name)}\s*\([^)]*\)[^:]*:.*?)(?=\ndef\s|\nclass\s|\Z)'
            elif lang == "kotlin":
                pattern = rf'(fun\s+{re.escape(target_name)}\s*\([^)]*\)[^{{]*\{{.*?\}})'
            elif lang == "go":
                pattern = rf'(func\s+(?:\([^)]+\)\s+)?{re.escape(target_name)}\s*\([^)]*\)[^{{]*\{{.*?\}})'
            else:
                pattern = rf'(function\s+{re.escape(target_name)}\s*\([^)]*\)[^{{]*\{{.*?\}})'
            match = re.search(pattern, code, re.DOTALL)
            if match:
                return code[:match.start()] + new_snippet + code[match.end():]
        except Exception as e:
            logger.debug("AST mutate fallback: %s", e)
        return code + "\n" + new_snippet

    def insert_function(self, code, new_function, lang="python"):
        if lang == "python" and code.strip():
            main_block = re.search(r'\nif\s+__name__', code)
            if main_block:
                return code[:main_block.start()] + "\n\n" + new_function + "\n" + code[main_block.start():]
        return code + "\n\n" + new_function

    def delete_function(self, code, target_name, lang="python"):
        if lang == "python":
            try:
                tree = ast.parse(code)
                lines = code.split('\n')
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if node.name == target_name:
                            start = node.lineno - 1
                            end = node.end_lineno
                            del lines[start:end]
                            return '\n'.join(lines)
            except SyntaxError:
                pass
        return self.mutate_node(code, target_name, "", lang)
