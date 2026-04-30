import asyncio
import tempfile
import os
from pathlib import Path
from src.core.shared.contracts import SandboxResult

class ReflexionSandbox:
    def __init__(self, timeout_seconds: int = 5):
        self.timeout_seconds = timeout_seconds

    async def validate_code(self, code: str, language: str, target_name: str) -> SandboxResult:
        ext_map = {"kotlin": ".kt", "python": ".py", "go": ".go", "javascript": ".js"}
        ext = ext_map.get(language, ".txt")
        
        tmp_dir = Path.home() / ".titan_omniscale" / "sandbox_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        
        tmp_file = tmp_dir / f"titan_trial_{os.getpid()}{ext}"
        
        try:
            tmp_file.write_text(code, encoding='utf-8')
            
            cmd = self._get_execution_command(str(tmp_file), language)
            if not cmd:
                return await self._fallback_ast_validation(code, language)

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
                
                if process.returncode == 0:
                    return SandboxResult(status="PASS")
                else:
                    error_msg = stderr.decode('utf-8', errors='ignore').strip()[:300]
                    return SandboxResult(status="FAIL_SYNTAX", error_message=error_msg)

            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                return SandboxResult(status="TIMEOUT", error_message="Ejecución abortada: Bucle infinito o exceso de tiempo.")

        except FileNotFoundError:
            return await self._fallback_ast_validation(code, language)
        except Exception as e:
            # We don't have FAIL_RUNTIME in SandboxResult, maybe FAIL_DEPENDENCY
            return SandboxResult(status="FAIL_DEPENDENCY", error_message=str(e))
        finally:
            if tmp_file.exists():
                tmp_file.unlink()

    def _get_execution_command(self, file_path: str, language: str) -> list[str] | None:
        if language == "python":
            # Using python instead of python3 because it's not allowed in standard tools, but since this is execution inside the sandbox, python should be fine as asked
            return ["python", "-m", "py_compile", file_path]
        elif language == "kotlin":
            if Path("/usr/bin/kotlinc").exists() or Path("/data/data/com.termux/files/usr/bin/kotlinc").exists():
                return ["kotlinc", "-nowarn", "-script", file_path]
        elif language == "go":
            if Path("/usr/bin/go").exists() or Path("/data/data/com.termux/files/usr/bin/go").exists():
                return ["go", "vet", file_path]
        elif language == "javascript":
            if Path("/usr/bin/node").exists() or Path("/data/data/com.termux/files/usr/bin/node").exists():
                return ["node", "--check", file_path]
        return None

    async def _fallback_ast_validation(self, code: str, language: str) -> SandboxResult:
        try:
            from tree_sitter_languages import get_parser
            parser = get_parser(language)
            tree = parser.parse(code.encode())
            if tree.root_node.has_error:
                err = self._find_error_node(tree.root_node)
                line = err.start_point[0] if err else 0
                return SandboxResult(status="FAIL_SYNTAX", error_message=f"AST Syntax Error en línea {line}.", error_node=str(line))
            return SandboxResult(status="PASS")
        except Exception as e:
            return SandboxResult(status="FAIL_DEPENDENCY", error_message=str(e))

    def _find_error_node(self, node):
        if node.type == "ERROR": return node
        for child in node.children:
            err = self._find_error_node(child)
            if err: return err
        return None
