"""MQTT 客户端：订阅传感器上报 topic。

缺失 paho-mqtt 时降级为 mock 模式（用 asyncio.Queue 注入）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def _settings_mqtt() -> tuple[str, int]:
    """从 config.settings（.env 的 MQTT_BROKER / MQTT_PORT）读取；失败返回空。"""
    try:
        from config import get_settings

        s = get_settings()
        return (s.mqtt_broker or ""), int(s.mqtt_port or 1883)
    except Exception:  # noqa: BLE001
        return "", 1883


class MQTTConnector:
    """MQTT 订阅：topic = 'construct/{tenant_id}/sensors/+/+'"""

    def __init__(
        self,
        broker: str | None = None,
        port: int | None = None,
        client_id: str | None = None,
        tenant_id: str = "tnt",
    ) -> None:
        # 未显式传参 → 从 .env / Settings 读取
        if broker is None or port is None:
            cfg_broker, cfg_port = _settings_mqtt()
            broker = broker or cfg_broker or ""
            port = port or cfg_port or 1883
        self._broker = broker
        self._port = port
        self._client_id = client_id or f"site_monitor_{tenant_id}_{secrets.token_hex(4)}"
        self._handlers: dict[str, list[Callable]] = {}
        self._client: Any = None
        self._mock_queue: asyncio.Queue = asyncio.Queue()
        self._mock_mode = False
        # 未配置 Broker → 显式 mock 模式（不尝试连接 localhost）
        if not broker:
            logger.info("MQTT_BROKER 未配置；MQTT 走 mock 模式")
            self._mock_mode = True
            return
        try:
            import paho.mqtt.client as mqtt  # type: ignore[import-not-found]

            self._client = mqtt.Client(client_id=self._client_id)
            self._client.on_message = self._on_message
            self._client.reconnect_delay_set(min_delay=1, max_delay=120)
            # connect_async 非阻塞，避免 broker 不可达时 __init__ 崩溃
            self._client.connect_async(broker, port, keepalive=60)
        except ImportError:
            logger.warning("paho-mqtt 未安装；MQTT 走 mock 模式")
            self._mock_mode = True
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "MQTT 初始化失败 %s:%s: %s → mock 模式", broker, port, e
            )
            self._client = None
            self._mock_mode = True

    def subscribe(self, topic: str, handler: Callable) -> None:
        """订阅 topic；handler 签名 async def handler(payload: dict) -> None。"""
        self._handlers.setdefault(topic, []).append(handler)
        if self._client is not None:
            self._client.subscribe(topic)

    def publish(self, topic: str, payload: dict) -> None:
        if self._client is not None:
            self._client.publish(topic, json.dumps(payload, ensure_ascii=False))

    async def mock_inject(self, topic: str, payload: dict) -> None:
        """mock 模式：往队列注入测试数据。"""
        if not self._mock_mode:
            raise RuntimeError("mock_inject 只能在 mock 模式调用")
        await self._mock_queue.put((topic, payload))

    async def loop_forever(self) -> None:
        """启动循环；mock 模式从 queue 拉取，真实模式用 asyncio.to_thread 包阻塞调用。"""
        if self._mock_mode:
            while True:
                topic, payload = await self._mock_queue.get()
                for h in self._handlers.get(topic, []):
                    try:
                        await h(payload)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("mock handler 失败: %s", e)
            return
        # 真实模式：paho-mqtt 的 loop_forever 是阻塞的，放到线程避免卡 event loop
        await asyncio.to_thread(self._client.loop_forever)

    def _on_message(self, _client: Any, _userdata: Any, msg: Any) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            logger.warning("MQTT 消息解析失败 topic=%s: %s", msg.topic, e)
            return
        for h in self._handlers.get(msg.topic, []):
            # 注意：handler 签名是 async；这里需要调度到 event loop
            try:
                loop = asyncio.get_running_loop()
                if asyncio.iscoroutinefunction(h):
                    loop.create_task(h(payload))
                else:
                    h(payload)
            except RuntimeError:
                # 没有 event loop（同步上下文）；直接同步调用
                if asyncio.iscoroutinefunction(h):
                    asyncio.run(h(payload))
                else:
                    h(payload)
