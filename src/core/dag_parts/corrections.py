"""
F5 Correction Logic + Fractal App Generation as a mixin.

Contains: _apply_f5_corrections and generate_fractal_app methods.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class CorrectionsMixin:
    """Mixin providing F5 correction logic and fractal app generation."""

    # ============================================================
    #  F5 CORRECTION LOGIC
    # ============================================================

    def _apply_f5_corrections(self, code: str, issues: list, lang: str) -> str:
        """
        F5: Aplica correcciones automáticas basadas en los issues detectados
        por ValidationAgent.
        """
        import re as _re
        corrected = code

        for issue in issues:
            issue_code = getattr(issue, 'code', '')
            severity = getattr(issue, 'severity', 'warning')

            if severity != 'error':
                continue

            if issue_code == 'dangerous_eval':
                corrected = _re.sub(
                    r'\beval\s*\(', 'ast.literal_eval(', corrected
                )
                if 'ast.literal_eval' in corrected and 'import ast' not in corrected:
                    corrected = 'import ast\n' + corrected

            elif issue_code == 'command_injection':
                # Replace os.system(CMD) with subprocess.run(shlex.split(CMD), ...)
                # os.system takes a single string; subprocess.run with shell=False
                # requires a list. Using shlex.split() to parse the command string
                # into a proper argument list.
                corrected = _re.sub(
                    r'os\.system\s*\(\s*([^)]+)\s*\)',
                    r'subprocess.run(shlex.split(\1), shell=False, capture_output=True)',
                    corrected
                )
                if 'subprocess.run' in corrected and 'import subprocess' not in corrected:
                    corrected = 'import subprocess\nimport shlex\n' + corrected
                elif 'shlex.split' in corrected and 'import shlex' not in corrected:
                    corrected = 'import shlex\n' + corrected

            elif issue_code == 'shell_injection':
                corrected = _re.sub(
                    r'subprocess\.\w+\s*\(([^)]*?)shell\s*=\s*True',
                    r'subprocess.run(\1shell=False',
                    corrected
                )

            elif issue_code == 'pickle_deserialization':
                # pickle and json are NOT interchangeable — pickle handles binary
                # data, json handles text.  Instead of silently replacing (which
                # breaks at runtime), we wrap the call with a safety check that
                # logs a warning and returns None for non-JSON-safe data.
                corrected = _re.sub(
                    r'pickle\.loads?\s*\(',
                    '_safe_deserialize(',
                    corrected
                )
                if '_safe_deserialize' in corrected and 'def _safe_deserialize' not in corrected:
                    safe_func = (
                        'import json\n'
                        'def _safe_deserialize(data):\n'
                        '    """F5: Safe replacement for pickle.loads — tries JSON first."""\n'
                        '    try:\n'
                        '        if isinstance(data, bytes):\n'
                        '            data = data.decode("utf-8")\n'
                        '        return json.loads(data)\n'
                        '    except (json.JSONDecodeError, UnicodeDecodeError):\n'
                        '        import logging; logging.warning("F5: Cannot safely deserialize pickle data")\n'
                        '        return None\n'
                        '\n'
                    )
                    corrected = safe_func + corrected

            elif issue_code == 'bare_except':
                corrected = _re.sub(
                    r'except\s*:', 'except Exception:', corrected
                )

            elif issue_code in ('weak_hash_md5', 'weak_hash_sha1'):
                if 'md5' in issue_code:
                    corrected = _re.sub(
                        r'hashlib\.md5\b', 'hashlib.sha256', corrected
                    )
                elif 'sha1' in issue_code:
                    corrected = _re.sub(
                        r'hashlib\.sha1\b', 'hashlib.sha256', corrected
                    )

        return corrected

    # ============================================================
    #  DAG-SPECIFIC PUBLIC API
    # ============================================================

    async def generate_fractal_app(self, description: str,
                                    project_name: str = "generated_project",
                                    project_type: str = "",
                                    language: str = "python",
                                    output_dir: str = "") -> Dict[str, Any]:
        """Brecha C: Genera una app completa usando Generación Fractal (Top-Down)."""
        fractal_result = self._fractal_gen.generate_project(
            description=description,
            project_type=project_type,
            project_name=project_name,
            language=language,
            output_dir=output_dir,
        )

        if self._memory and fractal_result.status == "complete":
            self._memory.save_project(
                project_name=project_name,
                project_type=project_type,
                description=description,
                path=output_dir,
                status="generated_fractal",
                entities=[],
                endpoints=[],
            )
            self._memory.save_episode(
                event_type="fractal_app_generated",
                description=f"Fractal generated {project_type} app: {project_name}",
                context=description[:200],
                outcome="success",
                importance=0.9,
            )

        return {
            "status": fractal_result.status,
            "project_name": fractal_result.project_name,
            "project_type": project_type,
            "files_generated": fractal_result.files_generated,
            "total_files": fractal_result.total_files,
            "items_completed": fractal_result.items_completed,
            "items_total": fractal_result.items_total,
            "current_phase": fractal_result.current_phase,
            "error": fractal_result.error,
        }
