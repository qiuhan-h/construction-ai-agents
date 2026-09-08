"""MCP 服务单元测试：tool/resource/prompt 注册与调用、错误处理、P3-3 最长前缀匹配。"""

from __future__ import annotations

import asyncio

import pytest

from common.exceptions import (
    MCPPromptNotFoundError,
    MCPResourceNotFoundError,
    MCPToolExecutionError,
    MCPToolNotFoundError,
)
from core.mcp.server import MCPService


def _fresh_service() -> MCPService:
    svc = MCPService()

    @svc.register_tool("echo", description="回显工具", input_schema={"type": "object"})
    async def _echo(text: str = "") -> dict:
        return {"echo": text}

    @svc.register_tool("boom", description="总是失败的工具")
    async def _boom() -> dict:
        raise RuntimeError("boom")

    @svc.register_resource("doc://f1", name="f1", description="围栏文档")
    async def _reader(uri: str = "", **kwargs) -> dict:
        return {"fence_id": "f1", "uri": uri}

    @svc.register_resource("regulation://*", name="regulations", description="规范前缀资源")
    async def _reg_reader(uri: str = "", **kwargs) -> dict:
        return {"code": uri.split("://", 1)[-1]}

    @svc.register_prompt("safety_plan", description="安全方案审查提示词")
    async def _render(project_id: str = "?") -> list:
        return [{"role": "user", "content": f"审查 {project_id}"}]

    return svc


def test_call_tool_returns_result_envelope() -> None:
    svc = _fresh_service()
    out = asyncio.run(svc.call_tool("echo", {"text": "hi"}))
    assert out["name"] == "echo"
    assert out["result"] == {"echo": "hi"}
    assert "called_at" in out


def test_list_tools_includes_registered() -> None:
    svc = _fresh_service()
    names = [t["name"] for t in svc.list_tools()]
    assert {"echo", "boom"} <= set(names)


def test_call_unknown_tool_raises() -> None:
    svc = _fresh_service()
    with pytest.raises(MCPToolNotFoundError):
        asyncio.run(svc.call_tool("not_exist"))


def test_tool_runner_error_wrapped() -> None:
    svc = _fresh_service()
    with pytest.raises(MCPToolExecutionError):
        asyncio.run(svc.call_tool("boom"))


def test_read_resource_exact_match() -> None:
    svc = _fresh_service()
    out = asyncio.run(svc.read_resource("doc://f1"))
    assert out["uri"] == "doc://f1"
    assert out["content"]["fence_id"] == "f1"


def test_read_resource_longest_prefix_match_p33() -> None:
    """P3-3 回归：regulation://GB50300/2020 应命中 regulation://* 前缀资源。"""
    svc = _fresh_service()
    out = asyncio.run(svc.read_resource("regulation://GB50300/2020"))
    assert out["content"]["code"] == "GB50300/2020"


def test_read_unknown_resource_raises() -> None:
    svc = _fresh_service()
    with pytest.raises(MCPResourceNotFoundError):
        asyncio.run(svc.read_resource("nothing://x"))


def test_render_prompt() -> None:
    svc = _fresh_service()
    out = asyncio.run(svc.render_prompt("safety_plan", {"project_id": "P-001"}))
    assert isinstance(out, dict)


def test_render_unknown_prompt_raises() -> None:
    svc = _fresh_service()
    with pytest.raises(MCPPromptNotFoundError):
        asyncio.run(svc.render_prompt("no_such_prompt"))
