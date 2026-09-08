"""智能体元数据 / 列表 / 详情 DTO。

用途：
- /agents 列表 / 详情接口的请求与响应模型；
- /agents/{name}/card 端点（Agent Card）的简化版本；
- 阶段二仅做"只读元数据"展示，注册 / 反注册留到阶段四管理面。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# =====================================================
# Skill DTO（与 core.a2a.agent_card.Skill 字段一致）
# =====================================================
class AgentSkillDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)


# =====================================================
# Capabilities DTO
# =====================================================
class AgentCapabilitiesDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    streaming: bool = False
    push_notifications: bool = False
    multi_turn: bool = True
    async_tasks: bool = True


# =====================================================
# Agent Card DTO（HTTP 层）
# =====================================================
class AgentCardDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card_id: str
    name: str
    version: str
    description: str = ""
    protocol_version: str
    url: str
    card_path: str = "/agent.json"
    skills: list[AgentSkillDTO] = Field(default_factory=list)
    capabilities: AgentCapabilitiesDTO = Field(default_factory=AgentCapabilitiesDTO)
    issued_at: str


# =====================================================
# 智能体列表 / 详情
# =====================================================
class AgentSummary(BaseModel):
    """智能体简要元信息（列表用）。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    description: str
    protocol_version: str
    skill_count: int = 0
    capabilities: AgentCapabilitiesDTO = Field(default_factory=AgentCapabilitiesDTO)
    is_business: bool = Field(default=True, description="是否为业务智能体")


class AgentDetail(AgentSummary):
    """智能体详情（含 Card 全文）。"""

    card: AgentCardDTO
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agents: list[AgentSummary] = Field(default_factory=list)
    total: int = 0


# =====================================================
# 健康探活（/agents/{name}/health）
# =====================================================
class AgentHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    healthy: bool
    version: str
    protocol_version: str
    tenant_id: str | None = None
    message: str | None = None


__all__ = [
    "AgentSkillDTO",
    "AgentCapabilitiesDTO",
    "AgentCardDTO",
    "AgentSummary",
    "AgentDetail",
    "AgentListResponse",
    "AgentHealthResponse",
]
