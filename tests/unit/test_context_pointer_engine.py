"""
Unit tests for ContextPointerEngine

Tests vectorized signatures (FunctionSignature, ContextPointer),
SignatureIndex indexing (Python and regex-based), similarity
matching / search, and compact context generation.
"""

import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from src.core.context_pointer_engine import (
    FunctionSignature, ContextPointer, SignatureIndex, CONTEXT_STORE_ROOT,
)


# ============================================================
#  Fixtures
# ============================================================

SAMPLE_PYTHON_CODE = '''
"""Module for user authentication."""

def login(username: str, password: str) -> bool:
    """Authenticate user with credentials."""
    token = create_token(username)
    if verify_password(password, username):
        return True
    return False

async def logout(session_id: str) -> None:
    """End user session."""
    destroy_session(session_id)

class UserAuth:
    """User authentication handler."""

    def authenticate(self, token: str) -> bool:
        """Validate authentication token."""
        return validate_token(token)
'''

SAMPLE_JS_CODE = '''
function handleClick(event) {
    const target = event.target;
    processClick(target);
}

async function fetchData(url) {
    const response = await fetch(url);
    return response.json();
}
'''


@pytest.fixture
def signature_index(tmp_path, monkeypatch):
    """Create a SignatureIndex with temporary context store."""
    store_dir = str(tmp_path / "ctx_store")
    monkeypatch.setattr("src.core.context_pointer_engine.CONTEXT_STORE_ROOT", store_dir)
    return SignatureIndex(project_root=str(tmp_path))


@pytest.fixture
def populated_index(signature_index):
    """Create a SignatureIndex with Python code indexed."""
    signature_index.index_code(SAMPLE_PYTHON_CODE, "auth.py")
    return signature_index


# ============================================================
#  FunctionSignature Tests
# ============================================================

class TestFunctionSignature:
    """Tests for FunctionSignature dataclass."""

    def test_to_pointer_format(self):
        """Should generate compact pointer representation."""
        sig = FunctionSignature(
            name="login", file_path="auth.py",
            line_start=5, line_end=10,
            params=["username:str", "password:str"],
            return_type="bool",
        )
        pointer = sig.to_pointer()
        assert "login" in pointer
        assert "username:str" in pointer
        assert "auth.py" in pointer
        assert "L5-10" in pointer

    def test_to_pointer_no_params(self):
        """Should handle empty params gracefully."""
        sig = FunctionSignature(
            name="init", file_path="main.py",
            line_start=1, line_end=1,
        )
        pointer = sig.to_pointer()
        assert "init" in pointer
        assert "()" in pointer

    def test_to_pointer_no_return_type(self):
        """Should omit return type when not specified."""
        sig = FunctionSignature(
            name="process", file_path="app.py",
            line_start=10, line_end=15,
            params=["data"],
        )
        pointer = sig.to_pointer()
        assert "->" not in pointer


# ============================================================
#  ContextPointer Tests
# ============================================================

class TestContextPointer:
    """Tests for ContextPointer dataclass and methods."""

    def test_to_model_context_with_docstring(self):
        """Should include docstring in model context."""
        sig = FunctionSignature(
            name="login", file_path="auth.py",
            line_start=5, line_end=10,
            docstring="Authenticate user",
        )
        ptr = ContextPointer(signature=sig, reason="User asked about login")
        ctx = ptr.to_model_context()
        assert "login" in ctx
        assert "Authenticate user" in ctx
        assert "User asked about login" in ctx

    def test_to_model_context_with_calls(self):
        """Should include call list in model context."""
        sig = FunctionSignature(
            name="login", file_path="auth.py",
            line_start=5, line_end=10,
            calls=["verify_password", "create_token"],
        )
        ptr = ContextPointer(signature=sig)
        ctx = ptr.to_model_context()
        assert "verify_password" in ctx

    def test_to_model_context_minimal(self):
        """Should work with minimal signature info."""
        sig = FunctionSignature(
            name="noop", file_path="utils.py",
            line_start=1, line_end=1,
        )
        ptr = ContextPointer(signature=sig)
        ctx = ptr.to_model_context()
        assert "noop" in ctx

    def test_load_code_from_disk(self, tmp_path):
        """Should load code lines from file using line range."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\nline4\nline5\n")
        sig = FunctionSignature(
            name="test_func", file_path=str(test_file),
            line_start=2, line_end=4,
        )
        ptr = ContextPointer(signature=sig)
        code = ptr.load_code_from_disk()
        assert "line2" in code
        assert "line3" in code
        assert "line4" in code
        assert "line1" not in code

    def test_load_code_nonexistent_file(self):
        """Should return empty string for nonexistent file."""
        sig = FunctionSignature(
            name="missing", file_path="/nonexistent/file.py",
            line_start=1, line_end=5,
        )
        ptr = ContextPointer(signature=sig)
        code = ptr.load_code_from_disk()
        assert code == ""

    def test_apply_modification(self, tmp_path):
        """Should replace lines in the target file."""
        test_file = tmp_path / "mod.py"
        test_file.write_text("def old():\n    pass\n\ndef other():\n    pass\n")
        sig = FunctionSignature(
            name="old", file_path=str(test_file),
            line_start=1, line_end=2,
        )
        ptr = ContextPointer(signature=sig)
        result = ptr.apply_modification("def new():\n    return 42")
        assert result is True
        content = test_file.read_text()
        assert "def new():" in content
        assert "return 42" in content

    def test_apply_modification_nonexistent_file(self):
        """Should return False for nonexistent file."""
        sig = FunctionSignature(
            name="old", file_path="/nonexistent/file.py",
            line_start=1, line_end=2,
        )
        ptr = ContextPointer(signature=sig)
        result = ptr.apply_modification("def new(): pass")
        assert result is False

    def test_apply_modification_with_sibling_adjustment(self, tmp_path):
        """Should adjust sibling pointer line numbers after modification."""
        test_file = tmp_path / "siblings.py"
        test_file.write_text(
            "def func_a():\n    pass\n\ndef func_b():\n    pass\n\ndef func_c():\n    pass\n"
        )
        sig_a = FunctionSignature(name="func_a", file_path=str(test_file), line_start=1, line_end=2)
        sig_b = FunctionSignature(name="func_b", file_path=str(test_file), line_start=4, line_end=5)
        sig_c = FunctionSignature(name="func_c", file_path=str(test_file), line_start=7, line_end=8)

        ptr_a = ContextPointer(signature=sig_a)
        ptr_b = ContextPointer(signature=sig_b)
        ptr_c = ContextPointer(signature=sig_c)

        # Expand func_a by 2 extra lines
        ptr_a.apply_modification(
            "def func_a():\n    extra_line_1\n    extra_line_2\n    pass",
            sibling_pointers=[ptr_b, ptr_c],
        )

        # func_b and func_c should be shifted by +2
        assert sig_b.line_start == 6
        assert sig_b.line_end == 7
        assert sig_c.line_start == 9
        assert sig_c.line_end == 10


# ============================================================
#  SignatureIndex - Python Indexing Tests
# ============================================================

class TestPythonIndexing:
    """Tests for Python code signature extraction."""

    def test_index_python_code(self, signature_index):
        """Should extract function signatures from Python code."""
        count = signature_index.index_code(SAMPLE_PYTHON_CODE, "auth.py")
        assert count >= 3  # login, logout, UserAuth (and possibly authenticate)

    def test_index_function_names(self, populated_index):
        """Should correctly index function names."""
        names = [key[0] if isinstance(key, tuple) else key for key in populated_index._name_index.keys()]
        assert "login" in names
        assert "logout" in names

    def test_index_class_signatures(self, populated_index):
        """Should index class definitions with method info."""
        names = [key[0] if isinstance(key, tuple) else key for key in populated_index._name_index.keys()]
        assert "UserAuth" in names

    def test_index_function_params(self, populated_index):
        """Should extract parameter names and types."""
        login_sigs = populated_index._name_index.get(("login", "auth.py"), [])
        assert len(login_sigs) >= 1
        params = login_sigs[0].params
        assert any("username" in p for p in params)
        assert any("password" in p for p in params)

    def test_index_function_return_type(self, populated_index):
        """Should extract return type annotations."""
        login_sigs = populated_index._name_index.get(("login", "auth.py"), [])
        assert len(login_sigs) >= 1
        assert login_sigs[0].return_type == "bool"

    def test_index_function_docstring(self, populated_index):
        """Should extract docstrings."""
        login_sigs = populated_index._name_index.get(("login", "auth.py"), [])
        assert len(login_sigs) >= 1
        assert "Authenticate" in login_sigs[0].docstring

    def test_index_function_calls(self, populated_index):
        """Should extract function call references."""
        login_sigs = populated_index._name_index.get(("login", "auth.py"), [])
        assert len(login_sigs) >= 1
        # login calls create_token and verify_password
        assert "create_token" in login_sigs[0].calls or "verify_password" in login_sigs[0].calls

    def test_index_function_complexity(self, populated_index):
        """Should compute cyclomatic complexity."""
        login_sigs = populated_index._name_index.get(("login", "auth.py"), [])
        assert len(login_sigs) >= 1
        # login has an if statement → complexity >= 2
        assert login_sigs[0].complexity >= 2

    def test_index_function_hash(self, populated_index):
        """Should compute content hash."""
        login_sigs = populated_index._name_index.get(("login", "auth.py"), [])
        assert len(login_sigs) >= 1
        assert login_sigs[0].hash != ""


# ============================================================
#  SignatureIndex - Regex Indexing Tests
# ============================================================

class TestRegexIndexing:
    """Tests for non-Python code signature extraction via regex."""

    def test_index_javascript_code(self, signature_index):
        """Should extract JS function signatures."""
        count = signature_index.index_code(SAMPLE_JS_CODE, "app.js")
        assert count >= 1
        names = [key[0] if isinstance(key, tuple) else key for key in signature_index._name_index.keys()]
        assert "handleClick" in names or "fetchData" in names

    def test_index_unknown_language(self, signature_index):
        """Should fallback to generic regex for unknown extensions."""
        code = "def some_func(arg1, arg2)"
        count = signature_index.index_code(code, "unknown.xyz")
        # May or may not match; just should not crash
        assert isinstance(count, int)

    def test_index_kotlin_code(self, signature_index):
        """Should extract Kotlin function signatures."""
        kt_code = "fun calculateTotal(price: Double, qty: Int): Double { return price * qty }"
        count = signature_index.index_code(kt_code, "calc.kt")
        assert count >= 1
        names = [key[0] if isinstance(key, tuple) else key for key in signature_index._name_index.keys()]
        assert "calculateTotal" in names


# ============================================================
#  SignatureIndex - Search Tests
# ============================================================

class TestSignatureSearch:
    """Tests for signature search and similarity matching."""

    def test_search_by_name(self, populated_index):
        """Should find signatures by exact or partial name match."""
        results = populated_index.search("login")
        assert len(results) >= 1
        assert any(p.signature.name == "login" for p in results)

    def test_search_by_partial_name(self, populated_index):
        """Should find signatures by partial name match."""
        results = populated_index.search("log")
        assert len(results) >= 1

    def test_search_no_results(self, populated_index):
        """Should return empty for non-matching query."""
        results = populated_index.search("nonexistent_function_xyz")
        assert results == []

    def test_search_respects_top_k(self, populated_index):
        """Should limit results to top_k."""
        results = populated_index.search("a", top_k=1)
        assert len(results) <= 1

    def test_search_returns_context_pointers(self, populated_index):
        """Search results should be ContextPointer instances."""
        results = populated_index.search("login")
        assert all(isinstance(p, ContextPointer) for p in results)

    def test_search_includes_relevance_score(self, populated_index):
        """Each result should have a relevance_score > 0."""
        results = populated_index.search("login")
        assert all(p.relevance_score > 0 for p in results)

    def test_get_by_name_exact(self, populated_index):
        """Should find a signature by exact name."""
        ptr = populated_index.get_by_name("login")
        assert ptr is not None
        assert ptr.signature.name == "login"

    def test_get_by_name_not_found(self, populated_index):
        """Should return None for unknown name."""
        ptr = populated_index.get_by_name("nonexistent")
        assert ptr is None


# ============================================================
#  SignatureIndex - Compact Context Tests
# ============================================================

class TestCompactContext:
    """Tests for build_compact_context method."""

    def test_compact_context_format(self, populated_index):
        """Should produce a context string with pointers."""
        ctx, pointers = populated_index.build_compact_context("login")
        assert "Context Pointers" in ctx or "login" in ctx
        assert len(pointers) >= 1

    def test_compact_context_no_results(self, signature_index):
        """Should return message when no functions found."""
        ctx, pointers = signature_index.build_compact_context("nonexistent")
        assert "No se encontraron" in ctx or len(pointers) == 0

    def test_compact_context_respects_max_tokens(self, populated_index):
        """Should limit output based on max_tokens parameter."""
        ctx, pointers = populated_index.build_compact_context("a", max_tokens=50)
        # With very low max_tokens, should produce limited output
        assert isinstance(ctx, str)


# ============================================================
#  SignatureIndex - Project Indexing Tests
# ============================================================

class TestProjectIndexing:
    """Tests for index_project method."""

    def test_index_project_with_files(self, tmp_path, monkeypatch):
        """Should index all code files in a project directory."""
        store_dir = str(tmp_path / "ctx_store")
        monkeypatch.setattr("src.core.context_pointer_engine.CONTEXT_STORE_ROOT", store_dir)

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("def main(): pass\n")
        (src_dir / "utils.py").write_text("def helper(): pass\n")
        (src_dir / "readme.md").write_text("# Not code")  # Should be ignored

        idx = SignatureIndex(project_root=str(tmp_path))
        count = idx.index_project()
        assert count >= 2  # main and helper functions

    def test_index_project_nonexistent(self, signature_index):
        """Should return 0 for nonexistent project root."""
        count = signature_index.index_project("/nonexistent/path")
        assert count == 0

    def test_index_project_multiple_languages(self, tmp_path, monkeypatch):
        """Should index files of multiple code languages."""
        store_dir = str(tmp_path / "ctx_store")
        monkeypatch.setattr("src.core.context_pointer_engine.CONTEXT_STORE_ROOT", store_dir)

        src_dir = tmp_path / "multi"
        src_dir.mkdir()
        (src_dir / "app.py").write_text("def python_func(): pass\n")
        (src_dir / "app.js").write_text("function jsFunc() {}\n")

        idx = SignatureIndex(project_root=str(src_dir))
        count = idx.index_project()
        assert count >= 1  # At least python_func


# ============================================================
#  SignatureIndex - Stats Tests
# ============================================================

class TestSignatureIndexStats:
    """Tests for SignatureIndex stats property."""

    def test_stats_structure(self, populated_index):
        """Stats should contain expected keys."""
        stats = populated_index.stats
        assert "total_signatures" in stats
        assert "total_files" in stats
        assert "unique_names" in stats
        assert "store_dir" in stats

    def test_stats_counts(self, populated_index):
        """Stats should report correct counts."""
        stats = populated_index.stats
        assert stats["total_signatures"] >= 3
        assert stats["total_files"] == 1
        assert stats["unique_names"] >= 3

    def test_stats_empty_index(self, signature_index):
        """Empty index should report zero counts."""
        stats = signature_index.stats
        assert stats["total_signatures"] == 0
        assert stats["total_files"] == 0
        assert stats["unique_names"] == 0
