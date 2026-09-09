"""施工合规校验智能体的 MCP 处理器：桥接 + 业务工具。"""

from __future__ import annotations

import logging
from typing import Any

from agents.compliance_agent.outputs import ViolationRepository
from agents.compliance_agent.prompts import (
    PROMPT_ENERGY_REVIEW,
    PROMPT_FIRE_REVIEW,
    PROMPT_GREEN_REVIEW,
    PROMPT_SEISMIC_REVIEW,
)
from agents.compliance_agent.regulation_engine import (
    RegulationIndex,
    RegulationLoader,
)
from common.exceptions import AgentError, AgentParseError
from core.llm import get_prompt_manager
from core.mcp.server import (
    MCPService,
    get_mcp_service,
)

logger = logging.getLogger("agents.compliance_agent.mcp_handlers")


class ComplianceMCPHandler:
    """合规智能体的 MCP 业务处理器。"""

    def __init__(self, service: MCPService | None = None) -> None:
        self._service = service or get_mcp_service()
        self._loader = RegulationLoader()
        self._index = RegulationIndex(self._loader)

    # =========================================================
    # 资源（转发到 core.mcp.resources.regulation_resource）
    # =========================================================
    async def read_regulation(self, code: str, version: str) -> dict[str, Any]:
        uri = f"regulation://{code}/{version}"
        try:
            return await self._service.read_resource(uri)
        except Exception as e:
            raise AgentError(
                f"MCP 读取法规失败: {code}/{version}",
                details={"uri": uri, "error": str(e)},
            ) from e

    # =========================================================
    # 工具（业务语义）
    # =========================================================
    async def search_regulation(
        self, *, design_type: str, top_k: int = 10,
    ) -> dict[str, Any]:
        """按 design_type 查适用法规清单。"""
        regs = self._index.search(design_type)
        return {
            "tool": "compliance.search_regulation",
            "design_type": design_type,
            "matches": [
                {"code": r.code, "version": r.version, "name": r.name,
                 "effective_date": r.effective_date}
                for r in regs[:top_k]
            ],
        }

    async def list_violations(
        self, *, tenant_id: str, status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """按 tenant_id + 状态查违规项。首版 mock 模式。"""
        repo = ViolationRepository()
        rows = repo.list_by_tenant(tenant_id, status=status, limit=limit)
        return {
            "tool": "compliance.list_violations",
            "tenant_id": tenant_id,
            "status": status,
            "count": len(rows),
            "items": rows,
        }

    async def mark_rectified(self, violation_id: str, note: str) -> dict[str, Any]:
        """标记违规已整改（首版 mock）。"""
        repo = ViolationRepository()
        ok = repo.update_status(violation_id, "closed", note=note)
        return {
            "tool": "compliance.mark_rectified",
            "violation_id": violation_id,
            "ok": ok,
        }

    async def invoke_review(
        self, *, tenant_id: str, project_id: str, plan_id: str,
        design_doc: dict[str, Any], checks: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        """供 4c 编排器调用：触发复审流程。

        返回：调起 ComplianceAgent.handle 的元数据（实际执行由编排器完成）。
        """
        return {
            "tool": "compliance.invoke_review",
            "tenant_id": tenant_id, "project_id": project_id, "plan_id": plan_id,
            "checks": checks or {"fire": True, "seismic": True,
                                 "energy": True, "green": True},
            "design_doc_keys": list(design_doc.keys())[:20],
        }

    # =========================================================
    # 提示词（4 个合规模板）
    # =========================================================
    async def render_prompt(
        self, name: str, project: str, design_doc: dict[str, Any],
        regulations: str = "",
    ) -> dict[str, Any]:
        """渲染 compliance.* 提示词。"""
        if name not in (
            PROMPT_FIRE_REVIEW, PROMPT_SEISMIC_REVIEW,
            PROMPT_ENERGY_REVIEW, PROMPT_GREEN_REVIEW,
        ):
            raise AgentParseError(f"未知提示词: {name}")
        try:
            text = get_prompt_manager().render(
                name, project=project,
                design_doc=_summarize(design_doc),
                regulations=regulations or "（无）",
            )
        except Exception as e:
            raise AgentParseError(
                f"渲染提示词失败: {name}", details={"error": str(e)}
            ) from e
        return {
            "name": name,
            "messages": [{"role": "user", "content": text}],
        }


def _summarize(d: dict[str, Any]) -> str:
    """把 design_doc 简化为单行摘要（避免提示词模板被超长文本填满）。"""
    parts: list[str] = []
    for k, v in d.items():
        if k == "_text":
            parts.append(f"原文: {str(v)[:200]}")
        else:
            parts.append(f"{k}={v}")
    return "; ".join(parts[:15])


# =========================================================
# MCP 工具注册
# =========================================================
def register_compliance_tools(service: MCPService | None = None) -> None:
    """把 compliance 业务工具注册到 MCP 服务。"""
    svc = service or get_mcp_service()
    handler = ComplianceMCPHandler(svc)

    @svc.register_tool(
        name="compliance.search_regulation",
        description="按 design_type 查适用法规清单",
        input_schema={
            "type": "object",
            "properties": {
                "design_type": {"type": "string", "enum": [
                    "fire", "seismic", "energy", "green", "general"
                ]},
                "top_k": {"type": "integer", "default": 10},
            },
            "required": ["design_type"],
        },
    )
    async def _search(design_type: str, top_k: int = 10) -> dict[str, Any]:
        return await handler.search_regulation(design_type=design_type, top_k=top_k)

    @svc.register_tool(
        name="compliance.list_violations",
        description="按 tenant_id + 状态查违规项",
        input_schema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "status": {"type": "string"},
                "limit": {"type": "integer", "default": 100},
            },
            "required": ["tenant_id"],
        },
    )
    async def _list(tenant_id: str, status: str | None = None,
                   limit: int = 100) -> dict[str, Any]:
        return await handler.list_violations(tenant_id=tenant_id, status=status, limit=limit)

    @svc.register_tool(
        name="compliance.mark_rectified",
        description="标记违规已整改",
        input_schema={
            "type": "object",
            "properties": {
                "violation_id": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["violation_id"],
        },
    )
    async def _mark(violation_id: str, note: str = "") -> dict[str, Any]:
        return await handler.mark_rectified(violation_id, note)

    @svc.register_tool(
        name="compliance.invoke_review",
        description="复审触发（供 4c 编排器调用）",
        input_schema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "project_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "design_doc": {"type": "object"},
            },
            "required": ["tenant_id", "project_id", "plan_id", "design_doc"],
        },
    )
    async def _invoke(tenant_id: str, project_id: str, plan_id: str,
                      design_doc: dict[str, Any]) -> dict[str, Any]:
        return await handler.invoke_review(
            tenant_id=tenant_id, project_id=project_id,
            plan_id=plan_id, design_doc=design_doc,
        )


# =========================================================
# 顶层入口
# =========================================================
def install() -> ComplianceMCPHandler:
    """安装 compliance_agent 的 MCP 工具，返回 handler。"""
    register_compliance_tools()
    return ComplianceMCPHandler()


__all__ = [
    "ComplianceMCPHandler",
    "register_compliance_tools",
    "install",
]
