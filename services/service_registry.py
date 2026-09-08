"""服务注册表（Service Registry）：system 动作的统一调度入口。

设计原则（O3, O4）：
- 编排器工作流中 `kind=system` 的节点，统一通过 `ServiceRegistry.dispatch(action, params, tenant_id)` 调用；
- 注册用 `@register_service("services.notify")` 装饰器，action 全名命名；
- 注册器自身只是路由，不做业务逻辑，4c 首版允许 handler 为空（返回 ack=False）。

Action 命名约定（与 4c plan 对齐）：
- `services.notify`         → 通知聚合（按 severity 路由渠道）
- `services.human_review`   → 人工复核请求创建
- `services.document.upload`→ 文档上传
- `services.ingest.iot`     → IoT 数据写入 TSDB
- `services.ingest.file`    → 文件类数据（图纸/法规）入库
- `services.ingest.api`     → 第三方 API 数据规范化
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


ServiceHandler = Callable[..., Awaitable[Any]]


# =====================================================
# 注册表（进程级单例）
# =====================================================
_REGISTRY: dict[str, ServiceHandler] = {}


def register_service(action: str) -> Callable[[ServiceHandler], ServiceHandler]:
    """装饰器：注册服务 action 处理器。

    使用：
        @register_service("services.notify")
        async def _notify(params, tenant_id): ...
    """

    def _wrap(fn: ServiceHandler) -> ServiceHandler:
        if action in _REGISTRY:
            logger.warning("服务 action 已注册，将被覆盖: %s", action)
        _REGISTRY[action] = fn
        return fn

    return _wrap


def unregister_service(action: str) -> bool:
    return _REGISTRY.pop(action, None) is not None


def list_services() -> list[str]:
    return sorted(_REGISTRY.keys())


def get_service(action: str) -> ServiceHandler | None:
    return _REGISTRY.get(action)


def is_registered(action: str) -> bool:
    return action in _REGISTRY


# =====================================================
# 调度
# =====================================================
class ServiceRegistry:
    """服务注册表（静态方法门面）。"""

    @staticmethod
    def dispatch(
        action: str,
        params: dict | None = None,
        tenant_id: str = "",
    ) -> Any:
        """分发 action；返回 handler 的返回值（异步时通过 asyncio 桥接）。

        - handler 是 async：返回 coroutine，调用方需 await；
        - handler 不存在：返回 _NotHandled（await 安全，可直接 await）；
        - handler 同步：返回 asyncio.to_thread 包装的 coroutine。
        """
        handler = _REGISTRY.get(action)
        if handler is None:
            logger.warning(
                "服务 action 未注册 action=%s（已注册: %s）",
                action, list(_REGISTRY.keys()),
            )
            return _NotHandled(action=action, params=params, tenant_id=tenant_id)
        # 校验必传 tenant_id
        sig = inspect.signature(handler)
        try:
            sig.bind(params or {}, tenant_id)
        except TypeError as e:
            raise ValueError(
                f"服务 {action} handler 签名不匹配 (params, tenant_id): {e}"
            ) from e
        if inspect.iscoroutinefunction(handler):
            return handler(params or {}, tenant_id)
        # 同步 handler：用 to_thread 避免阻塞事件循环
        return asyncio.to_thread(handler, params or {}, tenant_id)

    @staticmethod
    def is_registered(action: str) -> bool:
        return action in _REGISTRY

    @staticmethod
    def reset() -> None:
        """重置注册表（测试用）。"""
        _REGISTRY.clear()


# =====================================================
# 未注册结果占位
# =====================================================
class _NotHandled:
    """handler 未注册的占位返回值。

    H1 修正：实现 ``__await__`` 使其 await 安全，
    避免 ``await dispatch(...)`` 在 handler 未注册时抛 TypeError。
    """

    def __init__(self, action: str, params: dict | None, tenant_id: str) -> None:
        self.action = action
        self.params = params or {}
        self.tenant_id = tenant_id

    def __await__(self):
        """await _NotHandled → 返回 self.to_dict()。"""
        yield  # 使本函数成为合法的 generator-based coroutine
        return self.to_dict()

    def to_dict(self) -> dict:
        return {
            "ack": False,
            "action": self.action,
            "tenant_id": self.tenant_id,
            "reason": "service_not_registered",
        }


# =====================================================
# 4c 内置服务实现（编排器 / 业务 Agent 调用入口）
# =====================================================
@register_service("services.notify")
async def _service_notify(params: dict, tenant_id: str) -> dict:
    """通知聚合 dispatch（按 severity 路由到具体渠道）。"""
    from services.notification_service import get_notification_service

    severity = params.get("severity", "info")
    event_type = params.get("event_type", "manual.notify")
    title = params.get("title", "")
    body = params.get("body", "")
    channels = params.get("channels")
    meta = {
        k: v
        for k, v in params.items()
        if k not in {"severity", "event_type", "title", "body", "channels", "tenant_id"}
    }
    svc = get_notification_service()
    sent = await svc.send(
        tenant_id=tenant_id or params.get("tenant_id", ""),
        event_type=event_type,
        severity=severity,
        title=title,
        body=body,
        channels=channels,
        **meta,
    )
    return {"ack": True, "action": "services.notify", "sent": sent}


@register_service("services.human_review")
async def _service_human_review(params: dict, tenant_id: str) -> dict:
    """创建人工复核请求。"""
    from services.human_review_service import get_human_review_service

    svc = get_human_review_service()
    rid = await svc.create(
        tenant_id=tenant_id,
        task_id=params.get("task_id", ""),
        reason=params.get("reason", ""),
        context=params.get("context", {}),
    )
    return {"ack": True, "action": "services.human_review", "request_id": rid}


@register_service("services.document.upload")
async def _service_document_upload(params: dict, tenant_id: str) -> dict:
    """文档上传：bytes 走 params["file"]，filename 必填。"""
    from services.document_service import get_document_service

    project_id = params.get("project_id", "")
    filename = params.get("filename", "unnamed")
    file = params.get("file", b"")
    svc = get_document_service()
    storage_key = await svc.upload(
        tenant_id=tenant_id, project_id=project_id, file=file, filename=filename
    )
    return {
        "ack": True,
        "action": "services.document.upload",
        "storage_key": storage_key,
    }


@register_service("services.ingest.iot")
async def _service_ingest_iot(params: dict, tenant_id: str) -> dict:
    """IoT 传感器数据接入（4c mock：仅返回规范化结果）。"""
    return {
        "ack": True,
        "action": "services.ingest.iot",
        "tenant_id": tenant_id,
        "sensor_id": params.get("sensor_id"),
        "value": params.get("value"),
        "ts": params.get("ts"),
        "mode": "mock",
    }


@register_service("services.ingest.file")
async def _service_ingest_file(params: dict, tenant_id: str) -> dict:
    """文件类数据接入（4c mock：返回文件指纹）。"""
    import hashlib

    raw = params.get("raw", b"")
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    fingerprint = hashlib.sha256(raw).hexdigest()
    return {
        "ack": True,
        "action": "services.ingest.file",
        "tenant_id": tenant_id,
        "kind": params.get("kind", "regulation"),
        "fingerprint": fingerprint,
        "size": len(raw),
    }


@register_service("services.ingest.api")
async def _service_ingest_api(params: dict, tenant_id: str) -> dict:
    """第三方 API 数据接入（4c mock：返回规范化字段）。"""
    return {
        "ack": True,
        "action": "services.ingest.api",
        "tenant_id": tenant_id,
        "endpoint": params.get("endpoint"),
        "normalized": {
            k: v
            for k, v in params.items()
            if k in {"code", "title", "version", "effective_at"}
        },
    }
