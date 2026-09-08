"""RBAC 访问控制装饰器。

F7 原则：默认拒绝 + 最小权限。
- prod 模式：未声明 @require_role 的路由 → 拒绝（fail-secure）。
- dev 模式：未声明 @require_role 的路由 → 放行（便于调试）。
"""

from __future__ import annotations

import functools
from typing import Any

from fastapi import HTTPException

from api.dependencies.auth import AuthContext
from config.settings import get_settings


def require_role(*roles: str):
    """路由级权限装饰器：检查 auth.role 是否在允许的 role 列表中。

    用法：
        @router.post("/agents/{name}/invoke")
        @require_role("admin", "engineer")
        async def invoke_agent(...):
            ...
    """
    def decorator(func: Any) -> Any:
        @functools.wraps(func)
        async def wrapper(*args: Any, auth: AuthContext, **kwargs: Any) -> Any:
            settings = get_settings()
            # dev 模式放宽：仅当显式声明了 require_role 时才校验
            if settings.app_env == "prod" and auth.role not in roles:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "20001",
                        "message": f"RBAC 拒绝：角色 {auth.role!r} 无权访问（需要 {list(roles)}）",
                    },
                )
            return await func(*args, auth=auth, **kwargs)
        return wrapper
    return decorator


def require_permission(resource: str, action: str):
    """细粒度权限装饰器：检查 role 对 resource 的 action 权限。"""
    def decorator(func: Any) -> Any:
        @functools.wraps(func)
        async def wrapper(*args: Any, auth: AuthContext, **kwargs: Any) -> Any:
            from core.security.permissions import check_permission
            settings = get_settings()
            if settings.app_env == "prod":
                if not check_permission(auth.role, resource, action):
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "code": "20001",
                            "message": f"RBAC 拒绝：{auth.role} 无权 {action} {resource}",
                        },
                    )
            return await func(*args, auth=auth, **kwargs)
        return wrapper
    return decorator
