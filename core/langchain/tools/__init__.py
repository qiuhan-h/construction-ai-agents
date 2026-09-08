"""LangChain 业务工具子包（5b.6 实做，依 shu_zhuang_tu.txt 规约）。

子包结构（对齐 ``shu_zhuang_tu.txt`` 第 193-198 行）::

    tools/
      ├── __init__.py           本文件：适配层 + 工厂注册表
      ├── calculation.py        计算工具（荷载/风险/结构校核）
      ├── document_parse.py     文档解析工具（方案/图纸/文档校验）
      ├── gis_tools.py          GIS 工具（geofence/空间监测）
      └── vector_search.py     向量检索工具（5b.2 ChromaDB 接入）

设计（5b.6 边界）：
- 本 ``__init__.py`` 只做"工具适配 + 注册表 + LangChain 接入"，
  具体业务工具实现在子模块（``calculation`` / ``document_parse`` / ``gis_tools`` / ``vector_search``）；
- 业务工具统一协议 ``BusinessTool``：``name`` / ``description`` / ``async run(**kwargs)``；
- ``MCPToolAdapter``：把 MCP 服务端注册的工具适配为 ``BusinessTool``；
  缺 MCP service 单例时降级为 ``MockTool``（返回结构化空壳，便于离线测试）；
- ``LangChainToolAdapter``：把 ``BusinessTool`` 进一步包装成 LangChain ``Tool`` / ``BaseTool``；
  缺 langchain SDK 时降级为字典结构体（``{"name","description","run"}``）。
- ``get_tool(name)``：按名取单例；``register_tool``：注册自定义工具。

不依赖：
- 不重复实现 MCP 工具业务逻辑（业务逻辑在 ``core/mcp/tools/*``）；
- 不引入额外第三方包（langchain 在调用时再 import；缺包不抛 ImportError）；
- 不接向量库（向量库在 5b.2，由 ``vector_search`` 子模块注入）。

入口约定（5b.6 推荐）::

    from core.langchain.tools import get_tool, to_langchain_tool
    biz = get_tool("calculation.load")
    lc_tool = to_langchain_tool(biz)
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from typing import Any, Callable, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# =====================================================
# 稳定业务工具白名单（与 core/mcp/tools/* 注册名一致）
# 子模块（calculation/document_parse/gis_tools/vector_search）会
# 在 import 时惰性 register 进 _REGISTRY。
# =====================================================
_BUSINESS_TOOL_NAMES: tuple[str, ...] = (
    # calculation.py 注册
    "calculation.load",
    "calculation.risk",
    "calculation.structural_check",
    # document_parse.py 注册
    "validation.plan",
    "validation.drawing",
    "validation.document",
    # gis_tools.py 注册
    "analysis.aggregate_risk",
    # vector_search.py 注册（5b.2 ChromaDB）
    "vector.search",
    "vector.upsert",
)
_VALID_NAMES: set[str] = set(_BUSINESS_TOOL_NAMES)


# =====================================================
# 协议
# =====================================================
@runtime_checkable
class BusinessTool(Protocol):
    """业务工具统一协议（与 LangChain Tool 解耦）。"""

    name: str
    description: str

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        """执行工具，返回结构化 dict。"""
        ...


_ToolFactory = Callable[[], "BusinessTool"]


# =====================================================
# Mock 实现（缺 MCP service 时降级；测试也用）
# =====================================================
class MockTool:
    """不依赖 MCP service 的兜底业务工具。

    返回结构化空壳，让上游链 / Dashboard "上线即可用"。
    真实 MCP 工具调用由 ``MCPToolAdapter`` 提供。
    """

    backend_name: str = "mock"

    def __init__(self, name: str, description: str = "") -> None:
        if name not in _VALID_NAMES and not name.startswith(("safety.", "compliance.", "site_monitor.")):
            logger.debug("MockTool 注册非白名单工具名: %s", name)
        self.name = name
        self.description = description or f"Mock tool: {name}"

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "tool": self.name,
            "backend": self.backend_name,
            "mock": True,
            "echo": dict(kwargs),
        }


# =====================================================
# MCP 工具适配器
# =====================================================
def _mcp_service_safe() -> Any | None:
    """惰性获取 MCP service 单例；不可用时返回 None。"""
    try:
        from core.mcp.server import get_mcp_service  # type: ignore
        svc = get_mcp_service()
        _ = svc.list_tools()  # 触发一次确保注册表可用
        return svc
    except Exception as e:  # noqa: BLE001
        logger.debug("MCP service 不可用，工具适配降级为 Mock: %s", e)
        return None


class MCPToolAdapter:
    """把 MCP 工具适配为 ``BusinessTool``。

    - 调用 ``MCPService.call_tool(name, args)``；
    - service 不可用 / 工具未注册 → 降级 ``MockTool``；
    - ``run`` 永不抛 ``MCPToolExecutionError``，由调用方按 ``mock`` 字段区分。
    """

    backend_name: str = "mcp"

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description or f"MCP tool: {name}"

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        svc = _mcp_service_safe()
        if svc is None:
            return await MockTool(self.name, self.description).run(**kwargs)
        try:
            result = svc.call_tool(self.name, dict(kwargs))
            # 兼容返回 coroutine / Future / 其他 awaitable；
            # asyncio.iscoroutine 仅识别 coroutine，无法识别 Future，
            # 改用 inspect.isawaitable 同时覆盖两者。
            if inspect.isawaitable(result):
                result = await result
        except Exception as e:  # noqa: BLE001
            logger.warning("MCP 工具 %s 调用失败: %s → 降级 Mock", self.name, e)
            return await MockTool(self.name, self.description).run(**kwargs)
        if isinstance(result, dict):
            result.setdefault("tool", self.name)
            result.setdefault("backend", self.backend_name)
            return result
        return {
            "ok": True,
            "tool": self.name,
            "backend": self.backend_name,
            "raw": result,
        }


# =====================================================
# LangChain 适配器（缺 SDK 时降级）
# =====================================================
def _langchain_available() -> bool:
    try:
        import langchain  # type: ignore  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


class LangChainToolAdapter:
    """把 ``BusinessTool`` 包装为 LangChain ``BaseTool``。

    缺 langchain SDK 时**绝不抛 ImportError**——返回一个最小 dict 结构体，
    让上游链 / 测试可以离线构造；属性 / 接口保持一致。

    用法（业务链 / 测试 / Streamlit）::

        from core.langchain.tools import get_tool, to_langchain_tool
        biz = get_tool("calculation.load")
        lc_tool = to_langchain_tool(biz)
        # lc_tool 可直接喂给 LangChain AgentExecutor
    """

    def __init__(self, business_tool: BusinessTool) -> None:
        self._biz = business_tool
        self.name = business_tool.name
        self.description = business_tool.description
        self._lc_tool: Any | None = None

        if not _langchain_available():
            logger.debug(
                "langchain SDK 未安装 → %s 保留为最小 dict 结构体",
                self.name,
            )
            return
        try:
            try:
                from langchain.tools import BaseTool as _LCBaseTool  # type: ignore
            except ImportError:  # pragma: no cover
                from langchain_core.tools import BaseTool as _LCBaseTool  # type: ignore
            from pydantic import BaseModel, Field  # type: ignore  # noqa: F401

            adapter = self  # 闭包绑定

            class _WrappedTool(_LCBaseTool):
                name: str = Field(default=adapter.name)
                description: str = Field(default=adapter.description)

                def _run(self, *args: Any, **kwargs: Any) -> Any:
                    """同步入口：若 event loop 已运行，用 run_coroutine_threadsafe 投递。"""
                    try:
                        loop = asyncio.get_running_loop()
                        if loop.is_running():
                            # H5 修正：不再返回伪造 echo，而是投递到运行中的 loop
                            import concurrent.futures
                            future = asyncio.run_coroutine_threadsafe(
                                adapter._biz.run(**kwargs), loop
                            )
                            return future.result(timeout=30)
                    except RuntimeError:
                        pass  # 无运行中的 loop → 走 asyncio.run
                    return asyncio.run(adapter._biz.run(**kwargs))

                async def _arun(self, *args: Any, **kwargs: Any) -> Any:
                    return await adapter._biz.run(**kwargs)

            self._lc_tool = _WrappedTool()
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "langchain Tool 构造失败: %s → fallback 最小 dict 结构体",
                e,
            )
            self._lc_tool = None

    @property
    def langchain_tool(self) -> Any:
        """返回 LangChain ``Tool`` / ``BaseTool`` 实例；缺 SDK 时为 None。"""
        return self._lc_tool

    def as_dict(self) -> dict[str, Any]:
        """最小结构体（缺 SDK / 测试 / Streamlit 离线构造用）。"""
        return {
            "name": self.name,
            "description": self.description,
            "backend": getattr(self._biz, "backend_name", "unknown"),
            "run": self._biz.run,
        }


def to_langchain_tool(business_tool: BusinessTool) -> Any:
    """便捷入口：``BusinessTool`` → LangChain Tool。

    返回类型：
    - langchain SDK 可用 → ``BaseTool`` 实例；
    - 不可用 → ``dict`` 结构体（含 ``run`` 协程方法）。
    """
    adapter = LangChainToolAdapter(business_tool)
    return adapter.langchain_tool or adapter.as_dict()


# =====================================================
# 注册表 + 工厂
# =====================================================
_REGISTRY: dict[str, _ToolFactory] = {}
_registry_lock = threading.RLock()
_default_cache: dict[str, BusinessTool] = {}


def register_tool(name: str, factory: _ToolFactory) -> None:
    """注册自定义业务工具工厂（5b.6 公共扩展点）。

    子模块（calculation/document_parse/gis_tools/vector_search）
    在 import 时调用本函数完成默认注册。
    """
    with _registry_lock:
        _REGISTRY[name] = factory
        _default_cache.pop(name, None)


def _ensure_default_registry() -> None:
    """惰性填充默认注册表（避免 import 时强依赖 MCP service）。

    触发子模块 import：子模块各自调用 ``register_tool`` 注册白名单工具。
    """
    if _REGISTRY:
        return
    with _registry_lock:
        if _REGISTRY:
            return
        # 触发子模块 import（子模块内部 register_tool）
        try:
            from core.langchain.tools import calculation as _calc  # type: ignore  # noqa: F401
            from core.langchain.tools import document_parse as _doc  # type: ignore  # noqa: F401
            from core.langchain.tools import gis_tools as _gis  # type: ignore  # noqa: F401
            from core.langchain.tools import vector_search as _vec  # type: ignore  # noqa: F401
        except ImportError as e:
            logger.warning("tools 子模块 import 失败，仅保留 MockTool 兜底: %s", e)
        # 兜底：子模块未注册的，注册 MCPToolAdapter
        for name in _BUSINESS_TOOL_NAMES:
            if name not in _REGISTRY:
                def _factory(_n: str = name) -> BusinessTool:
                    return MCPToolAdapter(_n)
                _REGISTRY[name] = _factory


def get_tool(name: str, *, use_cache: bool = True) -> BusinessTool:
    """按 name 获取业务工具。

    - 默认白名单：``calculation.*`` / ``validation.*`` / ``analysis.aggregate_risk``
      / ``vector.search`` / ``vector.upsert``；
    - 自定义工具需先 ``register_tool``；
    - 永不抛 ``ModuleNotFoundError``；MCP 不可用时降级 ``MockTool``。
    """
    _ensure_default_registry()
    with _registry_lock:
        if use_cache and name in _default_cache:
            return _default_cache[name]
        if name not in _REGISTRY:
            logger.warning("工具 '%s' 未注册 → 返回 MockTool", name)
            tool: BusinessTool = MockTool(name)
        else:
            tool = _REGISTRY[name]()
        _default_cache[name] = tool
        return tool


# 兼容 5b.6 命名习惯（business_tool 单数别名）
get_business_tool = get_tool


def get_business_tools() -> dict[str, BusinessTool]:
    """返回平台稳定的业务工具集合（含白名单 + 自定义注册）。"""
    _ensure_default_registry()
    with _registry_lock:
        return {name: get_tool(name) for name in list(_REGISTRY.keys())}


def list_tools() -> list[str]:
    """返回已注册的工具名（按字典序）。"""
    _ensure_default_registry()
    with _registry_lock:
        return sorted(_REGISTRY.keys())


def reset_default_tools() -> None:
    """重置单例 cache（测试用）。"""
    with _registry_lock:
        _default_cache.clear()


def langchain_available() -> bool:
    """暴露给业务层 / 健康检查。"""
    return _langchain_available()


__all__ = [
    "BusinessTool",
    "LangChainToolAdapter",
    "MCPToolAdapter",
    "MockTool",
    "get_business_tool",
    "get_business_tools",
    "get_tool",
    "langchain_available",
    "list_tools",
    "register_tool",
    "reset_default_tools",
    "to_langchain_tool",
]
