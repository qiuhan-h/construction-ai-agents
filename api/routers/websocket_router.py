"""WebSocket 路由（4d D5）。

端点（/api/v1/ws 前缀）：
  WS /api/v1/ws/events?topic=alert.*&tenant_id=tnt_x  实时事件推送

设计：
- 客户端在 query 携带 ``topic``（支持通配符 ``*``）与 ``tenant_id``；
- 服务端先订阅，再 accept WebSocket，避免竞态（参考 4d plan §3.8）；
- 每 30s 发 ping；客户端断线时取消订阅并清理资源；
- 4d 不要求鉴权：ws query 传 tenant_id 即可（生产由前置网关做 JWT）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

logger = logging.getLogger("api.routers.websocket")


PING_INTERVAL_SECONDS = 30.0


def build_websocket_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/ws", tags=["websocket"])

    @router.websocket("/events")
    async def events_ws(
        ws: WebSocket,
        topic: str = Query(default="*.*", description="事件主题或通配符"),
        tenant_id: str = Query(default="", description="租户 ID"),
    ) -> None:
        from core.events import get_event_bus

        # 必须先 accept 才能 close：Starlette 的 WebSocket 在未 accept 时
        # 调用 close() 会抛 RuntimeError。先握手再以 1008 (Policy Violation)
        # 关闭，便于客户端拿到错误码并显示 reason。
        await ws.accept()
        if not tenant_id:
            await ws.close(code=1008, reason="tenant_id required")
            return
        bus = get_event_bus()
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        loop = asyncio.get_running_loop()

        async def _push(event: Any) -> None:
            # 过滤 tenant：跨租户事件不推
            if getattr(event, "tenant_id", None) and event.tenant_id != tenant_id:
                return
            # 不要吞掉 WebSocketDisconnect：交给外层循环捕获以触发清理
            await ws.send_json(
                {
                    "type": "event",
                    "topic": event.topic,
                    "tenant_id": event.tenant_id,
                    "source": event.source,
                    "event_id": event.event_id,
                    "payload": event.payload,
                    "occurred_at": event.occurred_at,
                }
            )

        # 把同步 bus.subscribe 触发的 handler 投递到 asyncio.Queue
        def _enqueue(event: Any) -> None:
            def _safe_put() -> None:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # 队列已满（消费端慢/卡住）：丢弃最早事件以腾出空间，
                    # 避免无限增长并尽快恢复实时推送。
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        queue.put_nowait(event)
                    except asyncio.QueueFull:
                        logger.warning(
                            "ws 事件队列已满，丢弃事件: tenant=%s", tenant_id
                        )

            loop.call_soon_threadsafe(_safe_put)

        # event_bus.subscribe 期望 async handler；包一层 async 即可。
        async def _async_handler(event: Any) -> None:
            _enqueue(event)

        await bus.subscribe(topic, _async_handler)
        logger.info("ws 订阅: topic=%s tenant=%s", topic, tenant_id)

        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=PING_INTERVAL_SECONDS
                    )
                except TimeoutError:
                    await ws.send_json({"type": "ping"})
                    continue

                await _push(event)
        except WebSocketDisconnect:
            logger.info("ws 客户端断开: tenant=%s", tenant_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("ws 异常: %s", e)
        finally:
            try:
                await bus.unsubscribe(topic, _async_handler)
            except Exception:  # noqa: BLE001
                pass

    return router


__all__ = ["build_websocket_router"]
