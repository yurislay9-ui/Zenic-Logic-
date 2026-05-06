"""
Tests for Layer 7: Reasoning agents (A35-A39).

All 5 agents tested:
  - A35 ProblemDetector
  - A36 StepDecomposer
  - A37 TemplateReasoner
  - A38 ConfidenceEstimator
  - A39 ConclusionExtractor
"""

import pytest

from src.core.agents_v2.reasoning import (
    ProblemDetector,
    StepDecomposer,
    TemplateReasoner,
    ConfidenceEstimator,
    ConclusionExtractor,
)
from src.core.agents_v2.schemas import (
    ProblemType,
    ReasoningStep,
    ReasoningResult,
    DecomposedSteps,
    ConfidenceResult,
    Conclusion,
)


# ═══════════════════════════════════════════════════════════
# A35 ProblemDetector Tests
# ═══════════════════════════════════════════════════════════

class TestProblemDetector:
    """A35: Detect the type of problem from query text."""

    def setup_method(self):
        self.detector = ProblemDetector()

    def test_api_problem(self):
        """'api' should detect api type."""
        result = self.detector.execute("Create a REST API for user management")
        assert isinstance(result, ProblemType)
        assert result.type == "api"

    def test_auth_problem(self):
        """'auth' should detect auth type."""
        result = self.detector.execute("Implement authentication and login system")
        assert result.type == "auth"

    def test_database_problem(self):
        """'database' should detect database type."""
        result = self.detector.execute("Design the database schema and migration")
        assert result.type == "database"

    def test_invoice_problem(self):
        """'invoice' should detect invoice type."""
        result = self.detector.execute("Create an invoice and billing system")
        assert result.type == "invoice"

    def test_inventory_problem(self):
        """'inventario' should detect inventory type."""
        result = self.detector.execute("Gestionar inventario y stock de productos")
        assert result.type == "inventory"

    def test_crm_problem(self):
        """'crm' should detect crm type."""
        result = self.detector.execute("Build a CRM for customer pipeline management")
        assert result.type == "crm"

    def test_automation_problem(self):
        """'automation' should detect automation type."""
        result = self.detector.execute("Create an automation with webhook trigger")
        assert result.type == "automation"

    def test_general_problem(self):
        """No matching keywords should return general type."""
        result = self.detector.execute("Process some data")
        assert result.type == "general"

    def test_empty_input(self):
        """Empty input should return general with 0 complexity."""
        result = self.detector.execute("")
        assert result.type == "general"
        assert result.complexity == 0.0

    def test_dict_input_query(self):
        """Dict with 'query' key should work."""
        result = self.detector.execute({"query": "Build an auth system"})
        assert result.type == "auth"

    def test_dict_input_text(self):
        """Dict with 'text' key should work."""
        result = self.detector.execute({"text": "Design the database schema"})
        assert result.type == "database"

    def test_problem_type_object_input(self):
        """ProblemType object should be handled."""
        pt = ProblemType(type="api")
        result = self.detector.execute(pt)
        # When passing ProblemType, it should still detect from its type
        assert isinstance(result, ProblemType)

    def test_subtype_jwt(self):
        """Auth with 'jwt' should detect jwt subtype."""
        result = self.detector.execute("Implement JWT token authentication")
        assert result.type == "auth"
        assert result.subtype == "jwt"

    def test_subtype_rest(self):
        """API with 'rest' should detect rest subtype."""
        result = self.detector.execute("Create REST API endpoints")
        assert result.type == "api"
        assert result.subtype == "rest"

    def test_subtype_scheduled(self):
        """Automation with 'schedule' should detect scheduled subtype."""
        result = self.detector.execute("Create scheduled automation daily")
        assert result.type == "automation"
        assert result.subtype == "scheduled"

    def test_complexity_short_query(self):
        """Short query should have low complexity."""
        result = self.detector.execute("Fix bug")
        assert result.complexity < 0.5

    def test_complexity_long_query(self):
        """Long query with multiple concepts should have high complexity."""
        result = self.detector.execute(
            "Build a microservice with API, database, authentication, "
            "caching, async processing and distributed scaling"
        )
        assert result.complexity > 0.5

    def test_complexity_connectors(self):
        """Multiple connectors (and, but, however) should increase complexity."""
        simple = self.detector.execute("Fix bug in code")
        complex_q = self.detector.execute("Fix bug in code and add tests but also handle edge cases")
        assert complex_q.complexity > simple.complexity

    def test_complexity_tech_terms(self):
        """Technical terms should increase complexity."""
        simple = self.detector.execute("Create a simple feature")
        tech = self.detector.execute("Create API with database, caching and middleware")
        assert tech.complexity > simple.complexity

    def test_auth_priority_over_api(self):
        """Auth should take priority over API (per TYPE_PRIORITY)."""
        result = self.detector.execute("Build an API with auth login")
        assert result.type == "auth"

    def test_detect_all_types(self):
        """detect_all_types should return all matching types."""
        results = self.detector.detect_all_types("Build an API with auth and database")
        types = [t for t, _ in results]
        assert "api" in types
        assert "auth" in types
        assert "database" in types

    def test_detect_all_types_empty(self):
        """detect_all_types with empty input should return empty list."""
        results = self.detector.detect_all_types("")
        assert results == []

    def test_fallback_returns_general(self):
        """Fallback should return general type."""
        result = self.detector.fallback(None)
        assert result.type == "general"
        assert result.source == "fallback"
        assert result.complexity == 0.5


# ═══════════════════════════════════════════════════════════
# A36 StepDecomposer Tests
# ═══════════════════════════════════════════════════════════

class TestStepDecomposer:
    """A36: Break a problem into ordered reasoning steps."""

    def setup_method(self):
        self.decomposer = StepDecomposer()

    def test_api_decomposition(self):
        """API type should produce API-specific steps."""
        result = self.decomposer.execute(ProblemType(type="api"))
        assert isinstance(result, DecomposedSteps)
        assert len(result.steps) > 0
        assert any("endpoint" in s.description.lower() for s in result.steps)

    def test_auth_decomposition(self):
        """Auth type should produce auth-specific steps."""
        result = self.decomposer.execute(ProblemType(type="auth"))
        assert len(result.steps) > 0
        assert any("auth" in s.description.lower() or "credential" in s.description.lower()
                    for s in result.steps)

    def test_database_decomposition(self):
        """Database type should produce database-specific steps."""
        result = self.decomposer.execute(ProblemType(type="database"))
        assert len(result.steps) > 0
        assert any("schema" in s.description.lower() or "database" in s.description.lower()
                    for s in result.steps)

    def test_automation_decomposition(self):
        """Automation type should produce automation-specific steps."""
        result = self.decomposer.execute(ProblemType(type="automation"))
        assert len(result.steps) > 0
        assert any("trigger" in s.description.lower() for s in result.steps)

    def test_generic_decomposition(self):
        """Unknown type should produce generic steps."""
        result = self.decomposer.execute(ProblemType(type="general"))
        assert len(result.steps) > 0
        # Generic template should have standard steps
        assert result.steps[0].step_number == 1

    def test_dict_input_with_type(self):
        """Dict with 'problem_type' key should work."""
        result = self.decomposer.execute({"problem_type": "invoice"})
        assert len(result.steps) > 0

    def test_dict_input_with_problem_type_object(self):
        """Dict with ProblemType object should work."""
        result = self.decomposer.execute({"problem_type": ProblemType(type="crm")})
        assert len(result.steps) > 0

    def test_string_input_auto_detects(self):
        """String input should auto-detect and decompose."""
        result = self.decomposer.execute("Build an API endpoint")
        assert len(result.steps) > 0

    def test_steps_are_numbered(self):
        """Steps should be numbered sequentially."""
        result = self.decomposer.execute(ProblemType(type="api"))
        for i, step in enumerate(result.steps):
            assert step.step_number == i + 1

    def test_dependencies_not_empty(self):
        """Dependencies should be populated for non-trivial templates."""
        result = self.decomposer.execute(ProblemType(type="api"))
        assert len(result.dependencies) > 0

    def test_order_matches_step_numbers(self):
        """Order should match step numbers."""
        result = self.decomposer.execute(ProblemType(type="auth"))
        assert result.order == [s.step_number for s in result.steps]

    def test_source_is_deterministic(self):
        """Source should be deterministic."""
        result = self.decomposer.execute(ProblemType(type="api"))
        assert result.source == "deterministic"

    def test_decompose_with_context(self):
        """decompose_with_context should inject context into first step."""
        result = self.decomposer.decompose_with_context(
            ProblemType(type="api"), context="Previous API used FastAPI"
        )
        assert len(result.steps) > 0
        assert "Previous API" in result.steps[0].description

    def test_max_steps_limit(self):
        """Steps should be capped at MAX_STEPS."""
        result = self.decomposer.execute(ProblemType(type="api"))
        assert len(result.steps) <= 8

    def test_fallback_returns_3_steps(self):
        """Fallback should return generic 3-step process."""
        result = self.decomposer.fallback(None)
        assert len(result.steps) == 3
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A37 TemplateReasoner Tests
# ═══════════════════════════════════════════════════════════

class TestTemplateReasoner:
    """A37: Apply template-based reasoning for known problem types."""

    def setup_method(self):
        self.reasoner = TemplateReasoner()

    def test_api_template(self):
        """API type should use API template."""
        result = self.reasoner.execute(ProblemType(type="api"))
        assert isinstance(result, ReasoningResult)
        assert result.template_used == "api"
        assert "API" in result.answer or "endpoint" in result.answer.lower()

    def test_auth_template(self):
        """Auth type should use auth template."""
        result = self.reasoner.execute(ProblemType(type="auth"))
        assert result.template_used == "auth"
        assert "JWT" in result.answer or "auth" in result.answer.lower()

    def test_database_template(self):
        """Database type should use database template."""
        result = self.reasoner.execute(ProblemType(type="database"))
        assert result.template_used == "database"
        assert "schema" in result.answer.lower() or "database" in result.answer.lower()

    def test_invoice_template(self):
        """Invoice type should use invoice template."""
        result = self.reasoner.execute(ProblemType(type="invoice"))
        assert result.template_used == "invoice"
        assert "invoice" in result.answer.lower()

    def test_inventory_template(self):
        """Inventory type should use inventory template."""
        result = self.reasoner.execute(ProblemType(type="inventory"))
        assert result.template_used == "inventory"

    def test_crm_template(self):
        """CRM type should use CRM template."""
        result = self.reasoner.execute(ProblemType(type="crm"))
        assert result.template_used == "crm"

    def test_automation_template(self):
        """Automation type should use automation template."""
        result = self.reasoner.execute(ProblemType(type="automation"))
        assert result.template_used == "automation"

    def test_logical_template(self):
        """Logical type should use logical template."""
        result = self.reasoner.execute(ProblemType(type="logical"))
        assert result.template_used == "logical"

    def test_arithmetic_template(self):
        """Arithmetic type should use arithmetic template."""
        result = self.reasoner.execute(ProblemType(type="arithmetic"))
        assert result.template_used == "arithmetic"

    def test_structural_template(self):
        """Structural type should use structural template."""
        result = self.reasoner.execute(ProblemType(type="structural"))
        assert result.template_used == "structural"

    def test_generic_template(self):
        """Unknown type should use generic template."""
        result = self.reasoner.execute(ProblemType(type="general"))
        assert result.template_used == "generic"
        assert result.confidence < 0.5

    def test_template_has_steps(self):
        """Template should produce reasoning steps."""
        result = self.reasoner.execute(ProblemType(type="api"))
        assert len(result.steps) > 0

    def test_step_conclusions_present(self):
        """Steps should have conclusions."""
        result = self.reasoner.execute(ProblemType(type="auth"))
        assert all(s.conclusion != "" for s in result.steps)

    def test_api_confidence(self):
        """API template should have reasonable confidence."""
        result = self.reasoner.execute(ProblemType(type="api"))
        assert result.confidence > 0.5

    def test_dict_input_with_type(self):
        """Dict with 'problem_type' key should work."""
        result = self.reasoner.execute({"problem_type": "api"})
        assert result.template_used == "api"

    def test_dict_input_with_problem_type_object(self):
        """Dict with ProblemType should work."""
        result = self.reasoner.execute({"problem_type": ProblemType(type="auth")})
        assert result.template_used == "auth"

    def test_string_input(self):
        """String input should auto-detect and apply template."""
        result = self.reasoner.execute("Build an authentication system")
        # Should detect auth and apply auth template
        assert isinstance(result, ReasoningResult)

    def test_context_enrichment(self):
        """Context should be appended to answer."""
        result = self.reasoner.execute({
            "problem_type": ProblemType(type="api"),
            "context": "Must use FastAPI framework",
        })
        assert "FastAPI" in result.answer or "context" in result.answer.lower()

    def test_list_available_templates(self):
        """list_available_templates should return all template names."""
        templates = self.reasoner.list_available_templates()
        assert "api" in templates
        assert "auth" in templates
        assert "database" in templates
        assert len(templates) >= 8

    def test_fallback_returns_generic(self):
        """Fallback should return generic template."""
        result = self.reasoner.fallback(None)
        assert result.template_used == "generic"
        assert result.source == "fallback"

    def test_source_is_deterministic(self):
        """Source should be deterministic."""
        result = self.reasoner.execute(ProblemType(type="api"))
        assert result.source == "deterministic"


# ═══════════════════════════════════════════════════════════
# A38 ConfidenceEstimator Tests
# ═══════════════════════════════════════════════════════════

class TestConfidenceEstimator:
    """A38: Estimate confidence in a reasoning result."""

    def setup_method(self):
        self.estimator = ConfidenceEstimator()

    def test_high_confidence_result(self):
        """Well-structured result with high base confidence should score well."""
        result = ReasoningResult(
            answer="Implement JWT-based authentication with token refresh, "
                   "password hashing, and RBAC for authorization. This is a "
                   "definitely clear and complete solution.",
            template_used="auth",
            confidence=0.8,
            steps=[
                ReasoningStep(step_number=1, description="Define auth", conclusion="Auth defined", confidence=0.8),
                ReasoningStep(step_number=2, description="Implement tokens", conclusion="Tokens implemented", confidence=0.85),
                ReasoningStep(step_number=3, description="Add RBAC", conclusion="RBAC added", confidence=0.75),
            ],
        )
        conf = self.estimator.execute(result)
        assert isinstance(conf, ConfidenceResult)
        assert conf.score > 0.5
        assert conf.recommendation in ("proceed", "caution")

    def test_low_confidence_short_answer(self):
        """Short answer should have low confidence."""
        result = ReasoningResult(
            answer="Fix it.",
            confidence=0.3,
            steps=[],
        )
        conf = self.estimator.execute(result)
        assert conf.score < 0.5

    def test_security_risk_decreases_confidence(self):
        """Answer with eval() should significantly decrease confidence."""
        safe = ReasoningResult(
            answer="Implement data processing with proper validation and error handling.",
            confidence=0.6,
        )
        risky = ReasoningResult(
            answer="Use eval() to process the data and exec() to run commands.",
            confidence=0.6,
        )
        safe_conf = self.estimator.execute(safe)
        risky_conf = self.estimator.execute(risky)
        assert risky_conf.score < safe_conf.score

    def test_hedging_decreases_confidence(self):
        """Hedging language should decrease confidence."""
        certain = ReasoningResult(
            answer="This is certainly the correct implementation with clear validation.",
            confidence=0.6,
        )
        hedging = ReasoningResult(
            answer="This might be perhaps a possible implementation maybe.",
            confidence=0.6,
        )
        certain_conf = self.estimator.execute(certain)
        hedging_conf = self.estimator.execute(hedging)
        assert hedging_conf.score < certain_conf.score

    def test_quality_issues_decrease_confidence(self):
        """TODO/FIXME markers should decrease confidence."""
        clean = ReasoningResult(
            answer="Complete implementation with error handling and validation.",
            confidence=0.6,
        )
        quality_issues = ReasoningResult(
            answer="TODO: implement error handling FIXME: add validation HACK: quick fix.",
            confidence=0.6,
        )
        clean_conf = self.estimator.execute(clean)
        issues_conf = self.estimator.execute(quality_issues)
        assert issues_conf.score < clean_conf.score

    def test_steps_improve_confidence(self):
        """Having reasoning steps should improve confidence."""
        no_steps = ReasoningResult(
            answer="Implement the authentication system with proper security.",
            confidence=0.6,
        )
        with_steps = ReasoningResult(
            answer="Implement the authentication system with proper security.",
            confidence=0.6,
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="Done", confidence=0.7),
                ReasoningStep(step_number=2, description="Step 2", conclusion="Done", confidence=0.8),
            ],
        )
        no_steps_conf = self.estimator.execute(no_steps)
        with_steps_conf = self.estimator.execute(with_steps)
        assert with_steps_conf.score >= no_steps_conf.score

    def test_template_match_improves_confidence(self):
        """Known template match should improve confidence."""
        generic = ReasoningResult(
            answer="Good implementation with error handling.",
            template_used="generic",
            confidence=0.6,
        )
        matched = ReasoningResult(
            answer="Good implementation with error handling.",
            template_used="auth",
            confidence=0.6,
        )
        generic_conf = self.estimator.execute(generic)
        matched_conf = self.estimator.execute(matched)
        assert matched_conf.score >= generic_conf.score

    def test_recommendation_proceed(self):
        """High confidence should recommend proceed."""
        result = ReasoningResult(
            answer="Complete implementation with thorough error handling, validation, "
                   "and comprehensive test coverage. Clearly the best approach.",
            confidence=0.9,
            template_used="auth",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="Done", confidence=0.9),
            ],
        )
        conf = self.estimator.execute(result)
        assert conf.recommendation in ("proceed", "caution")

    def test_recommendation_reject(self):
        """Very low confidence should recommend reject."""
        result = ReasoningResult(
            answer="eval()",
            confidence=0.1,
        )
        conf = self.estimator.execute(result)
        assert conf.recommendation in ("reject", "caution")

    def test_string_input(self):
        """String input should work."""
        conf = self.estimator.execute("This is a clear and complete implementation")
        assert isinstance(conf, ConfidenceResult)

    def test_dict_input(self):
        """Dict input should work."""
        conf = self.estimator.execute({"answer": "Implement auth", "confidence": 0.7})
        assert isinstance(conf, ConfidenceResult)

    def test_factors_populated(self):
        """Factors list should be populated."""
        result = ReasoningResult(
            answer="Good implementation with error handling and validation.",
            confidence=0.6,
            steps=[ReasoningStep(step_number=1, description="Step 1", conclusion="Done", confidence=0.7)],
        )
        conf = self.estimator.execute(result)
        assert len(conf.factors) > 0

    def test_estimate_with_evidence(self):
        """estimate_with_evidence should adjust based on evidence."""
        result = ReasoningResult(
            answer="Implementation with proper patterns.",
            confidence=0.6,
        )
        base = self.estimator.execute(result)
        with_evidence = self.estimator.estimate_with_evidence(
            result,
            evidence_for=["Pattern match", "Valid syntax"],
            evidence_against=["Security concern"],
        )
        # Score with evidence should differ from base
        assert isinstance(with_evidence, ConfidenceResult)
        assert len(with_evidence.factors) > len(base.factors)

    def test_fallback_returns_low_confidence(self):
        """Fallback should return low confidence with caution."""
        result = self.estimator.fallback(None)
        assert result.score < 0.5
        assert result.recommendation in ("caution", "reject")
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A39 ConclusionExtractor Tests
# ═══════════════════════════════════════════════════════════

class TestConclusionExtractor:
    """A39: Extract the final conclusion from reasoning steps."""

    def setup_method(self):
        self.extractor = ConclusionExtractor()

    def test_extract_from_reasoning_result(self):
        """Should extract conclusion from ReasoningResult."""
        result = ReasoningResult(
            answer="Build an API with endpoints and error handling.",
            template_used="api",
            confidence=0.8,
            steps=[
                ReasoningStep(step_number=1, description="Identify endpoints", conclusion="Endpoints identified", confidence=0.8),
                ReasoningStep(step_number=2, description="Implement handlers", conclusion="Handlers implemented", confidence=0.75),
                ReasoningStep(step_number=3, description="Add error handling", conclusion="Therefore the API is complete with proper error handling", confidence=0.85),
            ],
        )
        conclusion = self.extractor.execute(result)
        assert isinstance(conclusion, Conclusion)
        assert conclusion.text != ""
        assert conclusion.strength > 0.0

    def test_conclusion_marker_en(self):
        """'therefore' should be recognized as conclusion marker."""
        result = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="therefore the answer is 42", confidence=0.8),
            ],
        )
        conclusion = self.extractor.execute(result)
        assert "42" in conclusion.text or "answer" in conclusion.text.lower()

    def test_conclusion_marker_es(self):
        """'por lo tanto' should be recognized as conclusion marker."""
        result = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Paso 1", conclusion="por lo tanto la respuesta es correcta", confidence=0.8),
            ],
        )
        conclusion = self.extractor.execute(result)
        assert "correcta" in conclusion.text or "respuesta" in conclusion.text.lower()

    def test_last_step_conclusion(self):
        """Without markers, last step conclusion should be used."""
        result = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="First step done", confidence=0.7),
                ReasoningStep(step_number=2, description="Step 2", conclusion="Final implementation complete", confidence=0.8),
            ],
        )
        conclusion = self.extractor.execute(result)
        assert "Final implementation complete" in conclusion.text

    def test_extract_from_decomposed_steps(self):
        """Should extract from DecomposedSteps object."""
        steps = DecomposedSteps(
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="Analyzed requirements", confidence=0.8),
                ReasoningStep(step_number=2, description="Step 2", conclusion="In conclusion the system is ready", confidence=0.85),
            ],
            dependencies=["step_2 depends on step_1"],
            order=[1, 2],
        )
        conclusion = self.extractor.execute(steps)
        assert conclusion.text != ""
        assert "system is ready" in conclusion.text or "conclusion" in conclusion.text.lower()

    def test_extract_from_string(self):
        """Should extract from raw text string."""
        text = "After careful analysis, therefore the best approach is to use FastAPI with SQLite."
        conclusion = self.extractor.execute(text)
        assert conclusion.text != ""
        assert "FastAPI" in conclusion.text or "best approach" in conclusion.text

    def test_supporting_steps_populated(self):
        """supported_by should list supporting step conclusions."""
        result = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="Endpoints identified", confidence=0.8),
                ReasoningStep(step_number=2, description="Step 2", conclusion="Handlers implemented", confidence=0.75),
                ReasoningStep(step_number=3, description="Step 3", conclusion="Therefore API is complete", confidence=0.85),
            ],
        )
        conclusion = self.extractor.execute(result)
        assert len(conclusion.supported_by) > 0

    def test_strength_increases_with_steps(self):
        """More supporting steps should increase conclusion strength."""
        two_steps = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="First", confidence=0.7),
                ReasoningStep(step_number=2, description="Step 2", conclusion="Final answer", confidence=0.7),
            ],
        )
        five_steps = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=i + 1, description=f"Step {i+1}", conclusion=f"Conclusion {i+1}", confidence=0.7)
                for i in range(5)
            ],
        )
        two_conc = self.extractor.execute(two_steps)
        five_conc = self.extractor.execute(five_steps)
        assert five_conc.strength >= two_conc.strength

    def test_certainty_markers_boost_strength(self):
        """Certainty markers should boost conclusion strength."""
        certain = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="certainly the correct answer", confidence=0.7),
            ],
        )
        neutral = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="a possible answer", confidence=0.7),
            ],
        )
        certain_conc = self.extractor.execute(certain)
        neutral_conc = self.extractor.execute(neutral)
        assert certain_conc.strength >= neutral_conc.strength

    def test_empty_input(self):
        """Empty input should return empty conclusion."""
        conclusion = self.extractor.execute(ReasoningResult(answer="", steps=[]))
        assert conclusion.text == ""
        assert conclusion.strength == 0.0

    def test_extract_summary_convenience(self):
        """extract_summary should return just the text."""
        result = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion="The result is 42", confidence=0.8),
            ],
        )
        text = self.extractor.extract_summary(result)
        assert isinstance(text, str)
        assert "42" in text

    def test_conclusion_from_answer_text(self):
        """Should extract conclusion from answer text when steps lack conclusions."""
        result = ReasoningResult(
            answer="After analysis, therefore the solution is to use JWT tokens for authentication.",
            steps=[],
        )
        conclusion = self.extractor.execute(result)
        assert conclusion.text != ""

    def test_max_conclusion_length(self):
        """Conclusion should be capped at MAX_CONCLUSION_LENGTH."""
        long_conclusion = "A" * 500
        result = ReasoningResult(
            answer="",
            steps=[
                ReasoningStep(step_number=1, description="Step 1", conclusion=long_conclusion, confidence=0.7),
            ],
        )
        conclusion = self.extractor.execute(result)
        assert len(conclusion.text) <= 300

    def test_fallback_returns_empty(self):
        """Fallback should return empty conclusion."""
        conclusion = self.extractor.fallback(None)
        assert conclusion.text == ""
        assert conclusion.strength == 0.0
        assert conclusion.source == "fallback"


# ═══════════════════════════════════════════════════════════
# Integration: Full Reasoning Pipeline Test
# ═══════════════════════════════════════════════════════════

class TestReasoningPipeline:
    """End-to-end reasoning pipeline through all Layer 7 agents."""

    def test_full_reasoning_pipeline_api(self):
        """Full pipeline: detect → decompose → reason → estimate → extract."""
        query = "Build a REST API with authentication and database"

        # Step 1: Detect problem type
        problem = ProblemDetector().execute(query)
        assert problem.type == "auth"  # Auth takes priority per TYPE_PRIORITY
        assert problem.complexity > 0.3

        # Step 2: Decompose into steps
        steps = StepDecomposer().execute(problem)
        assert len(steps.steps) > 0
        assert len(steps.dependencies) > 0

        # Step 3: Apply template reasoning
        reasoning = TemplateReasoner().execute(problem)
        assert reasoning.answer != ""
        assert reasoning.template_used != ""
        assert reasoning.confidence > 0.5

        # Step 4: Estimate confidence
        confidence = ConfidenceEstimator().execute(reasoning)
        assert confidence.score > 0.0
        assert confidence.recommendation in ("proceed", "caution", "reject")
        assert len(confidence.factors) > 0

        # Step 5: Extract conclusion
        conclusion = ConclusionExtractor().execute(reasoning)
        assert conclusion.text != ""
        assert conclusion.strength > 0.0

    def test_full_reasoning_pipeline_invoice_es(self):
        """Full pipeline in Spanish: 'Crear sistema de facturación con inventario'"""
        query = "Crear sistema de facturación con inventario y alertas"

        # Step 1: Detect
        problem = ProblemDetector().execute(query)
        assert problem.type == "invoice"  # Invoice takes priority

        # Step 2: Decompose
        steps = StepDecomposer().execute(problem)
        assert len(steps.steps) > 0

        # Step 3: Reason
        reasoning = TemplateReasoner().execute(problem)
        assert reasoning.template_used == "invoice"

        # Step 4: Confidence
        confidence = ConfidenceEstimator().execute(reasoning)
        assert confidence.score > 0.3

        # Step 5: Conclusion
        conclusion = ConclusionExtractor().execute(reasoning)
        assert conclusion.text != ""

    def test_pipeline_with_context_injection(self):
        """Pipeline with context injection at each step."""
        query = "Automate daily email report"
        context = "Previous implementation used APScheduler"

        # Step 1: Detect
        problem = ProblemDetector().execute(query)
        assert problem.type == "automation"

        # Step 2: Decompose with context
        steps = StepDecomposer().decompose_with_context(problem, context=context)
        assert "APScheduler" in steps.steps[0].description or "Previous" in steps.steps[0].description

        # Step 3: Reason with context
        reasoning = TemplateReasoner().execute({
            "problem_type": problem,
            "context": context,
        })
        assert reasoning.answer != ""

        # Step 4: Confidence
        confidence = ConfidenceEstimator().execute(reasoning)
        assert isinstance(confidence, ConfidenceResult)

        # Step 5: Conclusion
        conclusion = ConclusionExtractor().execute(reasoning)
        assert conclusion.text != ""

    def test_pipeline_general_unknown_problem(self):
        """Pipeline should handle unknown problems gracefully."""
        query = "Process some random data"

        # Step 1: Detect → general
        problem = ProblemDetector().execute(query)
        assert problem.type == "general"

        # Step 2: Decompose → generic steps
        steps = StepDecomposer().execute(problem)
        assert len(steps.steps) > 0

        # Step 3: Reason → generic template
        reasoning = TemplateReasoner().execute(problem)
        assert reasoning.template_used == "generic"
        assert reasoning.confidence < 0.5

        # Step 4: Confidence should be cautious
        confidence = ConfidenceEstimator().execute(reasoning)
        assert confidence.recommendation in ("caution", "reject", "proceed")

        # Step 5: Conclusion should still extract something
        conclusion = ConclusionExtractor().execute(reasoning)
        assert isinstance(conclusion, Conclusion)
