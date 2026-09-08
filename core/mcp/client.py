"""MCP 客户端：通过 HTTP 调用对端 MCP 服务。

使用方式：
    from core.mcp.client import MCPClient
    client = MCPClient(base_url="http://10.0.0.10:9201")
    tools = await client.list_tools()
    out = await client.call_tool("calculation.load", {"plan_id": "plan_x"})

设计要点：
- 异步 httpx；失败按 4xx/5xx/超时映射到 MCPError 子类；
- 6xxx 错误码透传，方便上层精确处理。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from common.exceptions import (
    A2ANetworkError,
    MCPError,
    MCPPromptNotFoundError,
    MCPProtocolVersionMismatchError,
    MCPResourceNotFoundError,
    MCPToolExecutionError,
    MCPToolNotFoundError,
)
from common.ids import event_id
from common.timeutils import to_iso, utc_now
from core.mcp.server import JSONRPC_VERSION, MCP_PROTOCOL_VERSION

logger = logging.getLogger("core.mcp.client")


class MCPClient:
    """MCP HTTP 客户端。"""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> "MCPClient":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    # ---------- 公共方法 ----------
    async def list_resources(self, prefix: str | None = None) -> list[dict[str, Any]]:
        return (await self._call("resources/list", {"prefix": prefix} if prefix else {})).get("resources", [])

    async def read_resource(self, uri: str, **kwargs: Any) -> dict[str, Any]:
        params: dict[str, Any] = {"uri": uri}
        params.update(kwargs)
        return await self._call("resources/read", params)

    async def list_tools(self) -> list[dict[str, Any]]:
        return (await self._call("tools/list", {})).get("tools", [])

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._call("tools/call", {"name": name, "arguments": arguments or {}})

    async def list_prompts(self) -> list[dict[str, Any]]:
        return (await self._call("prompts/list", {})).get("prompts", [])

    async def render_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._call("prompts/get", {"name": name, "arguments": arguments or {}})

    # ---------- 内部 ----------
    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
            self._owns_client = True
        return self._client

    async def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/mcp"
        body = {
            "jsonrpc": JSONRPC_VERSION,
            "id": event_id(),
            "method": method,
            "params": params,
            "protocol_version": MCP_PROTOCOL_VERSION,
        }
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            client = self._ensure_client()
            try:
                resp = await client.post(url, json=body)
            except httpx.TimeoutException as e:
                last_exc = MCPError(f"MCP 调用超时: {method}", details={"method": method})
                logger.warning("MCP 超时 attempt=%d method=%s", attempt, method)
            except httpx.HTTPError as e:
                last_exc = A2ANetworkError(f"MCP 网络错误: {e!s}")
                logger.warning("MCP 网络错误 attempt=%d method=%s err=%s", attempt, method, e)
            else:
                return self._parse_response(resp, method)

            if attempt < self.max_retries:
                await asyncio.sleep(self.backoff_seconds * (attempt + 1))

        assert last_exc is not None
        raise last_exc

    def _parse_response(self, resp: httpx.Response, method: str) -> dict[str, Any]:
        try:
            data = resp.json()
        except Exception as e:
            raise MCPError(
                f"MCP 响应非 JSON: status={resp.status_code}",
                details={"method": method, "status": resp.status_code, "text": resp.text[:200]},
            ) from e
        if resp.status_code >= 500:
            raise MCPError(
                f"MCP 5xx: {resp.status_code}",
                details={"method": method, "body": data},
            )
        if resp.status_code >= 400:
            err = data.get("error") if isinstance(data, dict) else None
            if err:
                self._raise_for_error(err)
            raise MCPError(
                f"MCP 4xx: {resp.status_code}",
                details={"method": method, "status": resp.status_code, "body": data},
            )
        if isinstance(data, dict) and data.get("error"):
            self._raise_for_error(data["error"])
        if not isinstance(data, dict):
            return {"result": data}
        return data.get("result", {})

    def _raise_for_error(self, err: dict[str, Any]) -> None:
        code = str(err.get("code", ""))
        message = err.get("message", "MCP 错误")
        data = err.get("data") or {}
        if code == "60001":
            raise MCPResourceNotFoundError(message, details=data)
        if code == "60002":
            raise MCPToolNotFoundError(message, details=data)
        if code == "60003":
            raise MCPToolExecutionError(message, details=data)
        if code == "60004":
            raise MCPProtocolVersionMismatchError(message, details=data)
        if code == "60005":
            raise MCPPromptNotFoundError(message, details=data)
        raise MCPError(message, details={**data, "code": code})


# =====================================================
# 便捷工具
# =====================================================
def ping_info() -> dict[str, Any]:
    """用于健康检查/握手。"""
    return {
        "protocol_version": MCP_PROTOCOL_VERSION,
        "ts": to_iso(utc_now()),
    }
