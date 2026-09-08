"""Streamlit session_state 统一封装。

约定：
- key 前缀 ``caai_``（construction-ai-agents-）避免与第三方组件冲突；
- ``init_state()`` 幂等可重复调用；
- ``get_state()`` 返回 dict-like 代理，便于 ``state["token"]`` / ``state.token``。
"""

from __future__ import annotations

import threading
from typing import Any

try:
    import streamlit as st  # type: ignore
except Exception:  # noqa: BLE001
    # 让 utils 在没有 streamlit 的环境（如 CI 单元测试）也能 import
    st = None  # type: ignore[assignment]


DEFAULTS: dict[str, Any] = {
    "caai_tenant_id": "tnt_demo",
    "caai_user_id": "admin",
    "caai_token": "dev-tnt_demo-admin",
    "caai_api_base": "http://127.0.0.1:8000",
    "caai_ws_topic": "*.*",
    "caai_timeline": [],            # list[dict] 实时事件
    "caai_timeline_max": 200,       # 最多保留条数
    "caai_last_trigger_run_id": None,
    "caai_last_error": None,
    "caai_event_client": None,      # EventStreamClient 懒缓存
    "caai_active_page": "04_dashboard",
    "caai_selected_wf": None,
    "caai_active_run_id": None,
}

_init_lock = threading.Lock()


def init_state(force: bool = False) -> None:
    """初始化默认 key；force=True 时重置为默认（用于"清空"按钮）。"""
    if st is None:
        return
    with _init_lock:
        for k, v in DEFAULTS.items():
            if force or k not in st.session_state:
                st.session_state[k] = v


class StateManager:
    """session_state 的轻量代理。"""

    def __init__(self) -> None:
        # 触发一次初始化（幂等）
        init_state(force=False)

    # ---------- 基础 ----------
    def _get(self, key: str, default: Any = None) -> Any:
        if st is None:
            return DEFAULTS.get(key, default)
        # 必须尊重 default 参数：session_state 未初始化 / 不在
        # ScriptRunContext 时直接 [key] 会抛 KeyError，且 default 形同虚设。
        try:
            if key in st.session_state:
                return st.session_state[key]
        except Exception:  # noqa: BLE001
            pass
        # 未设置时退到 DEFAULTS（init_state 未跑过 / 跨 ScriptRunContext）
        if key in DEFAULTS:
            return DEFAULTS[key]
        return default

    def _set(self, key: str, value: Any) -> None:
        if st is not None:
            st.session_state[key] = value

    # ---------- 字段访问 ----------
    @property
    def tenant_id(self) -> str:
        return self._get("caai_tenant_id")

    @tenant_id.setter
    def tenant_id(self, v: str) -> None:
        self._set("caai_tenant_id", v)
        # 同步 token 提示
        if self._get("caai_token", "").startswith("dev-"):
            self.token = f"dev-{v}-{self.user_id}"

    @property
    def user_id(self) -> str:
        return self._get("caai_user_id")

    @user_id.setter
    def user_id(self, v: str) -> None:
        self._set("caai_user_id", v)
        if self._get("caai_token", "").startswith("dev-"):
            self.token = f"dev-{self.tenant_id}-{v}"

    @property
    def token(self) -> str:
        return self._get("caai_token")

    @token.setter
    def token(self, v: str) -> None:
        self._set("caai_token", v)

    @property
    def api_base(self) -> str:
        return self._get("caai_api_base")

    @api_base.setter
    def api_base(self, v: str) -> None:
        self._set("caai_api_base", v.rstrip("/"))

    @property
    def ws_topic(self) -> str:
        return self._get("caai_ws_topic")

    @ws_topic.setter
    def ws_topic(self, v: str) -> None:
        self._set("caai_ws_topic", v or "*.*")

    # ---------- 实时事件缓冲 ----------
    def push_event(self, event: dict[str, Any]) -> None:
        buf = list(self._get("caai_timeline") or [])
        buf.insert(0, event)
        max_n = int(self._get("caai_timeline_max") or 200)
        if len(buf) > max_n:
            buf = buf[:max_n]
        self._set("caai_timeline", buf)

    def clear_events(self) -> None:
        self._set("caai_timeline", [])

    def events(self) -> list[dict[str, Any]]:
        return list(self._get("caai_timeline") or [])

    # ---------- last run ----------
    @property
    def last_trigger_run_id(self) -> str | None:
        return self._get("caai_last_trigger_run_id")

    @last_trigger_run_id.setter
    def last_trigger_run_id(self, v: str | None) -> None:
        self._set("caai_last_trigger_run_id", v)

    # ---------- 错误提示 ----------
    @property
    def last_error(self) -> str | None:
        return self._get("caai_last_error")

    @last_error.setter
    def last_error(self, v: str | None) -> None:
        self._set("caai_last_error", v)

    def clear_error(self) -> None:
        self.last_error = None


def get_state() -> StateManager:
    return StateManager()


__all__ = ["StateManager", "get_state", "init_state", "DEFAULTS"]
