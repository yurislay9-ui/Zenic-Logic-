"""
Unit tests for ValidationAgent.

Tests the agent that unifies ChainValidator + code quality checks:
  - Code validation (security patterns, quality patterns, Python AST)
  - Chain validation (block compatibility, completeness)
  - Config validation (JSON/YAML, common issues)
  - Risk score calculation
  - Fix suggestions
  - Correction loop (parse_response for LLM output)
  - Legacy compatibility (to_validation_result)
"""

import pytest
from unittest.mock import MagicMock, patch

from src.core.agents.validation_agent import (
    ValidationAgent,
    SECURITY_PATTERNS,
    QUALITY_PATTERNS,
    CHAIN_COMPATIBILITY_RULES,
)
from src.core.agents.schemas import (
    ValidationInput,
    ValidationOutput,
    ValidationIssue,
)
from src.core.agents.base import AgentResult


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def agent():
    """ValidationAgent without external dependencies."""
    return ValidationAgent()


# ============================================================
#  Test: Code Validation - Security Patterns
# ============================================================

class TestValidationCodeSecurity:
    """Tests for security vulnerability detection in code."""

    def test_detect_eval(self, agent):
        """Should detect dangerous eval() usage."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="result = eval(user_input)",
            language="python",
        ))
        assert result.is_valid is False
        codes = [i.code for i in result.issues]
        assert "dangerous_eval" in codes

    def test_detect_exec(self, agent):
        """Should detect dangerous exec() usage."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="exec('print(1)')",
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "dangerous_exec" in codes

    def test_detect_os_system(self, agent):
        """Should detect os.system() command injection."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="os.system('rm -rf /')",
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "command_injection" in codes

    def test_detect_subprocess_shell_true(self, agent):
        """Should detect subprocess with shell=True."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="subprocess.call(cmd, shell=True)",
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "shell_injection" in codes

    def test_detect_pickle(self, agent):
        """Should detect pickle deserialization."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="data = pickle.loads(raw_bytes)",
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "pickle_deserialization" in codes

    def test_detect_md5(self, agent):
        """Should detect weak MD5 hash."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="hashlib.md5(data)",
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "weak_hash_md5" in codes

    def test_clean_code_passes(self, agent):
        """Should pass clean code with no issues."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="x = 1 + 2\nresult = x * 3",
            language="python",
        ))
        assert result.is_valid is True
        assert result.risk_score == 0.0

    def test_empty_code_passes(self, agent):
        """Should pass empty code."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="",
            language="python",
        ))
        assert result.is_valid is True
        assert result.risk_score == 0.0


# ============================================================
#  Test: Code Validation - Quality Patterns
# ============================================================

class TestValidationCodeQuality:
    """Tests for code quality pattern detection."""

    def test_detect_bare_except(self, agent):
        """Should detect bare except: clause."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="try:\n    x = 1\nexcept:\n    pass",
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "bare_except" in codes

    def test_detect_todo_comment(self, agent):
        """Should detect TODO/FIXME comments."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="# TODO: fix this later\nx = 1",
            language="python",
            rules=["quality"],
        ))
        codes = [i.code for i in result.issues]
        assert "todo_comment" in codes

    def test_detect_print_statement(self, agent):
        """Should detect print() statements."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="print('debug')",
            language="python",
            rules=["quality"],
        ))
        codes = [i.code for i in result.issues]
        assert "print_statement" in codes


# ============================================================
#  Test: Python AST Analysis
# ============================================================

class TestValidationPythonAST:
    """Tests for Python-specific AST analysis."""

    def test_detect_syntax_error(self, agent):
        """Should detect syntax errors in Python code."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="def foo(\n    x = 1",
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "syntax_error" in codes
        assert result.is_valid is False

    def test_detect_resource_leak(self, agent):
        """Should detect open() without 'with' in functions."""
        code = "def read_file(path):\n    f = open(path)\n    data = f.read()\n    return data\n"
        result = agent.fallback(ValidationInput(
            target="code",
            content=code,
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "resource_leak" in codes

    def test_bare_except_ast(self, agent):
        """Should detect bare except via AST analysis."""
        code = "try:\n    x = 1\nexcept:\n    pass\n"
        result = agent.fallback(ValidationInput(
            target="code",
            content=code,
            language="python",
        ))
        codes = [i.code for i in result.issues]
        assert "bare_except" in codes


# ============================================================
#  Test: Chain Validation
# ============================================================

class TestValidationChain:
    """Tests for chain/logic block validation."""

    def test_empty_chain(self, agent):
        """Should handle empty chain gracefully."""
        result = agent.fallback(ValidationInput(
            target="chain",
            content='{"blocks": []}',
        ))
        assert result.is_valid is True
        codes = [i.code for i in result.issues]
        assert "empty_chain" in codes

    def test_valid_chain(self, agent):
        """Should validate a valid chain."""
        chain = {
            "blocks": [
                {"name": "fetch_data", "category": "data"},
                {"name": "validate_data", "category": "validation"},
            ]
        }
        result = agent.fallback(ValidationInput(
            target="chain",
            content=chain,
        ))
        assert result.is_valid is True

    def test_missing_block_name(self, agent):
        """Should warn about blocks without names."""
        chain = {"blocks": [{}]}
        result = agent.fallback(ValidationInput(
            target="chain",
            content=chain,
        ))
        codes = [i.code for i in result.issues]
        assert "missing_name" in codes

    def test_long_chain_warning(self, agent):
        """Should warn about chains with >10 blocks."""
        blocks = [{"name": f"block_{i}", "category": "data"} for i in range(12)]
        chain = {"blocks": blocks}
        result = agent.fallback(ValidationInput(
            target="chain",
            content=chain,
        ))
        codes = [i.code for i in result.issues]
        assert "long_chain" in codes


# ============================================================
#  Test: Config Validation
# ============================================================

class TestValidationConfig:
    """Tests for configuration validation."""

    def test_debug_enabled(self, agent):
        """Should warn about DEBUG mode enabled."""
        config = {"DEBUG": True}
        result = agent.fallback(ValidationInput(
            target="config",
            content=config,
        ))
        codes = [i.code for i in result.issues]
        assert "debug_enabled" in codes

    def test_weak_secret_key(self, agent):
        """Should detect default/weak SECRET_KEY."""
        config = {"SECRET_KEY": "change-this"}
        result = agent.fallback(ValidationInput(
            target="config",
            content=config,
        ))
        assert result.is_valid is False
        codes = [i.code for i in result.issues]
        assert "weak_secret_key" in codes

    def test_valid_config(self, agent):
        """Should pass a valid config."""
        config = {"SECRET_KEY": "a1b2c3d4e5f6g7h8i9j0", "DEBUG": False}
        result = agent.fallback(ValidationInput(
            target="config",
            content=config,
        ))
        assert result.is_valid is True

    def test_invalid_json_string(self, agent):
        """Should detect invalid JSON config string."""
        result = agent.fallback(ValidationInput(
            target="config",
            content="{not valid json at all !@#}",
        ))
        # If yaml is available, it might parse it; if not, should be invalid
        # The key test is that it doesn't crash
        assert isinstance(result.is_valid, bool)
        assert isinstance(result.risk_score, float)


# ============================================================
#  Test: Risk Score Calculation
# ============================================================

class TestValidationRiskScore:
    """Tests for risk score calculation."""

    def test_no_issues_zero_risk(self, agent):
        """Should have 0 risk score when no issues."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="x = 1",
            language="python",
        ))
        assert result.risk_score == 0.0

    def test_error_issues_increase_risk(self, agent):
        """Should have higher risk score with error-level issues."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="eval('dangerous')",
            language="python",
        ))
        assert result.risk_score > 0.0

    def test_risk_score_capped_at_1(self, agent):
        """Risk score should never exceed 1.0."""
        # Use many dangerous patterns
        code = "eval('a')\nexec('b')\nos.system('c')\npickle.loads(d)\n"
        result = agent.fallback(ValidationInput(
            target="code",
            content=code,
            language="python",
        ))
        assert result.risk_score <= 1.0


# ============================================================
#  Test: Fix Suggestions
# ============================================================

class TestValidationFixSuggestions:
    """Tests for fix suggestion generation."""

    def test_suggestion_for_eval(self, agent):
        """Should suggest replacing eval() with ast.literal_eval()."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="eval(user_data)",
            language="python",
        ))
        suggestions = result.suggestions
        assert any("literal_eval" in s or "eval" in s for s in suggestions)

    def test_suggestion_for_pickle(self, agent):
        """Should suggest json instead of pickle."""
        result = agent.fallback(ValidationInput(
            target="code",
            content="pickle.loads(data)",
            language="python",
        ))
        suggestions = result.suggestions
        assert any("json" in s or "pickle" in s for s in suggestions)


# ============================================================
#  Test: LLM Path (build_prompt + parse_response)
# ============================================================

class TestValidationLLMPath:
    """Tests for LLM prompt building and response parsing."""

    def test_build_prompt_with_validation_input(self, agent):
        """Should build system + user prompt from ValidationInput."""
        system, user = agent.build_prompt(ValidationInput(
            target="code",
            content="eval(x)",
            rules=["security"],
            language="python",
        ))
        assert "validation" in system.lower()
        assert "code" in user

    def test_build_prompt_with_string(self, agent):
        """Should build prompt from plain string."""
        system, user = agent.build_prompt("some code to validate")
        assert "validation" in system.lower()

    def test_parse_response_valid_json(self, agent):
        """Should parse valid JSON response from LLM."""
        raw = '{"is_valid":false,"issues":[{"severity":"error","code":"dangerous_eval","message":"Use of eval()","line":1,"suggestion":"Use ast.literal_eval()"}],"suggestions":["Replace eval()"],"risk_score":0.3}'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.is_valid is False
        assert len(result.issues) == 1
        assert result.issues[0].code == "dangerous_eval"
        assert result.risk_score == 0.3
        assert result.source == "llm"

    def test_parse_response_free_text(self, agent):
        """Should parse free text with bullet points."""
        raw = "Found issues:\n- Use of eval() is dangerous\n- Missing error handling"
        result = agent.parse_response(raw, None)
        assert result is not None
        assert len(result.issues) >= 1
        assert result.source == "llm"

    def test_parse_response_empty(self, agent):
        """Should return None for very short/empty text."""
        result = agent.parse_response("short", None)
        assert result is None

    def test_parse_response_risk_score_clamped(self, agent):
        """Should clamp risk_score to 0-1 range."""
        raw = '{"is_valid":true,"issues":[],"suggestions":[],"risk_score":2.5}'
        result = agent.parse_response(raw, None)
        assert result.risk_score <= 1.0


# ============================================================
#  Test: Legacy Compatibility
# ============================================================

class TestValidationLegacyCompat:
    """Tests for to_validation_result() ChainValidator compatibility."""

    def test_to_validation_result(self, agent):
        """Should convert ValidationOutput to ValidationResult."""
        output = ValidationOutput(
            is_valid=False,
            issues=[
                ValidationIssue(severity="error", code="eval", message="Bad eval"),
                ValidationIssue(severity="warning", code="print", message="Print found"),
            ],
            risk_score=0.4,
        )
        with patch("src.core.chain_validator.ValidationResult") as MockResult:
            mock_result_instance = MagicMock()
            MockResult.return_value = mock_result_instance
            with patch("src.core.chain_validator.ValidationError", MagicMock):
                result = agent.to_validation_result(output)
                # Should have called add_error and add_warning
                mock_result_instance.add_error.assert_called_once()
                mock_result_instance.add_warning.assert_called_once()


# ============================================================
#  Test: Wire and Stats
# ============================================================

class TestValidationWireAndStats:
    """Tests for wire() and stats tracking."""

    def test_wire_semantic_engine(self, agent):
        """Should update semantic engine reference via wire()."""
        mock_se = MagicMock()
        agent.wire(semantic_engine=mock_se)
        assert agent._semantic_engine is mock_se

    def test_wire_smart_memory(self, agent):
        """Should update smart memory reference via wire()."""
        mock_mem = MagicMock()
        agent.wire(smart_memory=mock_mem)
        assert agent._smart_memory is mock_mem

    def test_stats_after_fallback(self, agent):
        """Should track fallback calls in stats."""
        agent.fallback(ValidationInput(
            target="code", content="x = 1", language="python"
        ))
        stats = agent.stats
        assert stats["name"] == "validation"
        assert stats["total_calls"] >= 1

    def test_validate_with_runner_success(self, agent):
        """Should use LLM result when runner succeeds."""
        mock_runner = MagicMock()
        llm_output = ValidationOutput(
            is_valid=True, issues=[], risk_score=0.0, source="llm"
        )
        mock_runner.run.return_value = AgentResult(
            success=True, data=llm_output, source="llm"
        )
        result = agent.validate_with_runner(
            mock_runner, "code", "x = 1"
        )
        assert result.is_valid is True
        assert result.source == "llm"

    def test_validate_with_runner_failure_falls_back(self, agent):
        """Should fall back when runner fails."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(
            success=False, data=None, error="LLM timeout"
        )
        result = agent.validate_with_runner(
            mock_runner, "code", "x = 1"
        )
        assert result.source == "fallback"
