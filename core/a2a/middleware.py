"""A2A 中间件：鉴权 / 日志 / 追踪 / 限流插槽。

每个中间件签名：
    async def mw(req: JSONRPCRequest, agent_name: str) -> None
异常直接抛出，server 会转为 A2A 错误响应。
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Awaitable, Callable

from core.a2a.serializers import JSONRPCRequest

logger = logging.getLogger("core.a2a.middleware")

Middleware = Callable[[JSONRPCRequest, str], Awaitable[None]]


# =====================================================
# 日志中间件
# =====================================================
async def logging_middleware(req: JSONRPCRequest, agent_name: str) -> None:
    """记录 A2A 请求的方法/智能体/ID，便于排障。"""
    logger.info(
        "A2A req method=%s agent=%s id=%s",
        req.method, agent_name, req.id,
    )


async def timing_middleware(req: JSONRPCRequest, agent_name: str) -> None:
    """打印请求到达时间（与耗时统计一起使用可挂 trace）。"""
    req.params.setdefault("_meta", {})
    req.params["_meta"]["received_at"] = time.time()


# =====================================================
# 鉴权中间件（占位实现，阶段四实装 JWT/Token 校验）
# =====================================================
async def auth_middleware(req: JSONRPCRequest, agent_name: str) -> None:
    """默认放行；阶段四在此校验 Authorization / JWT。

    严格模式下应：
        from common.exceptions import AuthenticationError
        token = req.params.get("auth_token")
        if not token or not verify_jwt(token):
            raise AuthenticationError("A2A 调用未认证")
    """
    return None


# =====================================================
# 限流中间件（占位实现）
# =====================================================
class RateLimiter:
    """基于滑动窗口的简单限流器（按 agent_name 维度）。"""

    def __init__(self, max_requests: int = 100, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # 用 deque 实现 O(1) popleft；早期版本用 list + pop(0) 是 O(n)
        self._hits: dict[str, deque[float]] = {}

    def middleware(self) -> Middleware:
        limiter = self

        async def _mw(req: JSONRPCRequest, agent_name: str) -> None:
            import time as _t
            now = _t.time()
            window = limiter.window_seconds
            buf = limiter._hits.setdefault(agent_name, deque())
            # 淘汰窗口外
            while buf and now - buf[0] > window:
                buf.popleft()
            if len(buf) >= limiter.max_requests:
                from common.exceptions import A2AError
                raise A2AError(
                    "A2A 调用频率超限",
                    details={"agent": agent_name, "limit": limiter.max_requests, "window": window},
                )
            buf.append(now)

        return _mw
