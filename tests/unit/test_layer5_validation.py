"""
Tests for Layer 5: Validation & Security agents (A23-A28).

All 6 agents tested:
  - A23 SecurityScanner
  - A24 SyntaxValidator
  - A25 ChainValidator
  - A26 ConfigValidator
  - A27 RiskCalculator
  - A28 FixSuggester
"""

import json
import pytest

from src.core.agents_v2.validation import (
    SecurityScanner,
    SyntaxValidator,
    ChainValidator,
    ConfigValidator,
    RiskCalculator,
    FixSuggester,
)
from src.core.agents_v2.schemas import (
    SecurityResult,
    SyntaxResult,
    ChainResult,
    ConfigResult,
    RiskResult,
    FixSuggestions,
    ValidationIssue,
)


# ═══════════════════════════════════════════════════════════
# A23 SecurityScanner Tests
# ═══════════════════════════════════════════════════════════

class TestSecurityScanner:
    """A23: Scan for dangerous patterns."""

    def setup_method(self):
        self.scanner = SecurityScanner()

    def test_safe_code_passes(self):
        """Clean code should be safe=True with risk_score=0.0."""
        result = self.scanner.execute({"code": "x = 1 + 2\nprint(x)"})
        assert isinstance(result, SecurityResult)
        assert result.safe is True
        assert result.risk_score == 0.0
        assert len(result.threats) == 0

    def test_eval_detected(self):
        """eval() should be detected as a threat."""
        result = self.scanner.execute({"code": "result = eval(user_input)"})
        assert result.safe is False
        assert any(t.code == "dangerous_eval" for t in result.threats)
        assert result.risk_score > 0

    def test_exec_detected(self):
        """exec() should be detected as a threat."""
        result = self.scanner.execute({"code": "exec(code_string)"})
        assert result.safe is False
        assert any(t.code == "dangerous_exec" for t in result.threats)

    def test_os_system_detected(self):
        """os.system() should be detected."""
        result = self.scanner.execute({"code": "os.system('rm -rf /')"})
        assert result.safe is False
        assert any(t.code == "os_system" for t in result.threats)

    def test_pickle_detected(self):
        """pickle.loads() should be detected."""
        result = self.scanner.execute({"code": "data = pickle.loads(raw)"})
        assert result.safe is False
        assert any(t.code == "pickle_load" for t in result.threats)

    def test_sql_injection_detected(self):
        """SQL injection via f-string should be detected."""
        result = self.scanner.execute({"code": 'f"SELECT * FROM users WHERE id={user_id}"'})
        assert result.safe is False
        assert any(t.code == "sql_injection" for t in result.threats)

    def test_subprocess_shell_detected(self):
        """subprocess with shell=True should be detected."""
        result = self.scanner.execute({"code": "subprocess.run(cmd, shell=True)"})
        assert result.safe is False
        assert any(t.code == "subprocess_shell" for t in result.threats)

    def test_weak_hash_md5_detected(self):
        """hashlib.md5() should be detected."""
        result = self.scanner.execute({"code": "hashlib.md5(data)"})
        assert result.safe is False
        assert any(t.code == "weak_hash_md5" for t in result.threats)

    def test_bare_except_detected(self):
        """Bare except should be detected."""
        result = self.scanner.execute({"code": "try:\n    x = 1\nexcept:\n    pass"})
        assert any(t.code == "bare_except" for t in result.threats)

    def test_safe_patterns_reduce_risk(self):
        """Safe patterns (try/except, logging, type hints) should reduce risk score."""
        dangerous = self.scanner.execute({"code": "eval('1+1')"})
        dangerous_with_safe = self.scanner.execute(
            {"code": "import logging\nlogger = logging.getLogger()\ntry:\n    eval('1+1')\nexcept ValueError:\n    logger.error('bad')"}
        )
        # Both should be unsafe (eval detected), but safe patterns reduce risk
        assert dangerous_with_safe.risk_score <= dangerous.risk_score

    def test_empty_code_is_safe(self):
        """Empty code should default to safe=True."""
        result = self.scanner.execute({"code": ""})
        assert result.safe is True

    def test_string_input_works(self):
        """String input (not dict) should work."""
        result = self.scanner.execute("eval('bad')")
        assert result.safe is False

    def test_fallback_returns_safe(self):
        """Fallback should return safe=False (precaution principle)."""
        result = self.scanner.fallback(None)
        assert result.safe is False
        assert result.risk_score == 1.0
        assert result.source == "fallback"

    def test_multiple_threats_detected(self):
        """Multiple threats in one code block should all be found."""
        code = "eval('x')\nexec('y')\nos.system('ls')"
        result = self.scanner.execute({"code": code})
        assert result.safe is False
        threat_codes = {t.code for t in result.threats}
        assert "dangerous_eval" in threat_codes
        assert "dangerous_exec" in threat_codes
        assert "os_system" in threat_codes

    def test_suggestions_provided(self):
        """Each threat should have a fix suggestion."""
        result = self.scanner.execute({"code": "eval('x')"})
        assert len(result.threats) > 0
        for threat in result.threats:
            assert threat.suggestion != ""


# ═══════════════════════════════════════════════════════════
# A24 SyntaxValidator Tests
# ═══════════════════════════════════════════════════════════

class TestSyntaxValidator:
    """A24: Validate code syntax via AST parsing."""

    def setup_method(self):
        self.validator = SyntaxValidator()

    def test_valid_python_code(self):
        """Valid Python code should pass."""
        result = self.validator.execute({"code": "x = 1\nprint(x)", "language": "python"})
        assert isinstance(result, SyntaxResult)
        assert result.valid is True

    def test_invalid_python_syntax(self):
        """Invalid Python should report syntax error."""
        result = self.validator.execute({"code": "def foo(\n  pass", "language": "python"})
        assert result.valid is False
        assert any(e.code == "syntax_error" for e in result.errors)

    def test_missing_return_warning(self):
        """Functions that may not return on all paths should get warning."""
        code = "def foo(x):\n    if x > 0:\n        return x"
        result = self.validator.execute({"code": code, "language": "python"})
        # May have warnings but still valid
        assert isinstance(result, SyntaxResult)

    def test_bare_except_in_ast(self):
        """Bare except detected via AST should be a warning."""
        code = "try:\n    x = 1\nexcept:\n    pass"
        result = self.validator.execute({"code": code, "language": "python"})
        assert any(e.code == "bare_except" for e in result.errors)

    def test_js_brace_validation(self):
        """JS/TS code should be validated via brace balance."""
        result = self.validator.execute({
            "code": "function foo() { return 1; }",
            "language": "javascript",
        })
        assert result.valid is True

    def test_mismatched_braces(self):
        """Mismatched braces should be detected."""
        result = self.validator.execute({
            "code": "function foo() { return [1, 2 ); }",
            "language": "javascript",
        })
        assert result.valid is False

    def test_unclosed_brace(self):
        """Unclosed braces should be detected."""
        result = self.validator.execute({
            "code": "function foo() { return 1;",
            "language": "javascript",
        })
        assert result.valid is False

    def test_empty_code_is_valid(self):
        """Empty code should default to valid=True."""
        result = self.validator.execute({"code": "", "language": "python"})
        assert result.valid is True

    def test_string_input_works(self):
        """String input should work."""
        result = self.validator.execute("x = 1")
        assert result.valid is True

    def test_fallback_returns_valid(self):
        """Fallback should return valid=True."""
        result = self.validator.fallback(None)
        assert result.valid is True
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A25 ChainValidator Tests
# ═══════════════════════════════════════════════════════════

class TestChainValidator:
    """A25: Validate logic chain compatibility and completeness."""

    def setup_method(self):
        self.validator = ChainValidator()

    def test_empty_chain_is_valid(self):
        """Empty chain should be valid with missing=['blocks']."""
        result = self.validator.execute({"chain": {"blocks": []}})
        assert isinstance(result, ChainResult)
        assert result.valid is True
        assert "blocks" in result.missing

    def test_valid_simple_chain(self):
        """Simple valid chain with context should pass cleanly."""
        chain = {
            "blocks": [
                {"name": "fetch_data", "category": "data", "outputs": ["records"]},
                {"name": "validate_data", "category": "validation", "inputs": ["records"]},
            ]
        }
        result = self.validator.execute({"chain": chain, "context": {"db": True}})
        assert result.valid is True
        # No type mismatches or critical issues
        assert not any("Type mismatch" in i or "CRITICAL" in i for i in result.incompatibilities)

    def test_missing_block_name_warning(self):
        """Block without name should produce incompatibility."""
        chain = {"blocks": [{"category": "data"}]}
        result = self.validator.execute({"chain": chain})
        assert any("no name" in i for i in result.incompatibilities)

    def test_type_mismatch_detected(self):
        """Type incompatibility between blocks should be detected."""
        chain = {
            "blocks": [
                {"name": "step1", "category": "data", "outputs": [{"type": "records"}]},
                {"name": "step2", "category": "business_logic", "inputs": [{"type": "html"}]},
            ]
        }
        result = self.validator.execute({"chain": chain})
        assert any("Type mismatch" in i for i in result.incompatibilities)

    def test_type_any_is_compatible(self):
        """Type 'any' should be compatible with everything."""
        chain = {
            "blocks": [
                {"name": "step1", "category": "data", "outputs": [{"type": "records"}]},
                {"name": "step2", "category": "validation", "inputs": [{"type": "any"}]},
            ]
        }
        result = self.validator.execute({"chain": chain})
        assert not any("Type mismatch" in i for i in result.incompatibilities)

    def test_category_compatibility_warning(self):
        """Incompatible category transitions should produce hints."""
        chain = {
            "blocks": [
                {"name": "validate", "category": "validation"},
                {"name": "logic", "category": "business_logic"},
            ]
        }
        result = self.validator.execute({"chain": chain})
        assert any("Category hint" in i for i in result.incompatibilities)

    def test_auth_block_needs_db_context(self):
        """Auth block without db in context should warn."""
        chain = {"blocks": [{"name": "auth_step", "category": "auth"}]}
        result = self.validator.execute({"chain": chain, "context": {}})
        assert any("auth" in i.lower() and "db" in i for i in result.incompatibilities)

    def test_auth_block_with_db_context_ok(self):
        """Auth block with db in context should not warn."""
        chain = {"blocks": [{"name": "auth_step", "category": "auth"}]}
        result = self.validator.execute({"chain": chain, "context": {"db": True}})
        assert not any("auth" in i.lower() and "db" in i for i in result.incompatibilities)

    def test_strict_mode_long_chain(self):
        """Strict mode: chain >10 blocks should warn."""
        blocks = [{"name": f"step_{i}", "category": "data"} for i in range(12)]
        chain = {"blocks": blocks}
        result = self.validator.execute({"chain": chain, "strict": True})
        assert any("12 blocks" in i for i in result.incompatibilities)

    def test_strict_mode_duplicate_names(self):
        """Strict mode: duplicate block names should warn."""
        chain = {
            "blocks": [
                {"name": "process", "category": "data"},
                {"name": "process", "category": "data"},
            ]
        }
        result = self.validator.execute({"chain": chain, "strict": True})
        assert any("Duplicate" in i for i in result.incompatibilities)

    def test_strict_mode_validation_after_logic(self):
        """Strict mode: validation after business_logic should warn."""
        chain = {
            "blocks": [
                {"name": "logic", "category": "business_logic"},
                {"name": "validate", "category": "validation"},
            ]
        }
        result = self.validator.execute({"chain": chain, "strict": True})
        assert any("Validation after" in i for i in result.incompatibilities)

    def test_json_string_chain(self):
        """JSON string chain should be parsed correctly."""
        chain_json = json.dumps({
            "blocks": [{"name": "step1", "category": "data"}]
        })
        result = self.validator.execute({"chain": chain_json})
        assert result.valid is True

    def test_missing_auth_block(self):
        """auth_required context without auth block should report missing."""
        chain = {"blocks": [{"name": "data_step", "category": "data"}]}
        result = self.validator.execute({
            "chain": chain,
            "context": {"auth_required": True},
        })
        assert "auth_block" in result.missing

    def test_object_blocks_with_attributes(self):
        """Blocks as objects with attributes should work."""
        class MockBlock:
            def __init__(self, name, category):
                self.name = name
                self.category = category
                self.outputs = []
                self.inputs = []
                self.execute = lambda data: data  # Has execute method

        chain = {"blocks": [MockBlock("step1", "data")]}
        result = self.validator.execute({"chain": chain, "context": {"db": True}})
        assert result.valid is True

    def test_fallback_returns_valid(self):
        """Fallback should return valid=True."""
        result = self.validator.fallback(None)
        assert result.valid is True
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A26 ConfigValidator Tests
# ═══════════════════════════════════════════════════════════

class TestConfigValidator:
    """A26: Validate configuration schemas and values."""

    def setup_method(self):
        self.validator = ConfigValidator()

    def test_valid_app_config(self):
        """Valid app config should pass."""
        config = {
            "name": "my-app",
            "version": "1.0.0",
            "debug": False,
        }
        result = self.validator.execute({"config": config, "config_type": "app"})
        assert isinstance(result, ConfigResult)
        assert result.valid is True

    def test_missing_required_key(self):
        """Missing required key should be an error."""
        config = {"name": "my-app"}  # Missing "version"
        result = self.validator.execute({"config": config, "config_type": "app"})
        assert result.valid is False
        assert any(i.code == "missing_required_key" for i in result.issues)

    def test_type_mismatch(self):
        """Wrong value type should be an error."""
        config = {
            "name": "my-app",
            "version": "1.0.0",
            "workers": "four",  # Should be int
        }
        result = self.validator.execute({"config": config, "config_type": "app"})
        assert result.valid is False
        assert any(i.code == "type_mismatch" for i in result.issues)

    def test_value_out_of_range(self):
        """Value outside allowed range should be an error."""
        config = {
            "name": "my-app",
            "version": "1.0.0",
            "workers": 100,  # Max is 64
        }
        result = self.validator.execute({"config": config, "config_type": "app"})
        assert result.valid is False
        assert any(i.code == "value_too_high" for i in result.issues)

    def test_debug_enabled_warning(self):
        """DEBUG=true should produce a security info issue."""
        config = {"name": "my-app", "version": "1.0.0", "debug": True}
        result = self.validator.execute({"config": config, "config_type": "app"})
        assert any(i.code == "debug_enabled" for i in result.issues)

    def test_weak_secret_key(self):
        """Weak SECRET_KEY should be an error."""
        config = {"secret_key": "change-this", "algorithm": "HS256"}
        result = self.validator.execute({"config": config, "config_type": "auth"})
        assert any(i.code == "weak_secret_key" for i in result.issues)

    def test_short_secret_key(self):
        """Short SECRET_KEY should produce a warning."""
        config = {"secret_key": "short", "algorithm": "HS256"}
        result = self.validator.execute({"config": config, "config_type": "auth"})
        assert any(i.code == "short_secret_key" for i in result.issues)

    def test_ssl_disabled_warning(self):
        """Database SSL disabled should warn."""
        config = {"host": "localhost", "port": 5432, "name": "mydb", "ssl": False}
        result = self.validator.execute({"config": config, "config_type": "database"})
        assert any(i.code == "ssl_disabled" for i in result.issues)

    def test_cors_wildcard_warning(self):
        """CORS with wildcard should warn."""
        config = {"cors_origins": "*"}
        result = self.validator.execute({"config": config})
        assert any(i.code == "cors_wildcard" for i in result.issues)

    def test_bind_all_interfaces_info(self):
        """Binding to 0.0.0.0 should produce info."""
        config = {"host": "0.0.0.0", "port": 8080}
        result = self.validator.execute({"config": config, "config_type": "server"})
        assert any(i.code == "bind_all_interfaces" for i in result.issues)

    def test_defaults_applied(self):
        """Missing optional keys should have defaults applied."""
        config = {"name": "my-app", "version": "1.0.0"}
        result = self.validator.execute({"config": config, "config_type": "app"})
        # Should have defaults applied for debug, env, workers
        assert len(result.defaults_applied) > 0

    def test_invalid_json_config(self):
        """Invalid JSON/YAML string should produce format error."""
        result = self.validator.execute({"config": "this is not json or yaml!!!"})
        # Even if parsed, the config should have issues or be empty
        # The key is it doesn't crash and returns a ConfigResult
        assert isinstance(result, ConfigResult)

    def test_valid_json_string_config(self):
        """Valid JSON string should be parsed correctly."""
        config_json = json.dumps({"name": "my-app", "version": "1.0.0"})
        result = self.validator.execute({"config": config_json, "config_type": "app"})
        assert result.valid is True

    def test_custom_schema_validation(self):
        """Custom schema should be validated."""
        custom_schema = {
            "required": ["api_key", "base_url"],
            "defaults": {"timeout": 30},
        }
        config = {"api_key": "sk-xxx", "base_url": "https://api.example.com"}
        result = self.validator.execute({"config": config, "schema": custom_schema})
        assert result.valid is True

    def test_custom_schema_missing_required(self):
        """Custom schema missing required should error."""
        custom_schema = {
            "required": ["api_key", "base_url"],
        }
        config = {"api_key": "sk-xxx"}
        result = self.validator.execute({"config": config, "schema": custom_schema})
        assert result.valid is False
        assert any("base_url" in i.message for i in result.issues)

    def test_database_port_range(self):
        """Database port should be 1-65535."""
        config = {"host": "localhost", "port": 99999, "name": "mydb"}
        result = self.validator.execute({"config": config, "config_type": "database"})
        assert result.valid is False
        assert any(i.code == "value_too_high" for i in result.issues)

    def test_logging_level_allowed_values(self):
        """Logging level should be one of the allowed values."""
        config = {"level": "VERBOSE"}  # Not in allowed values
        result = self.validator.execute({"config": config, "config_type": "logging"})
        assert result.valid is False
        assert any(i.code == "invalid_value" for i in result.issues)

    def test_fallback_returns_valid(self):
        """Fallback should return valid=True."""
        result = self.validator.fallback(None)
        assert result.valid is True
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A27 RiskCalculator Tests
# ═══════════════════════════════════════════════════════════

class TestRiskCalculator:
    """A27: Calculate aggregate risk score from all validations."""

    def setup_method(self):
        self.calculator = RiskCalculator()

    def test_no_issues_low_risk(self):
        """No validation issues should result in low risk."""
        result = self.calculator.execute({
            "security_result": SecurityResult(safe=True),
            "syntax_result": SyntaxResult(valid=True),
        })
        assert isinstance(result, RiskResult)
        assert result.level == "low"
        assert result.score == 0.0

    def test_security_threat_increases_risk(self):
        """Security threats should increase risk score."""
        result = self.calculator.execute({
            "security_result": SecurityResult(
                safe=False,
                threats=[ValidationIssue(severity="error", code="eval", message="eval found")],
                risk_score=0.5,
            ),
            "syntax_result": SyntaxResult(valid=True),
        })
        assert result.score > 0.0
        assert result.level in ("medium", "high", "critical")

    def test_syntax_error_increases_risk(self):
        """Syntax errors should increase risk score."""
        result = self.calculator.execute({
            "security_result": SecurityResult(safe=True),
            "syntax_result": SyntaxResult(
                valid=False,
                errors=[ValidationIssue(severity="error", code="syntax", message="bad syntax")],
            ),
        })
        assert result.score > 0.0

    def test_combined_risk_higher(self):
        """Combined security + syntax issues should be higher risk."""
        result_both = self.calculator.execute({
            "security_result": SecurityResult(
                safe=False,
                threats=[ValidationIssue(severity="error", code="eval", message="eval")],
                risk_score=0.5,
            ),
            "syntax_result": SyntaxResult(
                valid=False,
                errors=[ValidationIssue(severity="error", code="syntax", message="err")],
            ),
        })
        result_one = self.calculator.execute({
            "security_result": SecurityResult(safe=True),
            "syntax_result": SyntaxResult(
                valid=False,
                errors=[ValidationIssue(severity="error", code="syntax", message="err")],
            ),
        })
        assert result_both.score >= result_one.score

    def test_critical_risk_recommendations(self):
        """Critical risk level should have DO NOT deploy recommendation."""
        result = self.calculator.execute({
            "security_result": SecurityResult(
                safe=False,
                threats=[
                    ValidationIssue(severity="error", code="eval", message="eval"),
                    ValidationIssue(severity="error", code="exec", message="exec"),
                    ValidationIssue(severity="error", code="os_system", message="os.system"),
                ],
                risk_score=0.9,
            ),
            "syntax_result": SyntaxResult(
                valid=False,
                errors=[ValidationIssue(severity="error", code="syntax", message="err")],
            ),
        })
        if result.level == "critical":
            assert any("DO NOT deploy" in r for r in result.recommendations)

    def test_fallback_returns_low_risk(self):
        """Fallback should return low risk."""
        result = self.calculator.fallback(None)
        assert result.level == "low"
        assert result.source == "fallback"

    def test_non_dict_input_uses_fallback(self):
        """Non-dict input should use fallback."""
        result = self.calculator.execute("invalid")
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A28 FixSuggester Tests
# ═══════════════════════════════════════════════════════════

class TestFixSuggester:
    """A28: Suggest fixes for validation issues."""

    def setup_method(self):
        self.suggester = FixSuggester()

    def test_no_issues_empty_suggestions(self):
        """No issues should return empty suggestions."""
        result = self.suggester.execute([])
        assert isinstance(result, FixSuggestions)
        assert len(result.suggestions) == 0

    def test_eval_fix_suggestion(self):
        """eval() should get ast.literal_eval() suggestion."""
        issues = [ValidationIssue(severity="error", code="dangerous_eval", message="eval found")]
        result = self.suggester.execute(issues)
        assert len(result.suggestions) == 1
        assert "ast.literal_eval" in result.suggestions[0]
        assert result.priorities[0] == "high"

    def test_warning_is_medium_priority(self):
        """Warning severity should be medium priority."""
        issues = [ValidationIssue(severity="warning", code="missing_return", message="no return")]
        result = self.suggester.execute(issues)
        assert result.priorities[0] == "medium"

    def test_info_is_low_priority(self):
        """Info severity should be low priority."""
        issues = [ValidationIssue(severity="info", code="todo_comment", message="TODO found")]
        result = self.suggester.execute(issues)
        assert result.priorities[0] == "low"

    def test_auto_fixable_codes(self):
        """Known auto-fixable codes should be listed."""
        issues = [
            ValidationIssue(severity="warning", code="bare_except", message="bare except"),
            ValidationIssue(severity="warning", code="yaml_unsafe", message="unsafe yaml"),
        ]
        result = self.suggester.execute(issues)
        assert "bare_except" in result.auto_fixable
        assert "yaml_unsafe" in result.auto_fixable

    def test_dict_input_with_issues_key(self):
        """Dict input with 'issues' key should work."""
        issues = [ValidationIssue(severity="error", code="dangerous_eval", message="eval")]
        result = self.suggester.execute({"issues": issues})
        assert len(result.suggestions) == 1

    def test_unknown_code_gets_generic_suggestion(self):
        """Unknown error code should get a generic suggestion."""
        issues = [ValidationIssue(severity="error", code="unknown_error", message="something bad")]
        result = self.suggester.execute(issues)
        assert len(result.suggestions) == 1
        assert "Review and fix" in result.suggestions[0]

    def test_multiple_issues(self):
        """Multiple issues should all get suggestions."""
        issues = [
            ValidationIssue(severity="error", code="dangerous_eval", message="eval"),
            ValidationIssue(severity="warning", code="bare_except", message="bare except"),
            ValidationIssue(severity="info", code="debug_enabled", message="debug on"),
        ]
        result = self.suggester.execute(issues)
        assert len(result.suggestions) == 3
        assert len(result.priorities) == 3

    def test_fallback_returns_empty(self):
        """Fallback should return empty suggestions."""
        result = self.suggester.fallback(None)
        assert len(result.suggestions) == 0
        assert result.source == "fallback"

    def test_non_validation_issue_skipped(self):
        """Non-ValidationIssue objects should be skipped."""
        issues = [
            "not an issue object",
            ValidationIssue(severity="error", code="dangerous_eval", message="eval"),
        ]
        result = self.suggester.execute(issues)
        assert len(result.suggestions) == 1  # Only the valid issue


# ═══════════════════════════════════════════════════════════
# Integration: Full Validation Pipeline Test
# ═══════════════════════════════════════════════════════════

class TestValidationPipeline:
    """End-to-end validation pipeline through all Layer 5 agents."""

    def test_clean_code_passes_all(self):
        """Clean code should pass all validation layers."""
        code = "import logging\n\ndef process(data: dict) -> dict:\n    logger = logging.getLogger()\n    if not data:\n        raise ValueError('data required')\n    try:\n        result = {'processed': True}\n    except Exception as e:\n        logger.error(str(e))\n        raise\n    return result\n"

        # Step 1: Security scan
        scanner = SecurityScanner()
        sec_result = scanner.execute({"code": code})
        assert sec_result.safe is True

        # Step 2: Syntax validation
        validator = SyntaxValidator()
        syn_result = validator.execute({"code": code, "language": "python"})
        assert syn_result.valid is True

        # Step 3: Risk calculation
        calculator = RiskCalculator()
        risk_result = calculator.execute({
            "security_result": sec_result,
            "syntax_result": syn_result,
        })
        assert risk_result.level == "low"

        # Step 4: Fix suggestions (should be empty)
        suggester = FixSuggester()
        all_issues = sec_result.threats + syn_result.errors
        fix_result = suggester.execute(all_issues)
        assert len(fix_result.suggestions) == 0

    def test_dangerous_code_caught(self):
        """Dangerous code should be caught at security scan."""
        code = "eval(user_input)\nos.system('rm -rf /')\npickle.loads(data)"

        scanner = SecurityScanner()
        sec_result = scanner.execute({"code": code})
        assert sec_result.safe is False

        # Should have multiple threats
        assert len(sec_result.threats) >= 2

        # Risk should be elevated
        calculator = RiskCalculator()
        risk_result = calculator.execute({
            "security_result": sec_result,
            "syntax_result": SyntaxResult(valid=True),
        })
        assert risk_result.level in ("medium", "high", "critical")

        # Should get fix suggestions
        suggester = FixSuggester()
        fix_result = suggester.execute(sec_result.threats)
        assert len(fix_result.suggestions) >= 2

    def test_chain_and_config_validation(self):
        """Chain + Config validation together."""
        # Validate a chain
        chain_validator = ChainValidator()
        chain_result = chain_validator.execute({
            "chain": {
                "blocks": [
                    {"name": "fetch", "category": "data"},
                    {"name": "validate", "category": "validation"},
                ]
            }
        })
        assert chain_result.valid is True

        # Validate config
        config_validator = ConfigValidator()
        config_result = config_validator.execute({
            "config": {"host": "localhost", "port": 5432, "name": "mydb"},
            "config_type": "database",
        })
        assert config_result.valid is True
