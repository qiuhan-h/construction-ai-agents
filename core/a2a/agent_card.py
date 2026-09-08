"""智能体名片（Agent Card）：能力声明 + 元数据 + 端点。

A2A Discovery 流程：
  1. 客户端 GET <base_url><card_path>（默认 /agent.json）
  2. 返回 AgentCard JSON
  3. 客户端缓存（TTL 来自 config/a2a_config.yaml）
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from common.ids import new_id
from common.timeutils import to_iso, utc_now
from core.a2a.protocol import PROTOCOL_VERSION


# =====================================================
# 能力声明
# =====================================================
class Skill(BaseModel):
    """智能体的一个具体能力。"""

    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(..., description="能力 ID，在 agent 内唯一")
    name: str
    description: str
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="输入 JSON Schema 片段（可空）",
    )
    output_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="输出 JSON Schema 片段（可空）",
    )


class Capabilities(BaseModel):
    """智能体能力集合。"""

    model_config = ConfigDict(extra="forbid")

    streaming: bool = Field(default=False, description="是否支持流式输出")
    push_notifications: bool = Field(default=False, description="是否支持回调推送")
    multi_turn: bool = Field(default=True, description="是否支持多轮对话")
    async_tasks: bool = Field(default=True, description="是否支持异步任务")


# =====================================================
# Agent Card
# =====================================================
class AgentCard(BaseModel):
    """智能体名片（A2A Discovery 端点返回）。"""

    model_config = ConfigDict(extra="forbid")

    card_id: str = Field(default_factory=lambda: new_id("card"))
    name: str = Field(..., description="智能体唯一名（路由 key）")
    version: str = Field(default="1.0.0", description="智能体版本")
    description: str = Field(default="", description="智能体简介")
    protocol_version: str = Field(default=PROTOCOL_VERSION)
    url: HttpUrl | str = Field(..., description="A2A 服务基址（含协议与端口）")
    card_path: str = Field(default="/agent.json", description="Card 端点路径")
    skills: list[Skill] = Field(default_factory=list)
    capabilities: Capabilities = Field(default_factory=Capabilities)
    metadata: dict[str, Any] = Field(default_factory=dict)
    issued_at: str = Field(default_factory=lambda: to_iso(utc_now()))

    def card_url(self) -> str:
        base = str(self.url).rstrip("/")
        path = self.card_path if self.card_path.startswith("/") else f"/{self.card_path}"
        return f"{base}{path}"

    def to_public_dict(self) -> dict[str, Any]:
        """对外发布时序列化（去除敏感元数据）。"""
        data = self.model_dump(exclude={"metadata"}, exclude_none=True)
        return data
