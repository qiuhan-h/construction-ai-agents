"""施工安全审核智能体的 MCP 处理器：对外暴露资源/工具/提示词桥接。

设计：
- 资源：read_resource 转发到 core.mcp.server；
- 工具：call_tool 包成"安全搜索案例 / 安全匹配法规"等业务接口；
- 提示词：render_prompt 直接复用 core.mcp.prompts.safety.audit。

注意：本文件不重复注册 MCP 项；它包装 core.mcp.server 已有能力，
为其他智能体（compliance / site_monitor / orchestrator）提供业务语义入口。
"""

from __future__ import annotations

import logging
from typing import Any

from common.exceptions import AgentError, AgentParseError
from core.mcp.server import (
    MCPService,
    get_mcp_service,
    register_prompt as _register_prompt_global,
)

from agents.safety_audit_agent.knowledge_base import (
    CaseRetriever,
    StandardLoader,
)
from agents.safety_audit_agent.prompts import (
    PROMPT_PLAN_REVIEW,
)

logger = logging.getLogger("agents.safety_audit_agent.mcp_handlers")


class SafetyAuditMCPHandler:
    """安全审核智能体的 MCP 业务处理器（包 core.mcp 现有能力）。"""

    def __init__(self, service: MCPService | None = None) -> None:
        self._service = service or get_mcp_service()
        self._cases = CaseRetriever()
        self._stds = StandardLoader()

    # =====================================================
    # 资源（转发到 core.mcp 资源）
    # =====================================================
    async def read_regulation(
        self, code: str, version: str, *, tenant_id: str = ""
    ) -> dict[str, Any]:
        """按 regulation://{code}/{version} 读法规。"""
        try:
            return await self._service.read_resource(
                f"regulation://{code}/{version}", tenant_id=tenant_id
            )
        except Exception as e:
            raise AgentError(
                f"MCP 读取法规失败: {code}/{version}",
                details={
                    "code": code,
                    "version": version,
                    "tenant_id": tenant_id,
                    "error": str(e),
                },
            ) from e

    async def read_standard(
        self, code: str, version: str, *, tenant_id: str = ""
    ) -> dict[str, Any]:
        return await self._service.read_resource(
            f"standard://{code}/{version}", tenant_id=tenant_id
        )

    # =====================================================
    # 工具（业务语义入口）
    # =====================================================
    async def search_cases(
        self,
        tenant_id: str,
        query: str,
        *,
        top_k: int = 5,
    ) -> dict[str, Any]:
        hits = await self._cases.search_cases(tenant_id, query, top_k=top_k)
        return {
            "tool": "safety.search_case",
            "query": query,
            "top_k": top_k,
            "hits": [h.to_dict() for h in hits],
        }

    async def match_regulation(
        self,
        tenant_id: str,
        query: str,
        *,
        codes: list[str] | None = None,
    ) -> dict[str, Any]:
        """按 query 匹配法规（多租户隔离）。codes 为可选限制范围。"""
        regs = await self._stds.list_regulations(tenant_id)
        if codes:
            regs = [r for r in regs if r.code in codes]
        return {
            "tool": "safety.match_regulation",
            "query": query,
            "matched": [
                {"code": r.code, "version": r.version, "name": r.name}
                for r in regs
            ],
        }

    # =====================================================
    # 提示词（包成新模板 safety.plan_review）
    # =====================================================
    async def render_plan_review_prompt(
        self,
        project: str,
        stage: str,
        hazards: str = "",
        loads: str = "",
    ) -> dict[str, Any]:
        """直接调用 core.llm.get_prompt_manager().render() 渲染。"""
        from core.llm import get_prompt_manager

        try:
            text = get_prompt_manager().render(
                PROMPT_PLAN_REVIEW,
                project=project,
                stage=stage,
                hazards=hazards or "（无）",
                loads=loads or "（无）",
            )
        except Exception as e:
            raise AgentParseError(
                "渲染 plan_review 提示词失败",
                details={"error": str(e)},
            ) from e
        return {
            "name": PROMPT_PLAN_REVIEW,
            "messages": [{"role": "user", "content": text}],
        }


# =====================================================
# MCP 工具注册（装饰器调用）
# =====================================================
def register_safety_tools(service: MCPService | None = None) -> None:
    """把 safety_audit_agent 业务工具注册到 MCP 服务。"""
    svc = service or get_mcp_service()
    handler = SafetyAuditMCPHandler(svc)

    @svc.register_tool(
        name="safety.search_case",
        description="在知识库中按相似度检索施工事故案例",
        input_schema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5},
            },
            "required": ["tenant_id", "query"],
        },
    )
    async def _search_case(tenant_id: str, query: str, top_k: int = 5) -> dict[str, Any]:
        return await handler.search_cases(tenant_id, query, top_k=top_k)

    @svc.register_tool(
        name="safety.match_regulation",
        description="按关键字匹配租户可用的法规清单",
        input_schema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "query": {"type": "string"},
                "codes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["tenant_id", "query"],
        },
    )
    async def _match_regulation(
        tenant_id: str, query: str, codes: list[str] | None = None
    ) -> dict[str, Any]:
        return await handler.match_regulation(tenant_id, query, codes=codes)


# =====================================================
# 顶层工具
# =====================================================
def install() -> SafetyAuditMCPHandler:
    """安装 safety_audit_agent 的 MCP 工具，返回 handler。"""
    register_safety_tools()
    return SafetyAuditMCPHandler()


__all__ = [
    "SafetyAuditMCPHandler",
    "register_safety_tools",
    "install",
]
