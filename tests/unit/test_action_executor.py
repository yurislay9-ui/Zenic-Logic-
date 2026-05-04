"""
TITAN OMNISCALE X - ActionExecutor Unit Tests

Tests for src/core/action_executor.py:
  - ActionResult data class
  - Utility validators (_validate_email, _validate_url, _safe_path, _validate_sql)
  - EmailExecutor (dry-run mode, validation)
  - HttpExecutor (validation, invalid inputs)
  - DatabaseExecutor (query, script operations)
  - FileExecutor (write/read/mkdir operations)
  - TransformExecutor (map_fields, filter, sort, aggregate)
  - WebhookExecutor (verify signature)
  - NotificationExecutor (log channel, fallbacks)
"""

import asyncio
import hashlib
import hmac
import os
import tempfile

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.core.action_executor import (
    ActionResult,
    ActionExecutor,
    EmailExecutor,
    HttpExecutor,
    DatabaseExecutor,
    FileExecutor,
    TransformExecutor,
    WebhookExecutor,
    NotificationExecutor,
    _validate_email,
    _validate_url,
    _safe_path,
    _validate_sql,
)


# ============================================================
#  HELPER: Run async functions in tests
# ============================================================

def run_async(coro):
    """Helper to run an async coroutine in sync test context."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ============================================================
#  ACTIONRESULT TESTS
# ============================================================

class TestActionResult:
    """Tests for the ActionResult dataclass."""

    def test_success_result(self):
        """ActionResult should store success state and data."""
        result = ActionResult(True, {"key": "value"})
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error == ""
        assert result.duration_ms == 0.0

    def test_failure_result_with_error(self):
        """ActionResult should store failure state and error message."""
        result = ActionResult(False, {}, "Something went wrong", 12.5)
        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.duration_ms == 12.5


# ============================================================
#  VALIDATOR UTILITY TESTS
# ============================================================

class TestValidateEmail:
    """Tests for _validate_email utility."""

    def test_valid_email(self):
        assert _validate_email("user@example.com") is True

    def test_valid_email_with_dots(self):
        assert _validate_email("first.last@sub.domain.com") is True

    def test_invalid_email_no_at(self):
        assert _validate_email("userexample.com") is False

    def test_invalid_email_no_domain(self):
        assert _validate_email("user@") is False

    def test_invalid_email_empty(self):
        assert _validate_email("") is False


class TestValidateUrl:
    """Tests for _validate_url utility."""

    def test_valid_http_url(self):
        assert _validate_url("http://example.com") is True

    def test_valid_https_url(self):
        assert _validate_url("https://example.com/path") is True

    def test_invalid_url_no_scheme(self):
        assert _validate_url("example.com") is False

    def test_invalid_url_ftp(self):
        assert _validate_url("ftp://files.example.com") is False

    def test_invalid_url_empty(self):
        assert _validate_url("") is False


class TestSafePath:
    """Tests for _safe_path utility."""

    def test_safe_relative_path(self):
        """Relative path within base_dir should be allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _safe_path("file.txt", tmpdir)
            assert result.startswith(tmpdir)

    def test_path_traversal_blocked(self):
        """Path traversal with ../ should be blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="Path traversal"):
                _safe_path("../../../etc/passwd", tmpdir)

    def test_absolute_path_in_tmp(self):
        """Absolute path in /tmp should be allowed."""
        result = _safe_path("/tmp/test_file.txt", "/some/base")
        assert result.startswith("/tmp")


class TestValidateSql:
    """Tests for _validate_sql utility."""

    def test_safe_select_query(self):
        assert _validate_sql("SELECT * FROM users WHERE id = ?") is True

    def test_drop_table_detected(self):
        assert _validate_sql("SELECT 1; DROP TABLE users") is False

    def test_delete_from_detected(self):
        assert _validate_sql("SELECT 1; DELETE FROM users") is False

    def test_union_select_detected(self):
        assert _validate_sql("SELECT 1 UNION SELECT * FROM secrets") is False

    def test_normal_insert_passes(self):
        """Normal INSERT without dangerous patterns should pass."""
        assert _validate_sql("INSERT INTO users (name) VALUES (?)") is True


# ============================================================
#  EMAIL EXECUTOR TESTS
# ============================================================

class TestEmailExecutor:
    """Tests for EmailExecutor (dry-run mode)."""

    def setup_method(self):
        self.executor = EmailExecutor()

    def test_dry_run_without_smtp(self):
        """EmailExecutor should run in dry-run mode without SMTP config."""
        config = {
            "to": ["test@example.com"],
            "subject": "Test",
            "body": "Hello",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data.get("mode") == "dry_run"

    def test_invalid_email_rejected(self):
        """Invalid recipient email should be rejected."""
        config = {
            "to": ["not-an-email"],
            "subject": "Test",
            "body": "Hello",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Invalid email" in result.error

    def test_no_recipients_rejected(self):
        """Missing recipients should be rejected."""
        config = {
            "to": [],
            "subject": "Test",
            "body": "Hello",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "No recipient" in result.error

    def test_string_to_normalized(self):
        """String 'to' should be normalized to list."""
        config = {
            "to": "single@example.com",
            "subject": "Test",
            "body": "Hello",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True


# ============================================================
#  HTTP EXECUTOR TESTS
# ============================================================

class TestHttpExecutor:
    """Tests for HttpExecutor (validation only, no real HTTP calls)."""

    def setup_method(self):
        self.executor = HttpExecutor()

    def test_no_url_rejected(self):
        """Missing URL should be rejected."""
        config = {"url": ""}
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "No URL" in result.error

    def test_invalid_url_rejected(self):
        """Invalid URL should be rejected."""
        config = {"url": "not-a-url"}
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Invalid URL" in result.error

    def test_invalid_method_rejected(self):
        """Invalid HTTP method should be rejected."""
        config = {"url": "https://example.com", "method": "PATCHX"}
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Invalid HTTP method" in result.error


# ============================================================
#  DATABASE EXECUTOR TESTS
# ============================================================

class TestDatabaseExecutor:
    """Tests for DatabaseExecutor (using :memory: DB)."""

    def setup_method(self):
        self.executor = DatabaseExecutor()

    def test_query_operation(self):
        """Query operation on in-memory DB should work."""
        config = {
            "db_path": ":memory:",
            "operation": "script",
            "script": "CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT); INSERT INTO test VALUES (1, 'hello');",
        }
        # First create the table
        run_async(self.executor.execute(config, {}))

        # Then query
        query_config = {
            "db_path": ":memory:",
            "operation": "query",
            "query": "SELECT 1 as val",
        }
        result = run_async(self.executor.execute(query_config, {}))
        assert result.success is True

    def test_invalid_operation_rejected(self):
        """Invalid DB operation should be rejected."""
        config = {
            "db_path": ":memory:",
            "operation": "invalid_op",
            "query": "SELECT 1",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Invalid DB operation" in result.error

    def test_empty_query_rejected(self):
        """Empty query should be rejected."""
        config = {
            "db_path": ":memory:",
            "operation": "query",
            "query": "",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "No SQL query" in result.error

    def test_backup_in_memory_rejected(self):
        """Backup of in-memory DB should be rejected."""
        config = {
            "db_path": ":memory:",
            "operation": "backup",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Cannot backup in-memory" in result.error

    def test_script_execution(self):
        """Script execution should work on in-memory DB."""
        config = {
            "db_path": ":memory:",
            "operation": "script",
            "script": "CREATE TABLE t(x INT); INSERT INTO t VALUES(42);",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["script_lines"] >= 2

    def test_empty_script_rejected(self):
        """Empty script should be rejected."""
        config = {
            "db_path": ":memory:",
            "operation": "script",
            "script": "",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "No SQL script" in result.error


# ============================================================
#  FILE EXECUTOR TESTS
# ============================================================

class TestFileExecutor:
    """Tests for FileExecutor (using temp directories)."""

    def setup_method(self):
        self.executor = FileExecutor()
        self.tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_write_and_read(self):
        """Write then read should return the same content."""
        write_config = {
            "operation": "write",
            "source": os.path.join(self.tmpdir, "test.txt"),
            "content": "Hello World",
            "base_dir": self.tmpdir,
        }
        write_result = run_async(self.executor.execute(write_config, {}))
        assert write_result.success is True

        read_config = {
            "operation": "read",
            "source": "test.txt",
            "base_dir": self.tmpdir,
        }
        read_result = run_async(self.executor.execute(read_config, {}))
        assert read_result.success is True
        assert read_result.data["content"] == "Hello World"

    def test_mkdir_operation(self):
        """mkdir should create a directory."""
        config = {
            "operation": "mkdir",
            "source": "new_dir",
            "base_dir": self.tmpdir,
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert os.path.isdir(os.path.join(self.tmpdir, "new_dir"))

    def test_exists_operation(self):
        """exists should report file existence."""
        config = {
            "operation": "exists",
            "source": "nonexistent.txt",
            "base_dir": self.tmpdir,
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["exists"] is False

    def test_invalid_operation_rejected(self):
        """Invalid file operation should be rejected."""
        config = {
            "operation": "chmod",
            "source": "file.txt",
            "base_dir": self.tmpdir,
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Invalid file operation" in result.error

    def test_path_traversal_blocked(self):
        """Path traversal in file operations should be blocked."""
        config = {
            "operation": "read",
            "source": "../../../etc/passwd",
            "base_dir": self.tmpdir,
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False


# ============================================================
#  TRANSFORM EXECUTOR TESTS
# ============================================================

class TestTransformExecutor:
    """Tests for TransformExecutor (pure data operations)."""

    def setup_method(self):
        self.executor = TransformExecutor()

    def test_map_fields_dict(self):
        """map_fields should rename dict keys according to mapping."""
        config = {
            "operation": "map_fields",
            "data": {"old_key": "value"},
            "mapping": {"old_key": "new_key"},
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["result"]["new_key"] == "value"

    def test_filter_data(self):
        """filter should filter list items by key/value."""
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        config = {
            "operation": "filter",
            "data": data,
            "key": "age",
            "operator": "gt",
            "value": 26,
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert len(result.data["result"]) == 1
        assert result.data["result"][0]["name"] == "Alice"

    def test_sort_data(self):
        """sort should sort list items by key."""
        data = [
            {"name": "Charlie", "age": 35},
            {"name": "Alice", "age": 25},
            {"name": "Bob", "age": 30},
        ]
        config = {
            "operation": "sort",
            "data": data,
            "key": "age",
            "ascending": True,
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["result"][0]["name"] == "Alice"

    def test_aggregate_count(self):
        """aggregate count should return list length."""
        config = {
            "operation": "aggregate",
            "data": [{"x": 1}, {"x": 2}, {"x": 3}],
            "aggregation": "count",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["result"]["count"] == 3

    def test_no_data_rejected(self):
        """Missing data should be rejected."""
        config = {"operation": "map_fields", "mapping": {}}
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "No input data" in result.error

    def test_invalid_operation_rejected(self):
        """Invalid transform operation should be rejected."""
        config = {"operation": "explode", "data": [1, 2, 3]}
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Invalid transform operation" in result.error


# ============================================================
#  WEBHOOK EXECUTOR TESTS
# ============================================================

class TestWebhookExecutor:
    """Tests for WebhookExecutor (verify signature only)."""

    def setup_method(self):
        self.executor = WebhookExecutor()

    def test_verify_valid_signature(self):
        """verify should accept a valid HMAC-SHA256 signature."""
        secret = "my_secret"
        body = '{"event": "test"}'
        expected_sig = hmac.new(
            secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()

        config = {
            "action": "verify",
            "secret": secret,
            "verify_signature": expected_sig,
            "verify_body": body,
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["valid"] is True

    def test_verify_invalid_signature(self):
        """verify should reject an invalid HMAC-SHA256 signature."""
        config = {
            "action": "verify",
            "secret": "my_secret",
            "verify_signature": "invalid_hex_signature",
            "verify_body": '{"event": "test"}',
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["valid"] is False

    def test_verify_sha256_prefix(self):
        """verify should handle sha256= prefix in signature."""
        secret = "secret"
        body = "payload"
        sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        config = {
            "action": "verify",
            "secret": secret,
            "verify_signature": f"sha256={sig}",
            "verify_body": body,
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.data["valid"] is True

    def test_verify_missing_secret(self):
        """verify without secret should return error."""
        config = {
            "action": "verify",
            "verify_signature": "abc",
            "verify_body": "data",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Secret is required" in result.error

    def test_send_missing_url(self):
        """send without URL should return error."""
        config = {
            "action": "send",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False

    def test_invalid_action_rejected(self):
        """Invalid webhook action should be rejected."""
        config = {"action": "delete"}
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Invalid webhook action" in result.error


# ============================================================
#  NOTIFICATION EXECUTOR TESTS
# ============================================================

class TestNotificationExecutor:
    """Tests for NotificationExecutor."""

    def setup_method(self):
        self.executor = NotificationExecutor(
            email_executor=None,
            webhook_executor=None,
        )

    def test_log_channel(self):
        """log channel should succeed and deliver."""
        config = {
            "channel": "log",
            "message": "Test notification",
            "subject": "Test",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["channel"] == "log"
        assert result.data["delivered"] is True

    def test_email_channel_fallback(self):
        """email channel should fallback to log without EmailExecutor."""
        config = {
            "channel": "email",
            "recipient": "test@example.com",
            "message": "Hello",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["fallback"] is True

    def test_telegram_channel_fallback(self):
        """telegram channel should fallback to log without bot token."""
        config = {
            "channel": "telegram",
            "recipient": "12345",
            "message": "Hello",
        }
        # Ensure no TELEGRAM_BOT_TOKEN is set
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data.get("fallback") is True

    def test_webhook_channel_no_url_fallback(self):
        """webhook channel should fallback to log without URL."""
        config = {
            "channel": "webhook",
            "recipient": "",
            "message": "Hello",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data.get("fallback") is True

    def test_unknown_channel_falls_back(self):
        """Unknown channel should fallback to log."""
        config = {
            "channel": "slack",
            "message": "Hello",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["fallback"] is True
        assert result.data["original_channel"] == "slack"
