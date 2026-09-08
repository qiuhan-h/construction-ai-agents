"""pytest 共享配置与 fixture。

职责：
1. 把项目根目录加入 ``sys.path`` / ``PYTHONPATH``，确保 ``agents`` / ``core`` /
   ``common`` / ``models`` / ``api`` 等平铺包可被测试直接 import；
2. 在 ``pytest-asyncio`` 可用时，强制 ``asyncio_mode = auto``（与
   ``pyproject.toml`` 保持一致，避免 conftest 单独被加载时丢失该配置）；
3. 提供常用 mock fixture：鉴权上下文 / 事件总线 / 临时目录 / httpx mock。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

# =====================================================
# PYTHONPATH：把 construction-ai-agents 根目录加到搜索路径
# 文件路径：tests/conftest.py → parents[0] = tests/  parents[1] = 项目根
# =====================================================
PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ROOT_STR = str(PROJECT_ROOT)

if _ROOT_STR not in sys.path:
    sys.path.insert(0, _ROOT_STR)

# 让子进程也能继承到项目根
_EXISTING_PYTHONPATH = os.environ.get("PYTHONPATH", "")
if _ROOT_STR not in _EXISTING_PYTHONPATH.split(os.pathsep):
    os.environ["PYTHONPATH"] = (
        _ROOT_STR if not _EXISTING_PYTHONPATH
        else f"{_ROOT_STR}{os.pathsep}{_EXISTING_PYTHONPATH}"
    )


# =====================================================
# pytest 配置钩子
# =====================================================
def pytest_configure(config: pytest.Config) -> None:
    """在 ``pytest-asyncio`` 可用时显式写入 ``asyncio_mode = auto``。

    ``pyproject.toml`` 已声明该值；这里再次写入是为了让 conftest 在脱离
    pyproject 上下文（例如被 IDE 单独加载）时仍生效。``addinivalue_line``
    会幂等叠加，不会覆盖既有配置导致冲突。
    """
    try:
        import pytest_asyncio  # noqa: F401
    except ImportError:
        return
    config.addinivalue_line("asyncio_mode", "auto")


# =====================================================
# Fixture：mock 鉴权上下文
# =====================================================
@pytest.fixture()
def auth_context():
    """返回一个具备管理员 scope 的 ``AuthContext`` mock 实例。

    用例可通过 ``set_auth_override(auth_context)`` 注入到 FastAPI 依赖链中，
    也可直接断言其字段。
    """
    from api.dependencies.auth import AuthContext

    return AuthContext(
        tenant_id="tnt_test",
        user_id="user_test",
        scopes=["*"],
    )


@pytest.fixture()
def auth_override(auth_context):
    """把 ``auth_context`` 注入到全局 override，用例结束后自动复位。

    适合需要走 ``get_auth_context`` 依赖的 FastAPI 路由测试。
    """
    from api.dependencies.auth import reset_auth_state, set_auth_override

    set_auth_override(auth_context)
    yield auth_context
    reset_auth_state()


# =====================================================
# Fixture：mock 事件总线
# =====================================================
@pytest.fixture()
def event_bus():
    """提供一个隔离的全局 ``EventBus``，用例前后均重置。

    ``core.events`` 采用模块级单例 bus，直接复用会让历史订阅 / 计数器
    在用例间串扰；这里在 yield 前后都调用 ``reset_event_bus()`` 以保证隔离。
    """
    from core.events import get_event_bus, reset_event_bus

    reset_event_bus()
    bus = get_event_bus()
    yield bus
    reset_event_bus()


# =====================================================
# Fixture：临时目录
# =====================================================
@pytest.fixture()
def tmp_project_dir(tmp_path: Path) -> Path:
    """返回一个临时目录 Path（基于 pytest 内建 ``tmp_path``）。

    与 ``tmp_path`` 的区别在于命名更直观，便于在用例中表达「项目工作目录」
    语义（例如让 agent 把产物写到该目录下）。
    """
    return tmp_path


# =====================================================
# Fixture：httpx mock
# =====================================================
@pytest.fixture()
def httpx_mock():
    """httpx HTTP mock fixture。

    优先使用 ``respx``（功能更全，支持路由匹配）；缺失时降级为
    ``httpx.MockTransport``，调用方通过设置 ``httpx_mock.handler`` 自定义响应。

    用法（respx 可用时）::

        def test_x(httpx_mock):
            httpx_mock.get("https://api/").respond(200, json={"ok": 1})
            r = httpx.get("https://api/")
            assert r.json() == {"ok": 1}

    用法（降级 MockTransport）::

        def test_x(httpx_mock):
            def handler(request):
                return httpx.Response(200, json={"ok": 1})
            httpx_mock.set_handler(handler)
            r = httpx.Client(transport=httpx_mock.transport).get("https://api/")
            assert r.json() == {"ok": 1}
    """
    try:
        import respx

        with respx.mock(assert_all_called=False) as mock:
            yield mock
        return
    except ImportError:
        pass

    # 降级实现：基于 httpx.MockTransport（httpx 自带，无需额外依赖）
    import httpx

    class _HttpxMockFallback:
        def __init__(self) -> None:
            def _default_handler(request: httpx.Request) -> httpx.Response:
                return httpx.Response(
                    status_code=404,
                    json={"error": "no handler set", "url": str(request.url)},
                )

            self._handler = _default_handler
            self.transport = httpx.MockTransport(self._handler)

        def set_handler(self, fn) -> None:
            """设置响应处理函数 ``fn(request) -> httpx.Response``。"""
            self._handler = fn
            self.transport = httpx.MockTransport(self._handler)

    yield _HttpxMockFallback()
