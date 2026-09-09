"""事件总线：发布 / 订阅接口，支持进程内异步派发与可选 Redis Stream。

设计原则：
1. 默认进程内实现（asyncio + 回调列表），无外部依赖；
2. 当 settings.redis_url 非占位时，可选启用 Redis Stream 适配器
   （阶段二仅留接口与配置位，阶段四再补真实订阅端）；
3. publish/subscribe 全部 async；handler 内部异常被捕获并日志记录，
   不会让发布者失败；
4. 主题通配符：订阅 "inspection.*" 可匹配 "inspection.completed" 等
   一类事件，订阅 "*" 接收全部事件。

注意：
- 本模块不直接 import core.llm / core.a2a / core.mcp；
- 阶段二只覆盖进程内派发；多节点 / 持久化订阅留待阶段四。
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from common.exceptions import EventPublishError, EventSubscribeError
from core.events.events import Event

logger = logging.getLogger("core.events.event_bus")

# 处理器签名：async def handler(event: Event) -> None
EventHandler = Callable[[Event], Awaitable[None]]


# =====================================================
# 事件总线
# =====================================================
class EventBus:
    """进程内异步事件总线。

    特性：
    - 主题可带通配符（fnmatch 风格：inspection.* / *.*）；
    - 同一主题可注册多个处理器，按订阅顺序串行派发；
    - 处理器抛错不影响其它处理器与发布者；
    - 提供历史缓存（可选）便于新订阅者追赶。
    """

    def __init__(
        self,
        *,
        history_size: int = 100,
        enable_history: bool = False,
    ) -> None:
        # topic_pattern -> list[handler]
        self._subs: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = asyncio.Lock()
        # 历史缓存（仅保留最近 N 条）
        self._history: list[Event] = []
        self._history_size = max(0, history_size)
        self._enable_history = enable_history
        # 用于自检 / 调试
        self.published_count = 0
        self.delivered_count = 0

    # ---------- 订阅 ----------
    async def subscribe(
        self,
        topic_pattern: str,
        handler: EventHandler,
    ) -> None:
        """注册一个订阅。

        Args:
            topic_pattern: 主题或通配符，如 "inspection.*" / "*"
            handler: async 处理器，签名为 async def handler(event: Event) -> None
        """
        if not topic_pattern or not callable(handler):
            raise EventSubscribeError(
                "订阅参数非法",
                details={"topic_pattern": topic_pattern, "handler": getattr(handler, "__name__", None)},
            )
        async with self._lock:
            self._subs[topic_pattern].append(handler)
        logger.info(
            "事件订阅: pattern=%s handler=%s",
            topic_pattern, getattr(handler, "__name__", repr(handler)),
        )

    async def unsubscribe(
        self,
        topic_pattern: str,
        handler: EventHandler,
    ) -> bool:
        """取消订阅。返回是否成功移除。"""
        async with self._lock:
            handlers = self._subs.get(topic_pattern)
            if not handlers:
                return False
            try:
                handlers.remove(handler)
            except ValueError:
                return False
            if not handlers:
                self._subs.pop(topic_pattern, None)
        return True

    def subscribers_of(self, topic: str) -> list[EventHandler]:
        """同步返回当前匹配某主题的所有处理器（用于自检 / 调试）。

        H2 修正：先做 ``list(self._subs.items())`` snapshot，避免与
        subscribe/unsubscribe 并发时 ``dictionary changed size during iteration``。
        """
        out: list[EventHandler] = []
        # 先做 snapshot 避免 dict view 在迭代中被修改
        for pattern, handlers in list(self._subs.items()):
            if _match_topic(pattern, topic):
                # handlers 也取 snapshot 防并发修改
                out.extend(list(handlers))
        return out

    # ---------- 发布 ----------
    async def publish(self, event: Event) -> None:
        """发布事件（异步派发给所有匹配订阅）。"""
        if not isinstance(event, Event):
            raise EventPublishError(
                "事件类型非法",
                details={"type": type(event).__name__},
            )
        if not event.topic:
            raise EventPublishError("事件 topic 不能为空")

        # 写入历史
        if self._enable_history:
            self._history.append(event)
            if len(self._history) > self._history_size:
                self._history = self._history[-self._history_size:]

        handlers = self.subscribers_of(event.topic)
        self.published_count += 1
        if not handlers:
            logger.debug(
                "事件无订阅者: topic=%s event_id=%s", event.topic, event.event_id
            )
            return

        # 并发派发，单个 handler 失败不影响其它
        results = await asyncio.gather(
            *(self._safe_invoke(h, event) for h in handlers),
            return_exceptions=False,
        )
        self.delivered_count += sum(1 for r in results if r)

    async def publish_many(self, events: list[Event]) -> None:
        for ev in events:
            await self.publish(ev)

    # ---------- 历史 ----------
    def history(self, topic: str | None = None) -> list[Event]:
        """返回历史事件（仅在 enable_history=True 时非空）。"""
        if not self._enable_history:
            return []
        if topic is None:
            return list(self._history)
        return [e for e in self._history if e.topic == topic]

    async def reset(self) -> None:
        """清空订阅与历史（仅测试使用；async 与 lifespan 关闭一致）。"""
        self._subs.clear()
        self._history.clear()
        self.published_count = 0
        self.delivered_count = 0

    def reset_sync(self) -> None:
        """同步重置（兼容旧调用方）。"""
        self._subs.clear()
        self._history.clear()
        self.published_count = 0
        self.delivered_count = 0

    # ---------- 内部 ----------
    async def _safe_invoke(self, handler: EventHandler, event: Event) -> bool:
        try:
            await handler(event)
            return True
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "事件处理器失败: handler=%s topic=%s err=%s",
                getattr(handler, "__name__", repr(handler)),
                event.topic,
                e,
            )
            return False


# =====================================================
# 主题匹配
# =====================================================
def _match_topic(pattern: str, topic: str) -> bool:
    """匹配订阅 pattern 与事件 topic。

    底层使用 ``fnmatch.fnmatchcase``，通配符语义与 fnmatch 一致
    （L8 修补：早期 docstring 声称 "*" 不含 "."，与 fnmatch 实际行为
    不符——fnmatch 的 "*" 匹配任意字符序列，**包含 "."**）：
      "*"          匹配所有主题（含多层，如 "a.b.c"）
      "*.*"        至少含一个 "." 的主题
      "domain.*"   以 "domain." 开头的所有主题
      精确匹配     pattern == topic
    """
    if pattern == topic:
        return True
    if not pattern:
        return False
    # fnmatch 的 * / ? 语义：* 匹配任意字符（含 "."），? 匹配单个字符
    return fnmatch.fnmatchcase(topic, pattern)


# =====================================================
# 全局单例
# =====================================================
_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """获取全局事件总线（懒加载，含历史缓存开关）。"""
    global _bus
    if _bus is None:
        # 阶段二默认开启历史缓存（容量 100），便于自检 / 排障
        _bus = EventBus(history_size=100, enable_history=True)
    return _bus


def reset_event_bus() -> None:
    """重置全局事件总线（仅测试使用）。"""
    global _bus
    _bus = None


# =====================================================
# 简化发布接口（供业务层直接调用，无需 import 单例）
# =====================================================
async def publish(topic: str, tenant_id: str, source: str, **payload: Any) -> Event:
    """便捷发布：根据 topic/tenant/source/payload 构造 Event 并发布。"""
    event = Event(
        topic=topic,
        tenant_id=tenant_id,
        source=source,
        payload=payload,
    )
    await get_event_bus().publish(event)
    return event


def publish_sync(topic: str, tenant_id: str, source: str, **payload: Any) -> None:
    """同步便捷发布：在已有 event loop 中调用 publish()。

    如果当前没有运行中的事件循环，回退为 asyncio.run()（主要用于脚本/测试）。
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(publish(topic, tenant_id, source, **payload))
        return
    loop.create_task(publish(topic, tenant_id, source, **payload))
