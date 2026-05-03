"""
Unit tests for AuthService

Tests JWT/HMAC authentication, user management, RBAC, API key auth
using isolated SQLite databases per test.
"""

import os
import sys
import time
import pytest

# Ensure project root is importable
sys.path.insert(0, "/home/z/my-project/Zenic-Logic-")

from src.core.auth_service import AuthService, ROLE_HIERARCHY, ROLE_PERMISSIONS


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def auth(tmp_path):
    """Create an AuthService with a temp SQLite database."""
    db_path = str(tmp_path / "test_auth.sqlite")
    return AuthService(db_path=db_path, secret_key="test-secret-key-for-unit-tests")


@pytest.fixture
def registered_user(auth):
    """Register a standard user and return the result dict."""
    return auth.register_user("testuser", "test@example.com", "StrongPass1", "user")


@pytest.fixture
def admin_user(auth):
    """Register an admin user and return the result dict."""
    return auth.register_user("adminuser", "admin@example.com", "AdminPass1", "admin")


# ============================================================
#  Password Management Tests
# ============================================================

class TestPasswordManagement:
    """Tests for password hashing and verification."""

    def test_hash_password_returns_string(self):
        """hash_password should return a non-empty string."""
        hashed = AuthService.hash_password("TestPass123")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_password_different_hashes(self):
        """hash_password should produce different hashes for same password (salt)."""
        h1 = AuthService.hash_password("TestPass123")
        h2 = AuthService.hash_password("TestPass123")
        assert h1 != h2  # Different salts should produce different hashes

    def test_verify_password_correct(self):
        """verify_password should return True for correct password."""
        hashed = AuthService.hash_password("MyPassword1")
        assert AuthService.verify_password("MyPassword1", hashed) is True

    def test_verify_password_incorrect(self):
        """verify_password should return False for wrong password."""
        hashed = AuthService.hash_password("MyPassword1")
        assert AuthService.verify_password("WrongPassword1", hashed) is False

    def test_verify_password_empty_password(self):
        """verify_password should return False for empty password."""
        hashed = AuthService.hash_password("MyPassword1")
        assert AuthService.verify_password("", hashed) is False

    def test_verify_password_empty_hash(self):
        """verify_password should return False for empty hash."""
        assert AuthService.verify_password("password", "") is False

    def test_verify_password_none_inputs(self):
        """verify_password should return False for None inputs."""
        assert AuthService.verify_password(None, "hash") is False
        assert AuthService.verify_password("password", None) is False

    def test_verify_password_pbkdf2_format(self):
        """verify_password should handle pbkdf2$ format correctly."""
        hashed = AuthService.hash_password("TestPass123")
        # The hash should either start with pbkdf2$ (fallback) or be bcrypt
        if hashed.startswith("pbkdf2$"):
            assert AuthService.verify_password("TestPass123", hashed) is True

    def test_verify_password_invalid_hash_format(self):
        """verify_password should return False for invalid hash format."""
        assert AuthService.verify_password("password", "invalid$hash$format") is False


# ============================================================
#  User Registration Tests
# ============================================================

class TestUserRegistration:
    """Tests for user registration with validation."""

    def test_register_user_success(self, auth):
        """Should register a new user successfully."""
        result = auth.register_user("newuser", "new@example.com", "StrongPass1")
        assert "error" not in result
        assert result["username"] == "newuser"
        assert result["email"] == "new@example.com"
        assert result["role"] == "user"
        assert "user_id" in result

    def test_register_user_with_custom_role(self, auth):
        """Should register a user with a specific role."""
        result = auth.register_user("manager1", "mgr@example.com", "MgrPass123", "manager")
        assert "error" not in result
        assert result["role"] == "manager"

    def test_register_user_duplicate_username(self, auth, registered_user):
        """Should fail when registering with an existing username."""
        result = auth.register_user("testuser", "other@example.com", "OtherPass1")
        assert "error" in result
        assert "already exists" in result["error"].lower()

    def test_register_user_duplicate_email(self, auth, registered_user):
        """Should fail when registering with an existing email."""
        result = auth.register_user("otheruser", "test@example.com", "OtherPass1")
        assert "error" in result
        assert "already" in result["error"].lower()

    def test_register_user_short_username(self, auth):
        """Should reject usernames shorter than 3 characters."""
        result = auth.register_user("ab", "ab@example.com", "StrongPass1")
        assert "error" in result
        assert "3 characters" in result["error"]

    def test_register_user_long_username(self, auth):
        """Should reject usernames longer than 50 characters."""
        long_name = "a" * 51
        result = auth.register_user(long_name, "long@example.com", "StrongPass1")
        assert "error" in result
        assert "50 characters" in result["error"]

    def test_register_user_invalid_username_chars(self, auth):
        """Should reject usernames with special characters."""
        result = auth.register_user("user name", "user@example.com", "StrongPass1")
        assert "error" in result
        assert "underscores" in result["error"].lower()

    def test_register_user_invalid_email(self, auth):
        """Should reject invalid email formats."""
        result = auth.register_user("validuser", "not-an-email", "StrongPass1")
        assert "error" in result
        assert "email" in result["error"].lower()

    def test_register_user_short_password(self, auth):
        """Should reject passwords shorter than 8 characters."""
        result = auth.register_user("pwuser", "pw@example.com", "Short1")
        assert "error" in result
        assert "8 characters" in result["error"]

    def test_register_user_weak_password(self, auth):
        """Should reject passwords without uppercase, lowercase, and digit."""
        result = auth.register_user("weakuser", "weak@example.com", "alllowercase1")
        assert "error" in result
        assert "uppercase" in result["error"].lower()

    def test_register_user_invalid_role(self, auth):
        """Should reject invalid role values."""
        result = auth.register_user("roleuser", "role@example.com", "StrongPass1", "superadmin")
        assert "error" in result
        assert "Invalid role" in result["error"]

    def test_register_user_empty_inputs(self, auth):
        """Should reject empty username, email, or password."""
        result = auth.register_user("", "e@example.com", "StrongPass1")
        assert "error" in result

        result = auth.register_user("user2", "", "StrongPass1")
        assert "error" in result

        result = auth.register_user("user3", "e3@example.com", "")
        assert "error" in result


# ============================================================
#  User Login Tests
# ============================================================

class TestUserLogin:
    """Tests for user authentication."""

    def test_login_success(self, auth, registered_user):
        """Should log in with correct credentials."""
        result = auth.login_user("testuser", "StrongPass1")
        assert "error" not in result
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["token_type"] == "bearer"
        assert result["user"]["username"] == "testuser"

    def test_login_with_email(self, auth, registered_user):
        """Should log in using email instead of username."""
        result = auth.login_user("test@example.com", "StrongPass1")
        assert "error" not in result
        assert result["user"]["email"] == "test@example.com"

    def test_login_wrong_password(self, auth, registered_user):
        """Should fail with wrong password."""
        result = auth.login_user("testuser", "WrongPass1")
        assert "error" in result
        assert "credentials" in result["error"].lower()

    def test_login_nonexistent_user(self, auth):
        """Should fail for non-existent user."""
        result = auth.login_user("nouser", "SomePass123")
        assert "error" in result
        assert "credentials" in result["error"].lower()

    def test_login_deactivated_user(self, auth, registered_user):
        """Should fail for deactivated account."""
        uid = registered_user["user_id"]
        auth.deactivate_user(uid)
        result = auth.login_user("testuser", "StrongPass1")
        assert "error" in result
        assert "deactivated" in result["error"].lower()

    def test_login_updates_login_count(self, auth, registered_user):
        """Should increment login count after successful login."""
        uid = registered_user["user_id"]
        auth.login_user("testuser", "StrongPass1")
        user = auth.get_user(uid)
        assert user["login_count"] >= 1


# ============================================================
#  Token Management Tests
# ============================================================

class TestTokenManagement:
    """Tests for JWT/HMAC token creation, verification, and revocation."""

    def test_create_access_token(self, auth):
        """Should create an access token string."""
        token = auth.create_access_token(1, "user")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token(self, auth):
        """Should create a refresh token string."""
        token = auth.create_refresh_token(1)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_access_token(self, auth):
        """Should verify and decode a valid access token."""
        token = auth.create_access_token(1, "user")
        payload = auth.verify_token(token, "access")
        assert "error" not in payload
        assert payload["sub"] == "1"
        assert payload["role"] == "user"
        assert payload["type"] == "access"

    def test_verify_refresh_token(self, auth):
        """Should verify and decode a valid refresh token."""
        token = auth.create_refresh_token(1)
        payload = auth.verify_token(token, "refresh")
        assert "error" not in payload
        assert payload["sub"] == "1"
        assert payload["type"] == "refresh"

    def test_verify_token_wrong_type(self, auth):
        """Should reject token when type doesn't match."""
        token = auth.create_access_token(1, "user")
        payload = auth.verify_token(token, "refresh")
        assert "error" in payload
        assert "type" in payload["error"].lower()

    def test_verify_token_invalid_token(self, auth):
        """Should reject an invalid/malformed token."""
        payload = auth.verify_token("invalid.token.here", "access")
        assert "error" in payload

    def test_verify_token_empty_token(self, auth):
        """Should reject an empty token string."""
        payload = auth.verify_token("", "access")
        assert "error" in payload

    def test_revoke_token(self, auth):
        """Should revoke a token successfully."""
        token = auth.create_access_token(1, "user")
        assert auth.revoke_token(token) is True

    def test_is_token_revoked(self, auth):
        """Should detect revoked tokens."""
        token = auth.create_access_token(1, "user")
        payload = auth.verify_token(token, "access")
        jti = payload["jti"]
        assert auth.is_token_revoked(jti) is False
        auth.revoke_token(token)
        assert auth.is_token_revoked(jti) is True

    def test_revoked_token_verification_fails(self, auth):
        """Should fail verification for revoked tokens."""
        token = auth.create_access_token(1, "user")
        auth.revoke_token(token)
        payload = auth.verify_token(token, "access")
        assert "error" in payload
        assert "revoked" in payload["error"].lower()

    def test_is_token_revoked_empty_jti(self, auth):
        """Should return False for empty JTI."""
        assert auth.is_token_revoked("") is False

    def test_refresh_access_token(self, auth, registered_user):
        """Should exchange refresh token for new access + refresh tokens."""
        login_result = auth.login_user("testuser", "StrongPass1")
        refresh = login_result["refresh_token"]
        result = auth.refresh_access_token(refresh)
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["token_type"] == "bearer"

    def test_refresh_access_token_invalid(self, auth):
        """Should fail refresh with an invalid token."""
        result = auth.refresh_access_token("invalid-token")
        assert "error" in result

    def test_create_access_token_with_extra(self, auth):
        """Should include extra claims in the access token."""
        token = auth.create_access_token(1, "user", extra={"custom": "value"})
        payload = auth.verify_token(token, "access")
        assert payload.get("custom") == "value"


# ============================================================
#  User CRUD Tests
# ============================================================

class TestUserCRUD:
    """Tests for user management operations."""

    def test_get_user(self, auth, registered_user):
        """Should retrieve a user by ID without password hash."""
        uid = registered_user["user_id"]
        user = auth.get_user(uid)
        assert user is not None
        assert user["username"] == "testuser"
        assert "password_hash" not in user

    def test_get_user_nonexistent(self, auth):
        """Should return None for non-existent user ID."""
        user = auth.get_user(99999)
        assert user is None

    def test_update_user_email(self, auth, registered_user):
        """Should update user email."""
        uid = registered_user["user_id"]
        result = auth.update_user(uid, email="newemail@example.com")
        assert "error" not in result
        assert result["email"] == "newemail@example.com"

    def test_update_user_role(self, auth, registered_user):
        """Should update user role."""
        uid = registered_user["user_id"]
        result = auth.update_user(uid, role="manager")
        assert "error" not in result
        assert result["role"] == "manager"

    def test_update_user_invalid_role(self, auth, registered_user):
        """Should reject invalid role update."""
        uid = registered_user["user_id"]
        result = auth.update_user(uid, role="superadmin")
        assert "error" in result
        assert "Invalid role" in result["error"]

    def test_update_user_no_valid_fields(self, auth, registered_user):
        """Should reject updates with no valid fields."""
        uid = registered_user["user_id"]
        result = auth.update_user(uid, invalid_field="value")
        assert "error" in result

    def test_update_nonexistent_user(self, auth):
        """Should return error for non-existent user update."""
        result = auth.update_user(99999, email="x@example.com")
        assert "error" in result

    def test_deactivate_user(self, auth, registered_user):
        """Should deactivate a user."""
        uid = registered_user["user_id"]
        assert auth.deactivate_user(uid) is True
        user = auth.get_user(uid)
        assert user["active"] == 0

    def test_deactivate_nonexistent_user(self, auth):
        """Should return False for non-existent user deactivation."""
        assert auth.deactivate_user(99999) is False

    def test_list_users(self, auth, registered_user):
        """Should list registered users."""
        users = auth.list_users()
        assert isinstance(users, list)
        assert len(users) >= 1

    def test_list_users_by_role(self, auth, admin_user, registered_user):
        """Should filter users by role."""
        admins = auth.list_users(role="admin")
        assert all(u["role"] == "admin" for u in admins)

    def test_change_password(self, auth, registered_user):
        """Should change password with correct old password."""
        uid = registered_user["user_id"]
        assert auth.change_password(uid, "StrongPass1", "NewStrong1") is True
        # Verify new password works
        result = auth.login_user("testuser", "NewStrong1")
        assert "error" not in result

    def test_change_password_wrong_old(self, auth, registered_user):
        """Should fail with wrong old password."""
        uid = registered_user["user_id"]
        assert auth.change_password(uid, "WrongOld1", "NewStrong1") is False

    def test_reset_password(self, auth, registered_user):
        """Should reset password without old password (admin op)."""
        uid = registered_user["user_id"]
        assert auth.reset_password(uid, "ResetPass1") is True
        result = auth.login_user("testuser", "ResetPass1")
        assert "error" not in result


# ============================================================
#  RBAC Tests
# ============================================================

class TestRBAC:
    """Tests for Role-Based Access Control."""

    def test_check_permission_admin(self, auth, admin_user):
        """Admin should have manage_users permission."""
        uid = admin_user["user_id"]
        assert auth.check_permission(uid, "manage_users") is True

    def test_check_permission_user_read(self, auth, registered_user):
        """Regular user should have read permission."""
        uid = registered_user["user_id"]
        assert auth.check_permission(uid, "read") is True

    def test_check_permission_user_no_manage(self, auth, registered_user):
        """Regular user should NOT have manage_users permission."""
        uid = registered_user["user_id"]
        assert auth.check_permission(uid, "manage_users") is False

    def test_check_role_admin_meets_user(self, auth, admin_user):
        """Admin role should meet minimum 'user' role requirement."""
        uid = admin_user["user_id"]
        assert auth.check_role(uid, "user") is True

    def test_check_role_user_not_meet_admin(self, auth, registered_user):
        """User role should NOT meet minimum 'admin' role requirement."""
        uid = registered_user["user_id"]
        assert auth.check_role(uid, "admin") is False

    def test_check_role_deactivated_user(self, auth, registered_user):
        """Deactivated user should fail role check."""
        uid = registered_user["user_id"]
        auth.deactivate_user(uid)
        assert auth.check_role(uid, "user") is False

    def test_check_role_nonexistent_user(self, auth):
        """Non-existent user should fail role check."""
        assert auth.check_role(99999, "user") is False

    def test_get_user_permissions(self, auth, admin_user):
        """Should return correct permissions for admin role."""
        uid = admin_user["user_id"]
        perms = auth.get_user_permissions(uid)
        assert "manage_users" in perms
        assert "read" in perms

    def test_get_user_permissions_viewer(self, auth):
        """Viewer role should only have read permission."""
        result = auth.register_user("viewer1", "viewer@example.com", "ViewerPass1", "viewer")
        uid = result["user_id"]
        perms = auth.get_user_permissions(uid)
        assert perms == {"read"}


# ============================================================
#  API Key Tests
# ============================================================

class TestAPIKeys:
    """Tests for API key authentication."""

    def test_create_api_key(self, auth, registered_user):
        """Should create an API key for a user."""
        uid = registered_user["user_id"]
        result = auth.create_api_key(uid, "test-key", ["read", "write"])
        assert "error" not in result
        assert "api_key" in result
        assert result["api_key"].startswith("titan_")
        assert result["name"] == "test-key"
        assert result["permissions"] == ["read", "write"]

    def test_create_api_key_nonexistent_user(self, auth):
        """Should fail for non-existent user."""
        result = auth.create_api_key(99999, "test-key")
        assert "error" in result

    def test_create_api_key_deactivated_user(self, auth, registered_user):
        """Should fail for deactivated user."""
        uid = registered_user["user_id"]
        auth.deactivate_user(uid)
        result = auth.create_api_key(uid, "test-key")
        assert "error" in result

    def test_verify_api_key(self, auth, registered_user):
        """Should verify a valid API key."""
        uid = registered_user["user_id"]
        key_result = auth.create_api_key(uid, "test-key", ["read"])
        api_key = key_result["api_key"]
        identity = auth.verify_api_key(api_key)
        assert identity is not None
        assert identity["user_id"] == uid
        assert identity["name"] == "test-key"
        assert "read" in identity["permissions"]

    def test_verify_api_key_invalid(self, auth):
        """Should return None for invalid API key."""
        assert auth.verify_api_key("invalid_key") is None

    def test_verify_api_key_wrong_prefix(self, auth):
        """Should return None for key without titan_ prefix."""
        assert auth.verify_api_key("wrong_prefix_abc123") is None

    def test_verify_api_key_empty(self, auth):
        """Should return None for empty API key."""
        assert auth.verify_api_key("") is None

    def test_verify_api_key_revoked(self, auth, registered_user):
        """Should return None for revoked API key."""
        uid = registered_user["user_id"]
        key_result = auth.create_api_key(uid, "test-key")
        key_id = key_result["key_id"]
        api_key = key_result["api_key"]
        auth.revoke_api_key(key_id)
        assert auth.verify_api_key(api_key) is None

    def test_revoke_api_key(self, auth, registered_user):
        """Should revoke an API key."""
        uid = registered_user["user_id"]
        key_result = auth.create_api_key(uid, "test-key")
        key_id = key_result["key_id"]
        assert auth.revoke_api_key(key_id) is True

    def test_revoke_api_key_nonexistent(self, auth):
        """Should return False for non-existent key ID."""
        assert auth.revoke_api_key("nonexistent_key_id") is False

    def test_list_api_keys(self, auth, registered_user):
        """Should list API keys for a user."""
        uid = registered_user["user_id"]
        auth.create_api_key(uid, "key1")
        auth.create_api_key(uid, "key2")
        keys = auth.list_api_keys(uid)
        assert isinstance(keys, list)
        assert len(keys) >= 2


# ============================================================
#  Validation Tests
# ============================================================

class TestValidation:
    """Tests for the _validate_registration static method."""

    def test_valid_inputs(self):
        """Should return empty list for valid inputs."""
        errors = AuthService._validate_registration("validuser", "valid@example.com", "StrongPass1")
        assert errors == []

    def test_short_username(self):
        """Should report username too short."""
        errors = AuthService._validate_registration("ab", "e@example.com", "StrongPass1")
        assert any("3 characters" in e for e in errors)

    def test_long_username(self):
        """Should report username too long."""
        errors = AuthService._validate_registration("a" * 51, "e@example.com", "StrongPass1")
        assert any("50 characters" in e for e in errors)

    def test_invalid_username_chars(self):
        """Should report invalid username characters."""
        errors = AuthService._validate_registration("user@name", "e@example.com", "StrongPass1")
        assert any("underscores" in e.lower() for e in errors)

    def test_missing_email(self):
        """Should report missing email."""
        errors = AuthService._validate_registration("validuser", "", "StrongPass1")
        assert any("email" in e.lower() for e in errors)

    def test_invalid_email(self):
        """Should report invalid email format."""
        errors = AuthService._validate_registration("validuser", "not-email", "StrongPass1")
        assert any("email" in e.lower() for e in errors)

    def test_short_password(self):
        """Should report password too short."""
        errors = AuthService._validate_registration("validuser", "e@example.com", "Short1")
        assert any("8 characters" in e for e in errors)

    def test_weak_password_no_uppercase(self):
        """Should report missing uppercase in password."""
        errors = AuthService._validate_registration("validuser", "e@example.com", "alllowercase1")
        assert any("uppercase" in e.lower() for e in errors)

    def test_weak_password_no_digit(self):
        """Should report missing digit in password."""
        errors = AuthService._validate_registration("validuser", "e@example.com", "NoDigitPass")
        assert any("digit" in e.lower() for e in errors)

    def test_empty_username(self):
        """Should report empty/short username."""
        errors = AuthService._validate_registration("", "e@example.com", "StrongPass1")
        assert len(errors) > 0

    def test_empty_password(self):
        """Should report empty/short password."""
        errors = AuthService._validate_registration("validuser", "e@example.com", "")
        assert len(errors) > 0


# ============================================================
#  Statistics and Utility Tests
# ============================================================

class TestStatsAndUtility:
    """Tests for get_stats and ensure_admin."""

    def test_get_stats_empty(self, auth):
        """Should return zero stats for fresh database."""
        stats = auth.get_stats()
        assert stats["total_users"] == 0
        assert stats["active_users"] == 0
        assert stats["revoked_tokens"] == 0
        assert stats["active_api_keys"] == 0
        assert "jose_available" in stats
        assert "passlib_available" in stats

    def test_get_stats_after_registration(self, auth, registered_user):
        """Should reflect registered user in stats."""
        stats = auth.get_stats()
        assert stats["total_users"] == 1
        assert stats["active_users"] == 1

    def test_ensure_admin_creates_first(self, auth):
        """Should create admin user if none exists."""
        result = auth.ensure_admin("admin", "AdminPass1")
        assert "error" not in result
        assert result.get("initial_password") == "AdminPass1"

    def test_ensure_admin_exists(self, auth, admin_user):
        """Should detect existing admin and not create another."""
        result = auth.ensure_admin("admin", "NewAdminPass1")
        assert "already exists" in result["message"].lower()

    def test_ensure_admin_generates_password(self, auth):
        """Should generate password if none provided."""
        result = auth.ensure_admin("admin")
        assert "error" not in result
        assert "initial_password" in result

    def test_cleanup_revoked_tokens(self, auth):
        """Should clean up expired revoked tokens."""
        count = auth.cleanup_revoked_tokens()
        assert isinstance(count, int)
        assert count >= 0

    def test_role_hierarchy_consistency(self):
        """ROLE_HIERARCHY should have expected roles with increasing levels."""
        assert ROLE_HIERARCHY["viewer"] < ROLE_HIERARCHY["user"]
        assert ROLE_HIERARCHY["user"] < ROLE_HIERARCHY["manager"]
        assert ROLE_HIERARCHY["manager"] < ROLE_HIERARCHY["admin"]

    def test_role_permissions_consistency(self):
        """ROLE_PERMISSIONS should have permissions for all roles in hierarchy."""
        for role in ROLE_HIERARCHY:
            assert role in ROLE_PERMISSIONS

    def test_database_initialization(self, tmp_path):
        """AuthService should properly initialize the database on creation."""
        db_path = str(tmp_path / "init_test.sqlite")
        svc = AuthService(db_path=db_path, secret_key="test")
        # Tables should exist - verify by getting stats
        stats = svc.get_stats()
        assert isinstance(stats, dict)
        assert "total_users" in stats
