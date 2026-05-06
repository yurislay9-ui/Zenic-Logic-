"""
Tests for Layer 8: Verdict Engine agents (A40-A43).

All 4 agents tested:
  - A40 DeterministicPipeline (7 deterministic tasks)
  - A41 EvidenceCollectorV18
  - A42 ConsensusResolverV18
  - A43 VerdictEngineV18
"""

import pytest

from src.core.agents_v2.verdict import (
    DeterministicPipeline,
    EvidenceCollectorV18,
    ConsensusResolverV18,
    VerdictEngineV18,
)
from src.core.agents_v2.schemas import (
    PipelineResult,
    Evidence,
    EvidenceType,
    ConsensusResult,
    Verdict,
    VerdictInput,
    VerdictOutput,
    SecurityResult,
    SyntaxResult,
    CriticalityResult,
    IntentResult,
    ValidationIssue,
)


# ======================================================================
# A40 DeterministicPipeline Tests
# ======================================================================

class TestDeterministicPipeline:
    """A40: Execute all 7 deterministic tasks without AI."""

    def setup_method(self):
        self.pipeline = DeterministicPipeline()

    # --- Full pipeline execution ---

    def test_full_pipeline_string_input(self):
        """String input should run all 7 tasks."""
        result = self.pipeline.execute("Create a new API endpoint in app.py")
        assert isinstance(result, PipelineResult)
        assert result.classify is not None
        assert result.extract is not None
        assert result.pattern is not None
        assert result.fill is not None
        assert result.generate is not None
        assert result.explain is not None
        assert result.subtask is not None
        assert result.source == "deterministic"

    def test_full_pipeline_dict_input(self):
        """Dict input should run all 7 tasks."""
        result = self.pipeline.execute({
            "text": "Refactor the user auth module",
            "code": "def login(): pass",
            "language": "python",
        })
        assert isinstance(result, PipelineResult)
        assert result.classify is not None

    def test_full_pipeline_empty_input(self):
        """Empty input should still return PipelineResult."""
        result = self.pipeline.execute("")
        assert isinstance(result, PipelineResult)

    # --- Task 1: classify_intent ---

    def test_classify_create(self):
        """'create' should classify as CREATE."""
        result = self.pipeline.classify_intent("Create a new feature")
        assert result["operation"] == "CREATE"
        assert result["confidence"] > 0

    def test_classify_refactor(self):
        """'refactor' should classify as REFACTOR."""
        result = self.pipeline.classify_intent("Refactor the codebase")
        assert result["operation"] == "REFACTOR"

    def test_classify_delete(self):
        """'delete' should classify as DELETE."""
        result = self.pipeline.classify_intent("Delete the old module")
        assert result["operation"] == "DELETE"

    def test_classify_debug(self):
        """'fix' should classify as DEBUG."""
        result = self.pipeline.classify_intent("Fix the login bug")
        assert result["operation"] == "DEBUG"

    def test_classify_analyze(self):
        """'analyze' should classify as ANALYZE."""
        result = self.pipeline.classify_intent("Analyze the performance metrics")
        assert result["operation"] == "ANALYZE"

    def test_classify_optimize(self):
        """'optimize' should classify as OPTIMIZE."""
        result = self.pipeline.classify_intent("Optimize performance and speed up latency")
        assert result["operation"] in ("OPTIMIZE", "ANALYZE")

    def test_classify_es(self):
        """Spanish keywords should work."""
        result = self.pipeline.classify_intent("Crear una nueva funcionalidad")
        assert result["operation"] == "CREATE"

    def test_classify_goal_feature(self):
        """'feature' should set goal to FEATURE_ADD."""
        result = self.pipeline.classify_intent("Add a new feature for reporting")
        assert result["goal"] == "FEATURE_ADD"

    def test_classify_goal_security(self):
        """'security' should set goal to SECURITY_HARDEN."""
        result = self.pipeline.classify_intent("Fix security vulnerability in auth")
        assert result["goal"] == "SECURITY_HARDEN"

    def test_classify_empty(self):
        """Empty text should return SEARCH with 0 confidence."""
        result = self.pipeline.classify_intent("")
        assert result["operation"] == "SEARCH"
        assert result["confidence"] == 0.0

    # --- Task 2: extract_entities ---

    def test_extract_python_file(self):
        result = self.pipeline.extract_entities("Edit app.py to add endpoint")
        assert result["file"] == "app.py"
        assert result["lang"] == "python"

    def test_extract_javascript_file(self):
        result = self.pipeline.extract_entities("Fix bug in utils.js")
        assert result["file"] == "utils.js"
        assert result["lang"] == "javascript"

    def test_extract_function_name(self):
        result = self.pipeline.extract_entities("Fix the def process_data function")
        assert result["function"] == "process_data"

    def test_extract_language_from_keywords(self):
        result = self.pipeline.extract_entities("Write python code for data processing")
        assert result["lang"] == "python"

    def test_extract_no_file(self):
        result = self.pipeline.extract_entities("Fix the authentication system")
        assert result["file"] == ""

    def test_extract_empty(self):
        result = self.pipeline.extract_entities("")
        assert result["lang"] == "unknown"

    # --- Task 3: suggest_pattern ---

    def test_suggest_async(self):
        result = self.pipeline.suggest_pattern("handler", "Implement async processing")
        assert result["result"] == "async_await_pattern"

    def test_suggest_validator(self):
        result = self.pipeline.suggest_pattern("input", "Add validate and check data")
        assert result["result"] == "validator_pattern"

    def test_suggest_security(self):
        result = self.pipeline.suggest_pattern("auth", "Add security and authentication")
        assert result["result"] == "security_pattern"

    def test_suggest_default(self):
        result = self.pipeline.suggest_pattern("target", "Do something random")
        assert result["result"] == "default_pattern"
        assert result["confidence"] < 0.5

    # --- Task 4: fill_template_gaps ---

    def test_fill_gaps_with_context(self):
        template = "def __GAP_NAME__(): return __GAP_TYPE__"
        result = self.pipeline.fill_template_gaps(template, {"name": "process", "type": "str"})
        assert "process" in result["result"]
        assert "str" in result["result"]
        assert "__GAP_" not in result["result"]

    def test_fill_gaps_with_defaults(self):
        template = "def __GAP_NAME__(): pass"
        result = self.pipeline.fill_template_gaps(template, {})
        assert "generated" in result["result"]
        assert "__GAP_" not in result["result"]

    def test_fill_no_gaps(self):
        template = "def hello(): pass"
        result = self.pipeline.fill_template_gaps(template, {})
        assert result["result"] == template
        assert result["confidence"] == 1.0

    def test_fill_empty_template(self):
        result = self.pipeline.fill_template_gaps("", {})
        assert result["result"] == ""

    # --- Task 5: generate_pattern ---

    def test_generate_validator_python(self):
        result = self.pipeline.generate_pattern("validate input data", "python")
        assert "def" in result["result"]
        assert result["confidence"] > 0.5

    def test_generate_async_python(self):
        result = self.pipeline.generate_pattern("async await processing", "python")
        assert "async def" in result["result"]

    def test_generate_javascript(self):
        result = self.pipeline.generate_pattern("default", "javascript")
        assert result["result"] != ""

    def test_generate_default_pattern(self):
        result = self.pipeline.generate_pattern("something random", "python")
        assert result["result"] != ""
        assert result["confidence"] < 0.6

    # --- Task 6: explain_violation ---

    def test_explain_eval(self):
        result = self.pipeline.explain_violation("code", ["eval_call"])
        assert "code execution" in result["result"].lower() or "eval" in result["result"].lower()
        assert result["confidence"] == 0.95

    def test_explain_exec(self):
        result = self.pipeline.explain_violation("code", ["exec_call"])
        assert "exec" in result["result"].lower()

    def test_explain_multiple(self):
        result = self.pipeline.explain_violation("code", ["eval_call", "os_system"])
        assert len(result["result"]) > 20

    def test_explain_unknown_violation(self):
        result = self.pipeline.explain_violation("code", ["custom_issue"])
        assert "custom_issue" in result["result"]

    def test_explain_no_violations(self):
        result = self.pipeline.explain_violation("code", [])
        assert "No violations" in result["result"]

    # --- Task 7: describe_subtask ---

    def test_describe_subtask(self):
        result = self.pipeline.describe_subtask("app.py", "refactor")
        assert "refactor" in result["result"]
        assert "app" in result["result"]

    def test_describe_subtask_sanitizes(self):
        result = self.pipeline.describe_subtask("My Module.py", "create")
        assert " " not in result["result"]
        assert result["result"].islower() or "_" in result["result"]

    def test_describe_subtask_short_name(self):
        result = self.pipeline.describe_subtask("", "")
        assert result["result"] == "unnamed_subtask"

    # --- Fallback ---

    def test_fallback_returns_pipeline_result(self):
        result = self.pipeline.fallback(None)
        assert isinstance(result, PipelineResult)
        assert result.source == "fallback"


# ======================================================================
# A41 EvidenceCollectorV18 Tests
# ======================================================================

class TestEvidenceCollector:
    """A41: Collect evidence for/against a decision."""

    def setup_method(self):
        self.collector = EvidenceCollectorV18()

    def test_safe_security_evidence(self):
        result = self.collector.execute({
            "security_result": SecurityResult(safe=True),
        })
        assert len(result) > 0
        assert any(e.favors == "YES" for e in result)

    def test_unsafe_security_evidence(self):
        result = self.collector.execute({
            "security_result": SecurityResult(
                safe=False,
                threats=[ValidationIssue(code="eval_call", message="eval() detected")],
                risk_score=0.8,
            ),
        })
        assert len(result) > 0
        assert any(e.favors == "NO" for e in result)

    def test_valid_syntax_evidence(self):
        result = self.collector.execute({
            "syntax_result": SyntaxResult(valid=True),
        })
        assert any(e.favors == "YES" for e in result)

    def test_invalid_syntax_evidence(self):
        result = self.collector.execute({
            "syntax_result": SyntaxResult(
                valid=False,
                errors=[ValidationIssue(code="syntax_error", message="Invalid syntax")],
            ),
        })
        assert any(e.favors == "NO" for e in result)

    def test_low_criticality_evidence(self):
        result = self.collector.execute({
            "criticality_result": CriticalityResult(level=1, confidence=0.8),
        })
        assert any(e.favors == "YES" for e in result)

    def test_high_criticality_evidence(self):
        result = self.collector.execute({
            "criticality_result": CriticalityResult(level=3, confidence=0.9),
        })
        assert any(e.favors == "NO" for e in result)

    def test_high_intent_confidence(self):
        result = self.collector.execute({
            "intent_result": IntentResult(confidence=0.8),
        })
        assert any(e.favors == "YES" for e in result)

    def test_low_intent_confidence(self):
        result = self.collector.execute({
            "intent_result": IntentResult(confidence=0.2),
        })
        assert any(e.favors == "NO" for e in result)

    def test_combined_evidence(self):
        result = self.collector.execute({
            "security_result": SecurityResult(safe=True),
            "syntax_result": SyntaxResult(valid=True),
            "criticality_result": CriticalityResult(level=1, confidence=0.8),
        })
        assert len(result) >= 3

    def test_non_dict_input_returns_empty(self):
        result = self.collector.execute("invalid input")
        assert result == []

    def test_empty_dict_returns_empty(self):
        result = self.collector.execute({})
        assert result == []

    def test_evidence_types_are_set(self):
        result = self.collector.execute({
            "security_result": SecurityResult(safe=True),
            "syntax_result": SyntaxResult(valid=True),
        })
        types = {e.evidence_type for e in result}
        assert EvidenceType.SECURITY_CHECK in types
        assert EvidenceType.SYNTAX_VALID in types

    def test_fallback_returns_empty(self):
        result = self.collector.fallback(None)
        assert result == []


# ======================================================================
# A42 ConsensusResolverV18 Tests
# ======================================================================

class TestConsensusResolver:
    """A42: Resolve evidence into consensus or flag for AI."""

    def setup_method(self):
        self.resolver = ConsensusResolverV18()

    def test_unanimous_yes(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="YES", weight=0.8),
            Evidence(evidence_type=EvidenceType.PATTERN_MATCH, favors="YES", weight=0.7),
        ]
        result = self.resolver.execute(evidence)
        assert isinstance(result, ConsensusResult)
        assert result.verdict == Verdict.YES
        assert not result.needs_llm
        assert result.unanimous is True

    def test_unanimous_no(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="NO", weight=0.8),
            Evidence(evidence_type=EvidenceType.KEYWORD_CLASSIFY, favors="NO", weight=0.6),
        ]
        result = self.resolver.execute(evidence)
        assert result.verdict == Verdict.NO
        assert not result.needs_llm

    def test_security_veto(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SECURITY_CHECK, favors="NO", weight=0.9),
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="YES", weight=0.8),
            Evidence(evidence_type=EvidenceType.PATTERN_MATCH, favors="YES", weight=0.7),
        ]
        result = self.resolver.execute(evidence)
        assert result.verdict == Verdict.NO
        assert result.source == "deterministic_veto"
        assert not result.needs_llm

    def test_sandbox_veto(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SANDBOX_PASS, favors="NO", weight=0.8),
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="YES", weight=0.9),
        ]
        result = self.resolver.execute(evidence)
        assert result.verdict == Verdict.NO
        assert result.source == "deterministic_veto"

    def test_security_veto_low_weight_not_vetoed(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SECURITY_CHECK, favors="NO", weight=0.5),
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="YES", weight=0.9),
        ]
        result = self.resolver.execute(evidence)
        assert result.source != "deterministic_veto"

    def test_tie_requires_llm(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.PATTERN_MATCH, favors="YES", weight=0.5),
            Evidence(evidence_type=EvidenceType.KEYWORD_CLASSIFY, favors="NO", weight=0.5),
        ]
        result = self.resolver.execute(evidence)
        assert result.needs_llm is True

    def test_empty_evidence_needs_llm(self):
        result = self.resolver.execute([])
        assert result.needs_llm is True
        assert result.verdict == Verdict.NO

    def test_dict_input(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="YES", weight=0.8),
        ]
        result = self.resolver.execute({"evidence": evidence})
        assert result.verdict == Verdict.YES

    def test_score_normalized(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="YES", weight=0.9),
        ]
        result = self.resolver.execute(evidence)
        assert -1.0 <= result.score <= 1.0

    def test_signals_count(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="YES", weight=0.8),
            Evidence(evidence_type=EvidenceType.PATTERN_MATCH, favors="YES", weight=0.6),
        ]
        result = self.resolver.execute(evidence)
        assert result.signals_count == 2

    def test_evidence_for_against_populated(self):
        evidence = [
            Evidence(evidence_type=EvidenceType.SYNTAX_VALID, favors="YES", weight=0.8),
            Evidence(evidence_type=EvidenceType.KEYWORD_CLASSIFY, favors="NO", weight=0.3),
        ]
        result = self.resolver.execute(evidence)
        assert len(result.evidence_for) >= 1
        assert len(result.evidence_against) >= 1

    def test_fallback_returns_no(self):
        result = self.resolver.fallback(None)
        assert result.verdict == Verdict.NO
        assert result.confidence < 0.5
        assert result.source == "fallback"


# ======================================================================
# A43 VerdictEngineV18 Tests
# ======================================================================

class TestVerdictEngine:
    """A43: Binary verdict engine -- the ONLY place AI is used."""

    def setup_method(self):
        self.engine = VerdictEngineV18()

    def test_consensus_clear_no_ai(self):
        consensus = ConsensusResult(
            verdict=Verdict.YES,
            confidence=0.9,
            needs_llm=False,
        )
        result = self.engine.execute({"consensus_result": consensus})
        assert isinstance(result, VerdictOutput)
        assert result.verdict == Verdict.YES
        assert result.llm_used is False
        assert result.source == "deterministic_consensus"

    def test_consensus_clear_no_verdict(self):
        consensus = ConsensusResult(
            verdict=Verdict.NO,
            confidence=0.9,
            needs_llm=False,
        )
        result = self.engine.execute({"consensus_result": consensus})
        assert result.verdict == Verdict.NO
        assert result.llm_used is False

    def test_no_model_returns_no(self):
        result = self.engine.execute({"question": "Is this safe?"})
        assert result.verdict == Verdict.NO
        assert result.source in ("fallback_no_model", "fallback_circuit_open")

    def test_parse_verdict_yes(self):
        assert VerdictEngineV18._parse_verdict_response("YES") == "YES"

    def test_parse_verdict_no(self):
        assert VerdictEngineV18._parse_verdict_response("NO") == "NO"

    def test_parse_verdict_yes_with_think(self):
        response = " YES"
        assert VerdictEngineV18._parse_verdict_response(response) == "YES"

    def test_parse_verdict_no_with_think(self):
        response = " NO"
        assert VerdictEngineV18._parse_verdict_response(response) == "NO"

    def test_parse_verdict_si(self):
        assert VerdictEngineV18._parse_verdict_response("SI") == "YES"

    def test_parse_verdict_ambiguous(self):
        assert VerdictEngineV18._parse_verdict_response("MAYBE") is None

    def test_parse_verdict_empty(self):
        assert VerdictEngineV18._parse_verdict_response("") is None

    def test_parse_verdict_none(self):
        assert VerdictEngineV18._parse_verdict_response(None) is None

    def test_parse_verdict_yes_punctuation(self):
        assert VerdictEngineV18._parse_verdict_response("YES.") == "YES"

    def test_verdict_input_object(self):
        vinput = VerdictInput(question="Should this be approved?")
        result = self.engine.execute(vinput)
        assert isinstance(result, VerdictOutput)

    def test_wire_mini_ai(self):
        self.engine.wire_mini_ai(None)

    def test_verdict_stats_initial(self):
        stats = self.engine.verdict_stats
        assert stats["total_verdicts"] == 0
        assert "yes_count" in stats
        assert "no_count" in stats

    def test_fallback_returns_no(self):
        result = self.engine.fallback(None)
        assert result.verdict == Verdict.NO
        assert result.confidence < 0.5
        assert result.source == "fallback"
        assert result.llm_used is False


# ======================================================================
# Integration: Full Verdict Pipeline Test
# ======================================================================

class TestVerdictPipeline:
    """End-to-end verdict pipeline through all Layer 8 agents."""

    def test_safe_code_verdict_pipeline(self):
        """Safe code should go through pipeline -> YES without AI."""
        pipeline = DeterministicPipeline()
        pipe_result = pipeline.execute({
            "text": "Create a validation function in utils.py",
        })
        assert pipe_result.classify is not None

        collector = EvidenceCollectorV18()
        evidence = collector.execute({
            "security_result": SecurityResult(safe=True),
            "syntax_result": SyntaxResult(valid=True),
            "criticality_result": CriticalityResult(level=1, confidence=0.8),
            "intent_result": IntentResult(confidence=0.7),
        })
        assert len(evidence) > 0

        resolver = ConsensusResolverV18()
        consensus = resolver.execute(evidence)
        assert consensus.verdict == Verdict.YES
        assert not consensus.needs_llm

        engine = VerdictEngineV18()
        verdict = engine.execute({"consensus_result": consensus})
        assert verdict.verdict == Verdict.YES
        assert verdict.llm_used is False

    def test_unsafe_code_verdict_pipeline(self):
        """Unsafe code should trigger security veto -> NO without AI."""
        collector = EvidenceCollectorV18()
        evidence = collector.execute({
            "security_result": SecurityResult(
                safe=False,
                threats=[ValidationIssue(code="eval_call", message="eval() detected")],
                risk_score=0.9,
            ),
            "syntax_result": SyntaxResult(valid=True),
        })

        resolver = ConsensusResolverV18()
        consensus = resolver.execute(evidence)
        assert consensus.verdict == Verdict.NO
        assert consensus.source == "deterministic_veto"

        engine = VerdictEngineV18()
        verdict = engine.execute({"consensus_result": consensus})
        assert verdict.verdict == Verdict.NO
        assert verdict.llm_used is False

    def test_ambiguous_evidence_pipeline(self):
        """Ambiguous evidence should flag needs_llm=True."""
        evidence = [
            Evidence(evidence_type=EvidenceType.PATTERN_MATCH, favors="YES", weight=0.5),
            Evidence(evidence_type=EvidenceType.KEYWORD_CLASSIFY, favors="NO", weight=0.5),
        ]

        resolver = ConsensusResolverV18()
        consensus = resolver.execute(evidence)
        assert consensus.needs_llm is True

        engine = VerdictEngineV18()
        verdict = engine.execute({"consensus_result": consensus})
        assert verdict.verdict == Verdict.NO
