"""
RBAC and FastAPI integration mixin for AuthService.
"""

from ._imports import (
    logger, ROLE_HIERARCHY, ROLE_PERMISSIONS,
    HAS_FASTAPI, Depends, HTTPException, _security,
)


class RbacMixin:
    """RBAC and FastAPI integration for AuthService."""

    def check_permission(self, user_id: int, permission: str) -> bool:
        """Check if user has a specific permission."""
        return permission in self.get_user_permissions(user_id)

    def check_role(self, user_id: int, minimum_role: str) -> bool:
        """Check if user meets minimum role level."""
        user = self.get_user(user_id)
        if not user or not user.get("active"):
            return False
        return ROLE_HIERARCHY.get(user.get("role", ""), -1) >= ROLE_HIERARCHY.get(minimum_role, -1)

    def get_user_permissions(self, user_id: int) -> set:
        """Get all permissions for user based on their role."""
        user = self.get_user(user_id)
        if not user or not user.get("active"):
            return set()
        return ROLE_PERMISSIONS.get(user.get("role", "viewer"), set())

    def require_permission(self, permission: str):
        """FastAPI dependency factory requiring a specific permission."""
        auth = self
        async def _check(credentials=Depends(_security)) -> dict:
            payload = auth.verify_token(credentials.credentials, "access")
            if "error" in payload:
                raise HTTPException(status_code=401, detail=payload["error"],
                                    headers={"WWW-Authenticate": "Bearer"})
            uid = int(payload["sub"])
            if not auth.check_permission(uid, permission):
                raise HTTPException(status_code=403, detail=f"Permission '{permission}' required")
            return {"user_id": uid, "role": payload.get("role", "user"),
                    "permissions": list(auth.get_user_permissions(uid))}
        return _check

    def require_role(self, minimum_role: str):
        """FastAPI dependency factory requiring minimum role."""
        auth = self
        async def _check(credentials=Depends(_security)) -> dict:
            payload = auth.verify_token(credentials.credentials, "access")
            if "error" in payload:
                raise HTTPException(status_code=401, detail=payload["error"],
                                    headers={"WWW-Authenticate": "Bearer"})
            uid = int(payload["sub"])
            if not auth.check_role(uid, minimum_role):
                raise HTTPException(status_code=403, detail=f"Role '{minimum_role}' or higher required")
            return {"user_id": uid, "role": payload.get("role", "user"),
                    "permissions": list(auth.get_user_permissions(uid))}
        return _check

    def get_auth_dependencies(self) -> dict:
        """Returns FastAPI dependency functions for auth."""
        if not HAS_FASTAPI:
            return {"error": "FastAPI not available"}
        auth = self

        async def get_current_user(credentials=Depends(_security)) -> dict:
            payload = auth.verify_token(credentials.credentials, "access")
            if "error" in payload:
                raise HTTPException(status_code=401, detail=payload["error"],
                                    headers={"WWW-Authenticate": "Bearer"})
            uid = int(payload["sub"])
            user = auth.get_user(uid)
            if not user or not user.get("active"):
                raise HTTPException(status_code=401, detail="User not found or deactivated")
            return {"user_id": uid, "username": user.get("username", ""),
                    "role": user.get("role", "viewer"), "permissions": list(auth.get_user_permissions(uid))}

        async def require_admin(user=Depends(get_current_user)) -> dict:
            if user.get("role") != "admin":
                raise HTTPException(status_code=403, detail="Admin access required")
            return user

        async def require_manager(user=Depends(get_current_user)) -> dict:
            if ROLE_HIERARCHY.get(user.get("role", ""), -1) < ROLE_HIERARCHY["manager"]:
                raise HTTPException(status_code=403, detail="Manager or admin access required")
            return user

        return {
            "get_current_user": get_current_user,
            "require_admin": require_admin,
            "require_manager": require_manager,
            "require_permission": lambda perm: auth.require_permission(perm),
        }

    def protect_endpoint(self, minimum_role: str = "user"):
        """Decorator to protect a FastAPI endpoint by role."""
        if not HAS_FASTAPI:
            return lambda f: f
        auth = self

        def decorator(func):
            async def wrapper(*args, **kwargs):
                request = kwargs.get("request")
                if not request:
                    raise HTTPException(status_code=401, detail="No request object found")
                auth_hdr = request.headers.get("Authorization", "")
                if not auth_hdr.startswith("Bearer "):
                    raise HTTPException(status_code=401, detail="Bearer token required",
                                        headers={"WWW-Authenticate": "Bearer"})
                payload = auth.verify_token(auth_hdr[7:], "access")
                if "error" in payload:
                    raise HTTPException(status_code=401, detail=payload["error"])
                uid = int(payload["sub"])
                if not auth.check_role(uid, minimum_role):
                    raise HTTPException(status_code=403, detail=f"Role '{minimum_role}' or higher required")
                kwargs["auth_user_id"] = uid
                kwargs["auth_role"] = payload.get("role", "viewer")
                return await func(*args, **kwargs)
            wrapper.__name__ = func.__name__
            wrapper.__doc__ = func.__doc__
            return wrapper
        return decorator
