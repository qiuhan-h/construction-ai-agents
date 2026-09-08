"""审计日志中间件（7a-5 安全加固）。

记录 API 请求的审计轨迹：tenant_id + actor + action + resource + status_code。
生产环境合规审计与安全追溯使用。

设计：
- 仅记录写操作（POST/PUT/PATCH/DELETE）和登录操作，减少日志量；
- 数据库写入在后台线程执行，不阻塞响应；
- 数据库不可用时降级为 logger 记录。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("core.middleware.audit")


class AuditLogMiddleware(BaseHTTPMiddleware):
    """审计日志中间件：记录写操作和登录操作的审计轨迹。"""

    # 需要审计的 HTTP 方法（GET 不记录以减少日志量）
    _AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method

        # 跳过健康检查、指标端点
        if path.startswith("/api/v1/health") or path.startswith("/metrics"):
            return await call_next(request)

        # 仅记录写操作和登录操作
        is_auth = "/login" in path or "/auth" in path
        if method not in self._AUDITED_METHODS and not is_auth:
            return await call_next(request)

        # 处理请求
        response: Response = await call_next(request)

        # 提取审计信息
        tenant_id = request.headers.get("X-Tenant-ID", "unknown")
        actor = request.headers.get("X-User-ID", "system")
        ip = request.client.host if request.client else ""
        action = self._determine_action(method, path)

        # 后台记录审计日志（不阻塞响应）
        try:
            asyncio.get_running_loop().create_task(
                self._record_audit_log(
                    tenant_id=tenant_id,
                    actor=actor,
                    action=action,
                    resource=path,
                    method=method,
                    status_code=response.status_code,
                    ip=ip,
                )
            )
        except RuntimeError:
            # 无事件循环时降级为同步日志
            logger.info(
                "AUDIT tenant=%s actor=%s action=%s %s %s -> %s",
                tenant_id, actor, action, method, path, response.status_code,
            )

        return response

    def _determine_action(self, method: str, path: str) -> str:
        """根据HTTP方法和路径确定操作类型。"""
        if "/login" in path or "/auth" in path:
            return "login"
        if method == "POST":
            if "/trigger" in path or "/run" in path:
                return "execute"
            return "create"
        if method in ("PUT", "PATCH"):
            return "update"
        if method == "DELETE":
            return "delete"
        return method.lower()

    async def _record_audit_log(self, **kwargs: Any) -> None:
        """异步记录审计日志到数据库；失败降级为日志。"""
        try:
            await asyncio.to_thread(self._write_to_db, kwargs)
        except Exception as e:  # noqa: BLE001
            logger.warning("审计日志写入失败，降级为日志: %s | %s", e, kwargs)

    def _write_to_db(self, data: dict[str, Any]) -> None:
        """同步写入数据库。"""
        try:
            from core.storage.sqlalchemy_repos import get_session_scope
            from models.database.security_audit_log import SecurityAuditLogTable

            with get_session_scope() as session:
                log_entry = SecurityAuditLogTable(
                    id=uuid.uuid4().hex,
                    tenant_id=data.get("tenant_id", "unknown"),
                    actor=data.get("actor", "system"),
                    action=data.get("action", ""),
                    resource=data.get("resource"),
                    method=data.get("method"),
                    status_code=data.get("status_code"),
                    ip=data.get("ip"),
                    detail={},
                )
                session.add(log_entry)
        except ImportError:
            logger.debug("审计日志模块未就绪: %s", data)
        except Exception as e:  # noqa: BLE001
            logger.warning("审计日志写入数据库失败: %s | %s", e, data)
