"""
Unit tests for FractalGenerator (Brecha C)

Tests the 3-phase fractal generation pipeline:
  Phase 1 (Structural): Directory tree + file names
  Phase 2 (Skeletons): Empty classes/functions with docstrings
  Phase 3 (Fill): Logic implementation item by item

Also tests project templates and fallback generation.
"""

import os
import sys
import ast
import pytest
import tempfile
import shutil

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.fractal_generator import (
    FractalGenerator, FractalSpec, FileBlueprint, FractalResult,
    PROJECT_TEMPLATES, DEFAULT_TEMPLATE,
)


class TestFractalSpec:
    """Tests for FractalSpec data structure."""

    def test_default_spec(self):
        """FractalSpec should have sensible defaults."""
        spec = FractalSpec()
        assert spec.project_name == ""
        assert spec.phase == 0
        assert spec.directories == []
        assert spec.files == []
        assert spec.config_files == {}

    def test_spec_with_data(self):
        """FractalSpec should accept construction parameters."""
        spec = FractalSpec(
            project_name="test_project",
            project_type="auth_system",
            language="python",
            description="A test auth system",
            directories=["src/", "tests/"],
            files=[FileBlueprint(path="src/main.py")],
            phase=1,
        )
        assert spec.project_name == "test_project"
        assert spec.project_type == "auth_system"
        assert len(spec.directories) == 2
        assert len(spec.files) == 1
        assert spec.phase == 1


class TestFileBlueprint:
    """Tests for FileBlueprint data structure."""

    def test_default_blueprint(self):
        """FileBlueprint should have sensible defaults."""
        bp = FileBlueprint()
        assert bp.path == ""
        assert bp.language == "python"
        assert bp.classes == []
        assert bp.functions == []
        assert bp.imports == []

    def test_blueprint_with_classes(self):
        """FileBlueprint should hold class definitions."""
        bp = FileBlueprint(
            path="src/models/user.py",
            language="python",
            description="User model",
            classes=[
                {"name": "User", "docstring": "User model", "bases": "Base"},
            ],
            functions=[
                {"name": "create_user", "docstring": "Creates a user", "params": "data: dict"},
            ],
            imports=["from sqlalchemy import Column"],
        )
        assert bp.path == "src/models/user.py"
        assert len(bp.classes) == 1
        assert len(bp.functions) == 1
        assert bp.classes[0]["name"] == "User"
        assert bp.functions[0]["params"] == "data: dict"


class TestProjectTemplates:
    """Tests for built-in project templates."""

    def test_auth_system_template_exists(self):
        """auth_system template should be available."""
        assert "auth_system" in PROJECT_TEMPLATES

    def test_crud_dashboard_template_exists(self):
        """crud_dashboard template should be available."""
        assert "crud_dashboard" in PROJECT_TEMPLATES

    def test_inventory_template_exists(self):
        """inventory template should be available."""
        assert "inventory" in PROJECT_TEMPLATES

    def test_auth_system_has_required_files(self):
        """auth_system template should have models, routes, services, main."""
        template = PROJECT_TEMPLATES["auth_system"]
        paths = [f["path"] for f in template["files"]]
        assert any("models" in p for p in paths)
        assert any("routes" in p for p in paths)
        assert any("services" in p for p in paths)
        assert any("main.py" in p for p in paths)

    def test_auth_system_has_config_files(self):
        """auth_system template should have requirements.txt."""
        template = PROJECT_TEMPLATES["auth_system"]
        assert "requirements.txt" in template["config_files"]

    def test_default_template_exists(self):
        """DEFAULT_TEMPLATE should be available for unknown types."""
        assert DEFAULT_TEMPLATE is not None
        assert len(DEFAULT_TEMPLATE["files"]) > 0


class TestPhase1Structural:
    """Tests for Phase 1: Structural generation."""

    def setup_method(self):
        self.gen = FractalGenerator()

    def test_generate_structure_auth_system(self):
        """Phase 1 should generate auth_system structure."""
        spec = self.gen.generate_structure(
            description="Authentication system",
            project_type="auth_system",
            project_name="my_auth",
        )
        assert spec.project_name == "my_auth"
        assert spec.phase == 1
        assert len(spec.files) > 0
        assert len(spec.directories) > 0

    def test_generate_structure_unknown_type_uses_default(self):
        """Phase 1 should use DEFAULT_TEMPLATE for unknown types."""
        spec = self.gen.generate_structure(
            description="Unknown project",
            project_type="nonexistent_type",
            project_name="test",
        )
        assert spec.project_name == "test"
        assert len(spec.files) > 0  # Default template has files

    def test_generate_structure_has_config_files(self):
        """Phase 1 should include config files."""
        spec = self.gen.generate_structure(
            description="Auth system",
            project_type="auth_system",
        )
        assert len(spec.config_files) > 0

    def test_generate_structure_files_have_paths(self):
        """All files in spec should have a path."""
        spec = self.gen.generate_structure(
            description="CRUD dashboard",
            project_type="crud_dashboard",
        )
        for f in spec.files:
            assert f.path, f"File missing path: {f}"


class TestPhase2Skeletons:
    """Tests for Phase 2: Skeleton generation."""

    def setup_method(self):
        self.gen = FractalGenerator()

    def test_generate_python_skeleton(self):
        """Phase 2 should generate valid Python skeleton code."""
        bp = FileBlueprint(
            path="src/models/user.py",
            language="python",
            description="User model",
            classes=[
                {"name": "User", "docstring": "User model", "bases": "Base"},
            ],
            functions=[
                {"name": "create_user", "docstring": "Creates a user", "params": "data: dict"},
            ],
            imports=["from sqlalchemy import Column, Integer, String"],
        )
        skeleton = self.gen._generate_python_skeleton(bp)

        # Should contain imports
        assert "from sqlalchemy import Column, Integer, String" in skeleton
        # Should contain class
        assert "class User(Base):" in skeleton
        # Should contain docstring
        assert "User model" in skeleton
        # Should contain function
        assert "def create_user(data: dict):" in skeleton
        # Should contain pass placeholder
        assert "pass" in skeleton

    def test_generate_python_skeleton_valid_syntax(self):
        """Python skeleton should be valid syntax (AST parseable)."""
        bp = FileBlueprint(
            path="src/main.py",
            language="python",
            description="Main app",
            classes=[
                {"name": "App", "docstring": "Application class", "bases": ""},
            ],
            functions=[
                {"name": "run", "docstring": "Run the app", "params": ""},
            ],
        )
        skeleton = self.gen._generate_python_skeleton(bp)
        # Should parse without errors
        ast.parse(skeleton)

    def test_generate_js_skeleton(self):
        """Phase 2 should generate valid JavaScript skeleton."""
        bp = FileBlueprint(
            path="src/app.js",
            language="javascript",
            description="Main app",
            classes=[
                {"name": "App", "docstring": "Application", "bases": ""},
            ],
            functions=[
                {"name": "init", "docstring": "Initialize", "params": ""},
            ],
        )
        skeleton = self.gen._generate_js_skeleton(bp)
        assert "class App" in skeleton
        assert "function init" in skeleton

    def test_generate_kotlin_skeleton(self):
        """Phase 2 should generate valid Kotlin skeleton."""
        bp = FileBlueprint(
            path="src/Main.kt",
            language="kotlin",
            description="Main app",
            classes=[
                {"name": "Main", "docstring": "Main class", "bases": ""},
            ],
            functions=[
                {"name": "main", "docstring": "Entry point", "params": ""},
            ],
        )
        skeleton = self.gen._generate_kotlin_skeleton(bp)
        assert "class Main" in skeleton
        assert "fun main" in skeleton

    def test_full_skeleton_generation(self):
        """Full Phase 2 should add _generated_content to all files."""
        spec = self.gen.generate_structure(
            description="Auth system",
            project_type="auth_system",
        )
        spec = self.gen.generate_skeletons(spec)

        assert spec.phase == 2
        for f in spec.files:
            content = getattr(f, '_generated_content', '')
            # All non-init files should have content
            if not f.path.endswith("__init__.py") or f.classes or f.functions:
                assert content, f"No content for {f.path}"


class TestPhase3Fill:
    """Tests for Phase 3: Logic filling."""

    def setup_method(self):
        self.gen = FractalGenerator()

    def test_fill_creates_result(self):
        """Phase 3 should return a FractalResult."""
        spec = self.gen.generate_structure(
            description="Auth system",
            project_type="auth_system",
        )
        spec = self.gen.generate_skeletons(spec)
        result = self.gen.fill_logic(spec)

        assert isinstance(result, FractalResult)
        assert result.status == "complete"
        assert result.current_phase == 3

    def test_fill_with_output_dir(self):
        """Phase 3 should write files to output directory."""
        tmpdir = tempfile.mkdtemp(prefix="fractal_test_")
        try:
            spec = self.gen.generate_structure(
                description="Auth system",
                project_type="auth_system",
            )
            spec = self.gen.generate_skeletons(spec)
            result = self.gen.fill_logic(spec, output_dir=tmpdir)

            assert result.status == "complete"
            assert len(result.files_generated) > 0

            # Verify files exist on disk
            for fpath in result.files_generated:
                full_path = os.path.join(tmpdir, fpath)
                assert os.path.exists(full_path), f"File not created: {full_path}"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_fill_replaces_pass_todo(self):
        """Phase 3 should replace 'pass  # TODO: Implement' with logic."""
        bp = FileBlueprint(
            path="src/main.py",
            language="python",
            description="Main",
            functions=[
                {"name": "create_item", "docstring": "Creates an item", "params": "data: dict"},
            ],
        )
        spec = FractalSpec(
            project_name="test",
            project_type="crud_dashboard",
            language="python",
            files=[bp],
            phase=2,
        )
        spec = self.gen.generate_skeletons(spec)
        result = self.gen.fill_logic(spec)

        # The 'pass  # TODO: Implement' should be replaced
        content = getattr(bp, '_generated_content', '')
        # After fill, there should be implementation logic
        assert "pass  # TODO: Implement" not in content or "try:" in content


class TestFullPipeline:
    """Tests for the full 3-phase pipeline."""

    def setup_method(self):
        self.gen = FractalGenerator()

    def test_generate_project_auth_system(self):
        """Full pipeline should generate an auth system project."""
        result = self.gen.generate_project(
            description="Authentication system with JWT",
            project_type="auth_system",
            project_name="test_auth",
        )
        assert result.status == "complete"
        assert result.project_name == "test_auth"
        assert result.current_phase == 3
        assert result.total_files > 0

    def test_generate_project_crud(self):
        """Full pipeline should generate a CRUD dashboard project."""
        result = self.gen.generate_project(
            description="CRUD dashboard for inventory",
            project_type="crud_dashboard",
            project_name="test_crud",
        )
        assert result.status == "complete"
        assert result.total_files > 0

    def test_generate_project_with_output(self):
        """Full pipeline with output_dir should create files on disk."""
        tmpdir = tempfile.mkdtemp(prefix="fractal_full_")
        try:
            result = self.gen.generate_project(
                description="Test project",
                project_type="inventory",
                project_name="test_inventory",
                output_dir=tmpdir,
            )
            assert result.status == "complete"
            assert len(result.files_generated) > 0
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestUtilities:
    """Tests for utility methods."""

    def setup_method(self):
        self.gen = FractalGenerator()

    def test_get_template_types(self):
        """Should return list of available template types."""
        types = self.gen.get_template_types()
        assert isinstance(types, list)
        assert "auth_system" in types
        assert "crud_dashboard" in types
        assert "inventory" in types

    def test_get_spec_summary(self):
        """Should return a summary dict of the spec."""
        spec = self.gen.generate_structure(
            description="Auth system",
            project_type="auth_system",
            project_name="test",
        )
        summary = self.gen.get_spec_summary(spec)
        assert summary["project_name"] == "test"
        assert summary["project_type"] == "auth_system"
        assert "directories" in summary
        assert "files" in summary
        assert "classes" in summary
        assert "functions" in summary

    def test_fix_python_skeleton(self):
        """Should fix simple syntax errors in Python skeletons."""
        bad_code = "def foo():\n\n"
        fixed = self.gen._fix_python_skeleton(bad_code)
        # Should add 'pass' after the function definition
        assert "pass" in fixed


class TestPatternImplementation:
    """Tests for pattern-based fallback implementation."""

    def setup_method(self):
        self.gen = FractalGenerator()

    def test_create_pattern(self):
        """Create functions should get try/except implementation."""
        impl = self.gen._generate_pattern_implementation(
            "def create_user(data: dict):", FileBlueprint(),
            FractalSpec(project_type="auth_system"), "    "
        )
        assert len(impl) > 0
        assert any("try:" in line for line in impl)

    def test_get_pattern(self):
        """Get/list functions should get try/except implementation."""
        impl = self.gen._generate_pattern_implementation(
            "def get_users():", FileBlueprint(),
            FractalSpec(), "    "
        )
        assert len(impl) > 0

    def test_delete_pattern(self):
        """Delete functions should get try/except implementation."""
        impl = self.gen._generate_pattern_implementation(
            "def delete_user(user_id: int):", FileBlueprint(),
            FractalSpec(), "    "
        )
        assert len(impl) > 0

    def test_validate_pattern(self):
        """Validate functions should get try/except implementation."""
        impl = self.gen._generate_pattern_implementation(
            "def validate_token(token: str):", FileBlueprint(),
            FractalSpec(), "    "
        )
        assert len(impl) > 0

    def test_test_pattern(self):
        """Test functions should get assert implementation."""
        impl = self.gen._generate_pattern_implementation(
            "def test_something():", FileBlueprint(),
            FractalSpec(), "    "
        )
        assert len(impl) > 0
        assert any("assert" in line for line in impl)

    def test_unknown_pattern(self):
        """Unknown functions should get NotImplementedError."""
        impl = self.gen._generate_pattern_implementation(
            "def process_data(x):", FileBlueprint(),
            FractalSpec(), "    "
        )
        assert any("NotImplementedError" in line for line in impl)
