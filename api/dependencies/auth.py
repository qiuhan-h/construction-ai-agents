"""JWT / dev 鉴权依赖。

设计原则（D1, D3）：
- 优先用 python-jose 解析 HS256 token；
- 缺失时降级为 ``dev-{tenant_id}-{user_id}`` 前缀校验，仅供本地开发；
- 任何失败统一抛 401，错误码 30001（UNAUTHORIZED）。
- 4d 不引入 RBAC，仅做租户提取 + 身份记录。
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import get_settings

logger = logging.getLogger("api.dependencies.auth")

# 进程级安全锁：保证 reset_auth_state 在并发场景下不撕裂
_auth_lock = threading.Lock()

_bearer = HTTPBearer(auto_error=True)


class AuthContext:
    """鉴权上下文：从 Authorization Bearer token 解析得到。

    6b.2 新增 ``role`` 字段（默认 viewer），来源：
    - dev token: 固定 ``admin``（便于本地调试）；
    - JWT: ``role`` claim，缺失时默认 ``viewer``。
    """

    def __init__(
        self,
        tenant_id: str,
        user_id: str,
        scopes: list[str],
        role: str = "viewer",
        attributes: dict[str, Any] | None = None,
    ):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.scopes = scopes
        self.role = role
        self.attributes = attributes or {}

    def has_scope(self, scope: str) -> bool:
        return "*" in self.scopes or scope in self.scopes

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "scopes": list(self.scopes),
            "role": self.role,
            "attributes": dict(self.attributes),
        }


def _parse_dev_token(token: str) -> AuthContext:
    """``dev-{tenant_id}-{user_id}`` 形式解析。"""
    if not token.startswith("dev-"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "30001", "message": "invalid token (jose missing, only dev- prefix allowed)"},
        )
    parts = token[4:].split("-", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "30001", "message": "dev token 格式错误: dev-{tenant}-{user}"},
        )
    tenant_id, user_id = parts[0], parts[1]
    return AuthContext(
        tenant_id=tenant_id,
        user_id=user_id,
        scopes=["*"],
        role="admin",  # dev 模式默认 admin（便于本地调试）
    )


def _parse_jwt_token(token: str) -> AuthContext:
    """HS256 JWT 解析。"""
    from jose import JWTError, jwt

    settings = get_settings()
    secret = settings.api_jwt_secret.get_secret_value()
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "30001", "message": f"invalid jwt: {e}"},
        ) from e

    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "30001", "message": "missing tenant_id claim"},
        )
    user_id = str(payload.get("user_id") or "unknown")
    scopes = list(payload.get("scopes") or [])
    # 6b.2: 从 JWT claims 解析 role（缺失时默认 viewer）
    role = str(payload.get("role") or "viewer")
    attributes = dict(payload.get("attributes") or {})
    return AuthContext(
        tenant_id=str(tenant_id),
        user_id=user_id,
        scopes=scopes,
        role=role,
        attributes=attributes,
    )


async def get_auth_context(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> AuthContext:
    """FastAPI 依赖：从 Bearer token 解析 AuthContext。

    解析顺序：
    1. token 以 ``dev-`` 开头 → 走 dev 降级（不论 jose 是否可用）；
    2. 否则按 JWT 解码；
    3. jose 缺失 → 走 dev 降级。
    """
    token = creds.credentials
    # 1) dev- 前缀：始终降级解析
    if token.startswith("dev-"):
        return _parse_dev_token(token)
    # 2) 尝试 JWT
    try:
        return _parse_jwt_token(token)
    except ImportError:
        logger.warning("python-jose 缺失，降级为 dev- 前缀鉴权")
        return _parse_dev_token(token)


# =====================================================
# 测试钩子：mock 注入 + 重置
# =====================================================
_test_override: AuthContext | None = None
_test_override_lock = threading.Lock()


def set_auth_override(ctx: AuthContext | None) -> None:
    """测试用：直接覆盖 get_auth_context 的返回值。"""
    global _test_override
    with _test_override_lock:
        _test_override = ctx


def reset_auth_state() -> None:
    """重置测试覆盖 + 计数器。"""
    global _test_override
    with _auth_lock:
        _test_override = None


def _maybe_override(ctx: AuthContext) -> AuthContext:
    with _auth_lock:
        if _test_override is not None:
            return _test_override
    return ctx


# 重新挂一个 wrapped 依赖，保留 reset 钩子
_get_auth_context_real = get_auth_context


async def get_auth_context_with_override(  # noqa: ANN201
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
):
    ctx = await _get_auth_context_real(creds=creds)
    return _maybe_override(ctx)


# 用支持 override 的版本覆盖默认导出
get_auth_context = get_auth_context_with_override  # type: ignore[assignment]


__all__ = [
    "AuthContext",
    "get_auth_context",
    "set_auth_override",
    "reset_auth_state",
]
