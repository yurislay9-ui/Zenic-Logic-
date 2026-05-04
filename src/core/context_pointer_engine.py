"""
ZENIC LOGIC - ContextPointerEngine (Vectorización de Firmas para Code Path)

Resuelve la pérdida de datos en contextos de 20K+ tokens implementando
un sistema de PUNTEROS DE CONTEXTO que reemplaza los resúmenes semánticos.

Problema:
  Cuando OpenClaw envía un payload masivo de código (>20K tokens),
  comprimirlo en un resumen semántico pierde detalles críticos.
  El modelo Qwen no puede modificar código que no ve.

Solución:
  1. Vectorización de Firmas: cada función/clase se indexa por su firma
  2. Cuando se necesita modificar código, se pasan solo las COORDENADAS
  3. El código puro se almacena en disco de forma aislada
  4. Cuando el modelo genera una modificación, el AST Surgeon opera
     directamente sobre el archivo en disco, no sobre el contexto comprimido

Flujo:
  Código grande → SignatureIndex → ContextPointer[] → Modelo Qwen
       ↓                                              ↓
  Almacenado en disco                    Modificación → AST Surgeon → Archivo en disco

Ventajas:
  - El modelo ve "coordenadas" compactas (~100 tokens vs 20K)
  - El código real nunca se pierde (está en disco)
  - El AST Surgeon opera directamente sobre archivos
  - Compatible con SemanticEngine para búsqueda semántica de funciones
"""

import os
import re
import ast
import json
import hashlib
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# === Storage Root ===
CONTEXT_STORE_ROOT = os.path.join(
    os.path.expanduser("~"), ".titan_omniscale", "context_store"
)


@dataclass
class FunctionSignature:
    """Firma vectorizada de una función/método."""
    name: str
    file_path: str
    line_start: int
    line_end: int
    params: List[str] = field(default_factory=list)
    return_type: str = ""
    docstring: str = ""
    complexity: int = 1
    calls: List[str] = field(default_factory=list)
    hash: str = ""

    def to_pointer(self) -> str:
        """Convierte la firma en un puntero compacto para el modelo."""
        params_str = ", ".join(self.params) if self.params else "()"
        ret = f" -> {self.return_type}" if self.return_type else ""
        return f"📍 {self.name}({params_str}){ret} @ L{self.line_start}-{self.line_end} [{self.file_path}]"


@dataclass
class ContextPointer:
    """
    Puntero de contexto que referencia código en disco.

    En vez de pasar el código completo al modelo, se pasa un puntero
    compacto con las coordenadas del código relevante.
    """
    signature: FunctionSignature
    relevance_score: float = 0.0
    reason: str = ""  # Why this function is relevant

    def to_model_context(self) -> str:
        """Genera la representación compacta para enviar al modelo."""
        pointer = self.signature.to_pointer()
        doc = f'  """{self.signature.docstring[:100]}"""' if self.signature.docstring else ""
        reason = f"  # Relevante: {self.reason}" if self.reason else ""
        calls = f"  # Llama a: {', '.join(self.signature.calls[:5])}" if self.signature.calls else ""
        return f"{pointer}{doc}{reason}{calls}"

    def load_code_from_disk(self) -> str:
        """Carga el código real desde el archivo en disco."""
        try:
            if os.path.isfile(self.signature.file_path):
                with open(self.signature.file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                start = max(0, self.signature.line_start - 1)
                end = min(len(lines), self.signature.line_end)
                return "".join(lines[start:end])
        except Exception as e:
            logger.error(f"ContextPointer: Error loading code from disk: {e}")
        return ""

    def apply_modification(self, new_code: str, sibling_pointers: Optional[List['ContextPointer']] = None) -> bool:
        """
        Aplica una modificación directamente al archivo en disco
        usando coordenadas del puntero.

        Args:
            new_code: The replacement code for this pointer's range.
            sibling_pointers: Other ContextPointer objects for the same file whose
                line numbers should be adjusted after this modification. If not
                provided, sibling pointers will NOT be adjusted (known limitation).
        """
        try:
            if not os.path.isfile(self.signature.file_path):
                logger.error(f"ContextPointer: File not found: {self.signature.file_path}")
                return False

            with open(self.signature.file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            start = max(0, self.signature.line_start - 1)
            end = min(len(lines), self.signature.line_end)

            old_line_count = end - start

            # Reemplazar las líneas
            new_lines = new_code.splitlines(keepends=True)
            new_line_count = len(new_lines)
            lines[start:end] = new_lines

            with open(self.signature.file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            # Calculate line delta for sibling adjustment
            line_delta = new_line_count - old_line_count

            # Save original end before updating (needed for sibling comparison)
            original_line_end = self.signature.line_end

            # Update own signature
            self.signature.line_end = self.signature.line_start + new_line_count - 1
            new_hash = hashlib.sha256(new_code.encode()).hexdigest()[:16]
            self.signature.hash = new_hash

            # Adjust sibling pointers' line numbers for the same file
            if sibling_pointers:
                self._adjust_siblings(sibling_pointers, line_delta, original_line_end)
            elif line_delta != 0:
                # TODO: Without sibling_pointers, modifications that change line counts
                # will cause other ContextPointer objects for the same file to have
                # stale line_start/line_end values. Callers should pass sibling_pointers
                # obtained from SignatureIndex._signatures[file_path] to ensure
                # all pointers remain consistent after modifications.
                logger.warning(
                    f"ContextPointer: Line delta={line_delta} but no sibling pointers "
                    f"provided. Other pointers for {self.signature.file_path} may "
                    f"have stale line numbers."
                )

            logger.info(
                f"ContextPointer: Applied modification to {self.signature.name} "
                f"@ {self.signature.file_path}:{self.signature.line_start}"
            )
            return True

        except Exception as e:
            logger.error(f"ContextPointer: Error applying modification: {e}")
            return False

    def _adjust_siblings(self, sibling_pointers: List['ContextPointer'], line_delta: int, original_line_end: int = None):
        """
        Adjust line numbers of sibling ContextPointer objects that come AFTER
        this pointer in the same file.

        When a modification changes the number of lines, all subsequent
        pointers in the same file need their line_start and line_end
        shifted by the same delta.
        """
        if line_delta == 0:
            return

        # Use original line_end for comparison to avoid skipping siblings
        # that start at the same line as our new (expanded) end
        my_end = original_line_end if original_line_end is not None else self.signature.line_end
        for sibling in sibling_pointers:
            # Skip self and pointers that start before or at our original range
            if sibling is self:
                continue
            if sibling.signature.file_path != self.signature.file_path:
                continue
            if sibling.signature.line_start <= my_end:
                continue

            # Shift this sibling's line numbers
            sibling.signature.line_start += line_delta
            sibling.signature.line_end += line_delta
            logger.debug(
                f"ContextPointer: Adjusted sibling '{sibling.signature.name}' "
                f"by delta={line_delta} -> L{sibling.signature.line_start}-{sibling.signature.line_end}"
            )


class SignatureIndex:
    """
    Índice de firmas vectorizadas para un proyecto de código.

    Escanea archivos de código, extrae firmas de funciones/clases,
    y construye un índice compacto que permite buscar y referenciar
    código sin cargarlo completo en memoria.
    """

    def __init__(self, project_root: str = ""):
        self._root = project_root
        self._signatures: Dict[str, List[FunctionSignature]] = {}  # file -> [signatures]
        self._name_index: Dict[tuple, List[FunctionSignature]] = {}  # (name, file_path) -> [signatures]
        self._store_dir = CONTEXT_STORE_ROOT

    def index_project(self, project_root: str = "") -> int:
        """
        Indexa un proyecto completo, extrayendo firmas de todos los archivos.

        Returns:
            Número de firmas indexadas
        """
        root = project_root or self._root
        if not root or not os.path.isdir(root):
            logger.warning(f"SignatureIndex: Project root not found: {root}")
            return 0

        count = 0
        code_extensions = {".py", ".js", ".ts", ".kt", ".go", ".java", ".rs"}

        for filepath in Path(root).rglob("*"):
            if filepath.suffix in code_extensions:
                try:
                    content = filepath.read_text(encoding="utf-8", errors="ignore")
                    sigs = self._extract_signatures(content, str(filepath))
                    self._signatures[str(filepath)] = sigs
                    for sig in sigs:
                        self._name_index.setdefault((sig.name, sig.file_path), []).append(sig)
                    count += len(sigs)
                except Exception as e:
                    logger.debug(f"SignatureIndex: Error indexing {filepath}: {e}")

        logger.info(f"SignatureIndex: Indexed {count} signatures from {root}")
        return count

    def index_code(self, code: str, file_path: str = "input.py") -> int:
        """
        Indexa código individual, extrayendo firmas.

        Returns:
            Número de firmas extraídas
        """
        sigs = self._extract_signatures(code, file_path)
        self._signatures[file_path] = sigs
        for sig in sigs:
            self._name_index.setdefault((sig.name, sig.file_path), []).append(sig)

        # Also store the code in the context store for disk-based operations
        self._store_code(code, file_path)

        return len(sigs)

    def _extract_signatures(self, code: str, file_path: str) -> List[FunctionSignature]:
        """Extrae firmas de funciones y clases del código."""
        signatures = []

        # Detect language
        ext = Path(file_path).suffix
        if ext == ".py":
            signatures = self._extract_python_signatures(code, file_path)
        else:
            signatures = self._extract_regex_signatures(code, file_path, ext)

        return signatures

    def _extract_python_signatures(self, code: str, file_path: str) -> List[FunctionSignature]:
        """Extrae firmas usando ast nativo de Python."""
        signatures = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Extract parameters
                    params = []
                    for arg in node.args.args:
                        param = arg.arg
                        if arg.annotation:
                            if isinstance(arg.annotation, ast.Name):
                                param += f":{arg.annotation.id}"
                            elif isinstance(arg.annotation, ast.Constant):
                                param += f":{arg.annotation.value}"
                        params.append(param)

                    # Return type
                    return_type = ""
                    if node.returns:
                        if isinstance(node.returns, ast.Name):
                            return_type = node.returns.id
                        elif isinstance(node.returns, ast.Constant):
                            return_type = str(node.returns.value)

                    # Docstring
                    docstring = ast.get_docstring(node) or ""

                    # Calls
                    calls = []
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            if isinstance(child.func, ast.Name):
                                calls.append(child.func.id)
                            elif isinstance(child.func, ast.Attribute):
                                calls.append(child.func.attr)
                    calls = list(set(calls))[:10]

                    # Complexity
                    complexity = 1
                    for child in ast.walk(node):
                        if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                            complexity += 1

                    # Content hash
                    content = ast.get_source_segment(code, node) or node.name
                    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

                    sig = FunctionSignature(
                        name=node.name,
                        file_path=file_path,
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        params=params,
                        return_type=return_type,
                        docstring=docstring[:200],
                        complexity=complexity,
                        calls=calls,
                        hash=content_hash,
                    )
                    signatures.append(sig)

                elif isinstance(node, ast.ClassDef):
                    methods = [
                        n.name for n in node.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ]
                    content_hash = hashlib.sha256(node.name.encode()).hexdigest()[:16]
                    docstring = ast.get_docstring(node) or ""

                    sig = FunctionSignature(
                        name=node.name,
                        file_path=file_path,
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        params=[f"class({', '.join(methods[:5])})"],
                        return_type="class",
                        docstring=docstring[:200],
                        complexity=len(methods),
                        calls=methods[:10],
                        hash=content_hash,
                    )
                    signatures.append(sig)

        except SyntaxError as e:
            logger.debug(f"SignatureIndex: Syntax error in {file_path}: {e}")

        return signatures

    def _extract_regex_signatures(self, code: str, file_path: str, ext: str) -> List[FunctionSignature]:
        """Extrae firmas usando regex para lenguajes sin parser nativo."""
        signatures = []
        patterns = {
            ".js": r'(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)',
            ".ts": r'(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)(?:\s*:\s*([^{]+))?',
            ".kt": r'fun\s+(\w+)\s*\(([^)]*)\)(?:\s*:\s*(\w+))?',
            ".go": r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(([^)]*)\)(?:\s*([^({]+))?',
            ".java": r'(?:public|private|protected)?\s*(?:static\s+)?(?:\w+(?:<[^>]+>)?\s+)+(\w+)\s*\(([^)]*)\)',
            ".rs": r'(?:pub\s+)?fn\s+(\w+)\s*\(([^)]*)\)(?:\s*->\s*([^{]+))?',
        }

        pattern = patterns.get(ext, r'(?:def|function|fun|func)\s+(\w+)\s*\(([^)]*)\)')
        for match in re.finditer(pattern, code):
            name = match.group(1)
            params_str = match.group(2) if match.lastindex and match.lastindex >= 2 else ""
            ret_type = match.group(3) if match.lastindex and match.lastindex >= 3 else ""

            # Count line number
            line_num = code[:match.start()].count('\n') + 1

            params = [p.strip().split(':')[0].strip() for p in params_str.split(',') if p.strip()]

            sig = FunctionSignature(
                name=name,
                file_path=file_path,
                line_start=line_num,
                line_end=line_num + 5,  # Estimate
                params=params[:8],
                return_type=ret_type.strip() if ret_type else "",
                hash=hashlib.sha256(match.group(0).encode()).hexdigest()[:16],
            )
            signatures.append(sig)

        return signatures

    def _store_code(self, code: str, file_path: str):
        """Almacena código en el context store para acceso desde disco."""
        os.makedirs(self._store_dir, exist_ok=True)
        safe_name = file_path.replace("/", "_").replace("\\", "_")
        store_path = os.path.join(self._store_dir, f"{safe_name}.stored")
        try:
            with open(store_path, "w", encoding="utf-8") as f:
                f.write(code)
        except Exception as e:
            logger.debug(f"SignatureIndex: Error storing code: {e}")

    # ================================================================
    #  QUERY
    # ================================================================

    def search(self, query: str, top_k: int = 10) -> List[ContextPointer]:
        """
        Busca firmas relevantes basado en una consulta.

        Returns:
            Lista de ContextPointer ordenados por relevancia
        """
        query_lower = query.lower()
        query_words = set(query_lower.replace("_", " ").split())
        pointers = []

        for (name, file_path), sigs in self._name_index.items():
            for sig in sigs:
                score = 0

                # Name match
                if query_lower == name.lower():
                    score += 100
                elif query_lower in name.lower():
                    score += 50
                else:
                    name_words = set(name.lower().replace("_", " ").split())
                    overlap = query_words & name_words
                    score += len(overlap) * 20

                # Docstring match
                if sig.docstring:
                    doc_words = set(sig.docstring.lower().split())
                    doc_overlap = query_words & doc_words
                    score += len(doc_overlap) * 5

                # Call match (functions that call the queried function)
                if query_lower in [c.lower() for c in sig.calls]:
                    score += 15

                if score > 0:
                    reason = ""
                    if query_lower in name.lower():
                        reason = f"Nombre coincide con '{query}'"
                    elif sig.docstring and any(w in sig.docstring.lower() for w in query_words):
                        reason = f"Docstring menciona términos relevantes"
                    elif query_lower in [c.lower() for c in sig.calls]:
                        reason = f"Llama a función relacionada"

                    pointers.append(ContextPointer(
                        signature=sig,
                        relevance_score=score,
                        reason=reason,
                    ))

        pointers.sort(key=lambda p: p.relevance_score, reverse=True)
        return pointers[:top_k]

    def get_by_name(self, name: str, file_path: Optional[str] = None) -> Optional[ContextPointer]:
        """Obtiene un puntero por nombre exacto de función.

        Args:
            name: Function/class name to look up.
            file_path: Optional file path for disambiguation. If provided,
                looks up (name, file_path) directly. If None, searches all
                entries and returns the first match (with a warning).
        """
        if file_path is not None:
            sigs = self._name_index.get((name, file_path))
            if sigs:
                return ContextPointer(signature=sigs[0], reason="Exact name and file match")
            return None
        # Fallback: search all entries with this name
        matches = []
        for (n, fp), sigs in self._name_index.items():
            if n == name:
                matches.extend(sigs)
        if matches:
            logger.warning(
                f"ContextPointerEngine: get_by_name('{name}') matched "
                f"{len(matches)} signature(s) across multiple files without "
                f"file_path disambiguation; returning first match"
            )
            return ContextPointer(signature=matches[0], reason="Exact name match (no file_path specified)")
        return None

    def build_compact_context(self, query: str, max_tokens: int = 2000) -> Tuple[str, List[ContextPointer]]:
        """
        Construye un contexto compacto de punteros para enviar al modelo.

        En vez de enviar 20K+ tokens de código, envía ~200-500 tokens
        de punteros con coordenadas. El modelo puede pedir código
        específico cuando lo necesite para modificar.

        Returns:
            (compact_context_string, list_of_pointers)
        """
        pointers = self.search(query, top_k=20)

        if not pointers:
            return "No se encontraron funciones relevantes.", []

        lines = [
            f"# Context Pointers for: {query}",
            f"# {len(pointers)} funciones indexadas, código en disco",
            f"# Para modificar: especifica nombre + nuevo código",
            "",
        ]

        total_chars = 0
        used_pointers = []

        for ptr in pointers:
            ctx_line = ptr.to_model_context()
            if total_chars + len(ctx_line) > max_tokens * 4:  # ~4 chars per token
                break
            lines.append(ctx_line)
            total_chars += len(ctx_line)
            used_pointers.append(ptr)

        lines.append("")
        lines.append(f"# Total: {len(used_pointers)} punteros | Código disponible en disco bajo demanda")

        return "\n".join(lines), used_pointers

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del índice."""
        total_funcs = sum(len(sigs) for sigs in self._signatures.values())
        total_files = len(self._signatures)
        return {
            "total_signatures": total_funcs,
            "total_files": total_files,
            "unique_names": len(self._name_index),
            "store_dir": self._store_dir,
        }
