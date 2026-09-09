"""MCP 服务端：注册表 + JSON-RPC 处理器 + FastAPI 路由。

核心能力：
- 资源（Resource）：通过 URI 寻址的只读数据（regulation://、standard://、case://）
- 工具（Tool）：可调用的无副作用函数（load_calculator、validate_plan 等）
- 提示词（Prompt）：可参数化的模板（safety_prompts）

所有注册项由装饰器完成；MCPServer 处理 JSON-RPC 2.0 over HTTP/SSE 入口。
阶段二只暴露 HTTP 端点；SSE 流式输出阶段四补。
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from common.exceptions import (
    AppException,
    MCPPromptNotFoundError,
    MCPResourceNotFoundError,
    MCPToolExecutionError,
    MCPToolNotFoundError,
)
from common.ids import event_id
from common.timeutils import to_iso, utc_now

logger = logging.getLogger("core.mcp.server")

MCP_PROTOCOL_VERSION: str = "1.0"
JSONRPC_VERSION: str = "2.0"


# =====================================================
# 资源 / 工具 / 提示词描述
# =====================================================
@dataclass
class ResourceDescriptor:
    uri: str
    name: str
    description: str = ""
    mime_type: str = "text/plain"
    reader: Callable[..., Awaitable[Any]] | None = None
    lister: Callable[..., Awaitable[list[dict[str, Any]]]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolDescriptor:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    runner: Callable[..., Awaitable[Any]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptDescriptor:
    name: str
    description: str = ""
    arguments: list[dict[str, Any]] = field(default_factory=list)
    renderer: Callable[..., Awaitable[Any]] | None = None


# =====================================================
# MCPService：注册表 + 路由执行
# =====================================================
class MCPService:
    """MCP 注册中心 + 处理器。"""

    def __init__(self) -> None:
        self._resources: dict[str, ResourceDescriptor] = {}
        self._tools: dict[str, ToolDescriptor] = {}
        self._prompts: dict[str, PromptDescriptor] = {}
        self._lock = asyncio.Lock()

    # ---------- 资源 ----------
    def register_resource(
        self,
        uri: str,
        *,
        name: str,
        description: str = "",
        mime_type: str = "text/plain",
        metadata: dict[str, Any] | None = None,
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
            self._resources[uri] = ResourceDescriptor(
                uri=uri, name=name, description=description,
                mime_type=mime_type, reader=fn, metadata=metadata or {},
            )
            logger.info("MCP 注册资源: %s -> %s", uri, fn.__name__)
            return fn
        return decorator

    def add_resource(self, desc: ResourceDescriptor) -> None:
        self._resources[desc.uri] = desc

    # ---------- 工具 ----------
    def register_tool(
        self,
        name: str,
        *,
        description: str = "",
        input_schema: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
            schema = input_schema or _infer_input_schema(fn)
            self._tools[name] = ToolDescriptor(
                name=name, description=description, input_schema=schema,
                runner=fn, metadata=metadata or {},
            )
            logger.info("MCP 注册工具: %s -> %s", name, fn.__name__)
            return fn
        return decorator

    def add_tool(self, desc: ToolDescriptor) -> None:
        self._tools[desc.name] = desc

    # ---------- 提示词 ----------
    def register_prompt(
        self,
        name: str,
        *,
        description: str = "",
        arguments: list[dict[str, Any]] | None = None,
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
            self._prompts[name] = PromptDescriptor(
                name=name, description=description,
                arguments=arguments or [], renderer=fn,
            )
            logger.info("MCP 注册提示词: %s -> %s", name, fn.__name__)
            return fn
        return decorator

    def add_prompt(self, desc: PromptDescriptor) -> None:
        self._prompts[desc.name] = desc

    # ---------- 列表与读取 ----------
    def list_resources(self, prefix: str | None = None) -> list[dict[str, Any]]:
        out = []
        for uri, r in self._resources.items():
            if prefix and not uri.startswith(prefix):
                continue
            out.append({
                "uri": uri,
                "name": r.name,
                "description": r.description,
                "mimeType": r.mime_type,
            })
        return out

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.input_schema,
            }
            for t in self._tools.values()
        ]

    def list_prompts(self) -> list[dict[str, Any]]:
        return [
            {
                "name": p.name,
                "description": p.description,
                "arguments": p.arguments,
            }
            for p in self._prompts.values()
        ]

    async def read_resource(self, uri: str, **kwargs: Any) -> dict[str, Any]:
        # 1) 精确匹配（如 regulation://_list）
        desc = self._resources.get(uri)
        # 2) 若未命中，尝试最长前缀匹配（如 regulation://* 匹配 regulation://GB50300/2020）
        if desc is None:
            best_uri: str | None = None
            best_len = -1
            for reg_uri, _reg_desc in self._resources.items():
                if reg_uri.endswith("*"):
                    prefix = reg_uri[:-1]
                    if uri.startswith(prefix) and len(prefix) > best_len:
                        best_uri = reg_uri
                        best_len = len(prefix)
            if best_uri is not None:
                desc = self._resources[best_uri]
        if desc is None or desc.reader is None:
            raise MCPResourceNotFoundError(
                f"MCP 资源不存在: {uri}", details={"uri": uri}
            )
        try:
            content = await desc.reader(uri=uri, **kwargs)
        except AppException:
            raise
        except Exception as e:
            raise MCPResourceNotFoundError(
                f"MCP 资源读取失败: {uri}",
                details={"uri": uri, "error": str(e)},
            ) from e
        return {
            "uri": uri,
            "mimeType": desc.mime_type,
            "content": content,
        }

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        desc = self._tools.get(name)
        if desc is None or desc.runner is None:
            raise MCPToolNotFoundError(
                f"MCP 工具不存在: {name}", details={"name": name}
            )
        try:
            result = await desc.runner(**(arguments or {}))
        except AppException:
            raise
        except Exception as e:
            logger.exception("MCP 工具执行失败: %s", name)
            raise MCPToolExecutionError(
                f"MCP 工具执行失败: {name}",
                details={"name": name, "error": str(e)},
            ) from e
        return {
            "name": name,
            "result": result,
            "called_at": to_iso(utc_now()),
            "event_id": event_id(),
        }

    async def render_prompt(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        desc = self._prompts.get(name)
        if desc is None or desc.renderer is None:
            raise MCPPromptNotFoundError(
                f"MCP 提示词模板不存在: {name}", details={"name": name}
            )
        try:
            content = await desc.renderer(**(arguments or {}))
        except AppException:
            raise
        except Exception as e:
            raise MCPToolExecutionError(
                f"MCP 提示词渲染失败: {name}",
                details={"name": name, "error": str(e)},
            ) from e
        return {"name": name, "content": content}


# =====================================================
# 全局单例
# =====================================================
_service: MCPService | None = None


def get_mcp_service() -> MCPService:
    global _service
    if _service is None:
        _service = MCPService()
        # 触发资源/工具/提示词模块自注册
        _bootstrap_default_registry(_service)
    return _service


def reset_mcp_service() -> None:
    """重置单例（仅测试使用）。"""
    global _service
    _service = None


def _bootstrap_default_registry(service: MCPService) -> None:
    """加载并执行 resources / tools / prompts 三个子包的顶层模块，
    让它们的 @register_* 装饰器生效。"""
    from core.mcp.prompts import safety_prompts  # noqa: F401
    from core.mcp.resources import case_resource, regulation_resource, standard_resource  # noqa: F401
    from core.mcp.tools import analysis_tools, calculation_tools, validation_tools  # noqa: F401


# =====================================================
# 顶层薄封装
# =====================================================
def register_resource(*args: Any, **kwargs: Any) -> Callable[..., Any]:
    return get_mcp_service().register_resource(*args, **kwargs)


def register_tool(*args: Any, **kwargs: Any) -> Callable[..., Any]:
    return get_mcp_service().register_tool(*args, **kwargs)


def register_prompt(*args: Any, **kwargs: Any) -> Callable[..., Any]:
    return get_mcp_service().register_prompt(*args, **kwargs)


# =====================================================
# JSON-RPC 处理器（与 A2A 同形态，便于客户端复用）
# =====================================================
class MCPServer:
    """MCP JSON-RPC 处理器（无 HTTP 依赖，单元测试可用）。"""

    def __init__(self, service: MCPService | None = None) -> None:
        self.service = service or get_mcp_service()

    async def handle_raw(self, body: dict[str, Any]) -> dict[str, Any]:
        """处理一条 JSON-RPC 帧，返回响应 dict。"""
        jsonrpc = body.get("jsonrpc", JSONRPC_VERSION)
        req_id = str(body.get("id", "0"))
        method = body.get("method")
        params = body.get("params") or {}

        if not method:
            return _err(req_id, -32600, "Invalid Request: missing method")

        try:
            if method == "resources/list":
                result = {"resources": self.service.list_resources(params.get("prefix"))}
            elif method == "resources/read":
                # 显式校验必填参数 uri，避免 KeyError 被外层 except Exception
                # 吞成 -32603 Internal error（应返回 -32602 Invalid params）。
                if "uri" not in params:
                    return _err(req_id, -32602, "Invalid params: missing 'uri'")
                result = await self.service.read_resource(
                    params["uri"], **{k: v for k, v in params.items() if k != "uri"}
                )
            elif method == "tools/list":
                result = {"tools": self.service.list_tools()}
            elif method == "tools/call":
                # 同上：显式校验 name，避免 KeyError 被吞成 -32603。
                if "name" not in params:
                    return _err(req_id, -32602, "Invalid params: missing 'name'")
                result = await self.service.call_tool(
                    params["name"], params.get("arguments")
                )
            elif method == "prompts/list":
                result = {"prompts": self.service.list_prompts()}
            elif method == "prompts/get":
                # 同上：显式校验 name。
                if "name" not in params:
                    return _err(req_id, -32602, "Invalid params: missing 'name'")
                result = await self.service.render_prompt(
                    params["name"], params.get("arguments")
                )
            else:
                return _err(req_id, -32601, f"Method not found: {method}")
        except AppException as e:
            payload = e.to_dict()
            # JSON-RPC 规范要求 error.code 必须为整数；AppException.code 是
            # 字符串（如 "A2A_CALL_FAILED"），与 _err() 的 int code 类型不一致。
            # 统一映射为 JSON-RPC 保留的 server error 段（-32000 ~ -32099），
            # 原字符串 error_code 放入 data 以便排障。
            return {
                "jsonrpc": jsonrpc, "id": req_id,
                "error": {
                    "code": -32000,
                    "message": payload["message"],
                    "data": {
                        "error_code": payload["code"],
                        "details": payload.get("details"),
                    },
                },
            }
        except Exception as e:
            logger.exception("MCP 处理器失败: %s", method)
            return _err(req_id, -32603, f"Internal error: {e!s}")

        return {"jsonrpc": jsonrpc, "id": req_id, "result": result}


def _err(req_id: str, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "error": {"code": code, "message": message}}


def _infer_input_schema(fn: Callable[..., Any]) -> dict[str, Any]:
    """根据函数签名推导简单 JSON Schema（首版）。"""
    sig = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, p in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        ann = p.annotation
        schema: dict[str, Any] = {}
        if ann in (str, int, float, bool):
            schema["type"] = {str: "string", int: "integer", float: "number", bool: "boolean"}[ann]
        elif ann is list or ann is dict:
            schema["type"] = "object" if ann is dict else "array"
        else:
            schema["type"] = "string"  # 保守默认
        properties[name] = schema
        if p.default is inspect.Parameter.empty:
            required.append(name)
    out: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        out["required"] = required
    return out


# =====================================================
# FastAPI 路由
# =====================================================
def build_fastapi_router():
    """构造 MCP FastAPI 路由：POST /mcp 为 JSON-RPC 端点。"""
    try:
        from fastapi import APIRouter, Request
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("FastAPI 未安装，无法构建 MCP 路由") from e

    router = APIRouter()
    server = MCPServer()

    @router.post("")
    @router.post("/")
    async def mcp_endpoint(request: Request) -> dict[str, Any]:
        body = await request.json()
        return await server.handle_raw(body)

    @router.get("/resources")
    async def list_resources(prefix: str | None = None) -> dict[str, Any]:
        return {"resources": server.service.list_resources(prefix)}

    @router.get("/tools")
    async def list_tools() -> dict[str, Any]:
        return {"tools": server.service.list_tools()}

    @router.get("/prompts")
    async def list_prompts() -> dict[str, Any]:
        return {"prompts": server.service.list_prompts()}

    return router
