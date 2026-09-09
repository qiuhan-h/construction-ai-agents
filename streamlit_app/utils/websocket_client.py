"""WebSocket 事件订阅客户端。

- 同步客户端（依赖 ``websocket-client``），不依赖 asyncio；
- 通过回调把消息丢到 Streamlit ``session_state``，再由页面 ``st.rerun()`` 刷新；
- 自动断线重连（指数退避，最大 5s）；
- 4d 已规定 ``ws URL = /api/v1/ws/events?topic=*.*&tenant_id=...``，客户端把租户从 token 解析。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

try:  # 可选依赖；缺包时本类仅作 stub
    from websocket import WebSocketApp, WebSocketConnectionClosedException  # type: ignore

    _WS_AVAILABLE = True
    _WS_IMPORT_ERROR: Exception | None = None
except Exception as e:  # noqa: BLE001
    WebSocketApp = None  # type: ignore
    WebSocketConnectionClosedException = Exception  # type: ignore
    _WS_AVAILABLE = False
    _WS_IMPORT_ERROR = e


EventCallback = Callable[[dict[str, Any]], None]


class EventStreamClient:
    """事件流客户端（同步线程）。"""

    def __init__(
        self,
        ws_url: str,
        topic: str = "*.*",
        tenant_id: str = "",
        on_event: EventCallback | None = None,
        *,
        reconnect_max_delay: float = 5.0,
    ) -> None:
        self.ws_url = ws_url.rstrip("/")
        self.topic = topic
        self.tenant_id = tenant_id
        self.on_event = on_event or (lambda _e: None)
        self.reconnect_max_delay = reconnect_max_delay
        self._ws: WebSocketApp | None = None  # type: ignore[assignment]
        self._thread: threading.Thread | None = None
        self._stop_evt = threading.Event()
        self._connected = threading.Event()

    # ---------- 生命周期 ----------
    def start(self) -> bool:
        """启动后台线程；返回 True 表示已启动。"""
        if not _WS_AVAILABLE:
            logger.warning(
                "websocket-client 未安装，事件流不可用: %s", _WS_IMPORT_ERROR
            )
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run_forever, name="EventStreamClient", daemon=True
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_evt.set()
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:  # noqa: BLE001
                pass

    def is_connected(self) -> bool:
        return self._connected.is_set()

    # ---------- 内部 ----------
    def _run_forever(self) -> None:
        delay = 1.0
        while not self._stop_evt.is_set():
            try:
                self._connect_once()
            except Exception as e:  # noqa: BLE001
                logger.debug("ws 异常: %s", e)
            if self._stop_evt.is_set():
                break
            time.sleep(min(delay, self.reconnect_max_delay))
            delay = min(delay * 2.0, self.reconnect_max_delay)
        self._connected.clear()

    def _connect_once(self) -> None:
        url = f"{self.ws_url}/api/v1/ws/events?topic={self.topic}&tenant_id={self.tenant_id}"

        def _on_open(ws):  # noqa: ANN001
            self._connected.set()
            logger.info("ws 已连接: %s", url)

        def _on_message(ws, message):  # noqa: ANN001
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                return
            try:
                self.on_event(payload)
            except Exception as e:  # noqa: BLE001
                logger.warning("事件回调异常: %s", e)

        def _on_close(ws, code, msg):  # noqa: ANN001
            self._connected.clear()
            logger.info("ws 关闭: code=%s msg=%s", code, msg)

        def _on_error(ws, err):  # noqa: ANN001
            self._connected.clear()
            logger.warning("ws 错误: %s", err)

        ws = WebSocketApp(
            url,
            on_open=_on_open,
            on_message=_on_message,
            on_close=_on_close,
            on_error=_on_error,
        )
        self._ws = ws
        ws.run_forever(ping_interval=25, ping_timeout=10)


def build_ws_base_from_http(http_base: str) -> str:
    """把 http(s)://host:port 转成 ws(s)://host:port。"""
    if http_base.startswith("https://"):
        return "wss://" + http_base[len("https://"):]
    if http_base.startswith("http://"):
        return "ws://" + http_base[len("http://"):]
    return http_base


__all__ = ["EventStreamClient", "build_ws_base_from_http", "_WS_AVAILABLE"]
