"""A2A REST DTO：与 core.a2a.message / serializers 对应的 Pydantic 模型。

用途：
- FastAPI 路由层接收 / 返回 HTTP 请求体时使用（DTO 边界）；
- 与 core.a2a 内部模型解耦，避免协议改动波及 HTTP 接口；
- 字段含义与 core.a2a.message 一致，但允许 extra="allow" 以便扩展。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# =====================================================
# 消息部分（与 core.a2a.message.MessagePart 对齐）
# =====================================================
class A2AMessagePartDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(default="text", description="text | file | data")
    text: str | None = None
    file_uri: str | None = None
    data: dict[str, Any] | None = None


# =====================================================
# 消息体（HTTP 入参 DTO）
# =====================================================
class A2AMessageDTO(BaseModel):
    """A2A 消息 HTTP 入参。"""

    model_config = ConfigDict(extra="forbid")

    message_id: str | None = Field(
        default=None,
        description="消息 ID（msg_ 前缀；不填时由服务端补全）",
    )
    tenant_id: str = Field(..., description="租户 ID（多租户隔离）")
    role: str = Field(default="user", description="user | agent | system")
    parts: list[A2AMessagePartDTO] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# =====================================================
# 发送消息 请求 / 响应
# =====================================================
class A2ASendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: A2AMessageDTO = Field(..., description="要发送的消息体")
    wait: bool = Field(default=False, description="是否同步等待结果（仅小任务）")
    timeout_seconds: float | None = Field(
        default=None, ge=0.1, le=120.0,
        description="同步等待超时（秒），仅 wait=True 生效",
    )


class A2ASendMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="任务 ID（task_ 前缀）")
    state: str = Field(..., description="任务状态（pending/running/completed/failed/cancelled）")
    agent: str = Field(..., description="承接此任务的智能体名")
    response: A2AMessageDTO | None = Field(
        default=None, description="智能体返回消息（wait=True 时填充）"
    )
    artifacts: list[dict[str, Any]] = Field(
        default_factory=list, description="产物列表（图片/文件/报告等）"
    )
    error: dict[str, Any] | None = Field(
        default=None, description="失败时的错误信息"
    )


# =====================================================
# 任务查询 / 取消
# =====================================================
class A2AGetTaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    agent: str
    tenant_id: str
    state: str
    message_id: str | None = None
    error: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str
    updated_at: str


class A2ACancelTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, description="取消原因（写入任务 error）")


class A2ACancelTaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    cancelled: bool
    state: str


class A2AListTasksResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks: list[A2AGetTaskResponse] = Field(default_factory=list)


# =====================================================
# 错误响应（与 api/schemas/response_schemas.ErrorResponse 一致）
# =====================================================
class A2AErrorInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    data: dict[str, Any] | None = None


class A2AErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: str = Field(default="2.0")
    id: str | None = None
    error: A2AErrorInfo


__all__ = [
    "A2AMessagePartDTO",
    "A2AMessageDTO",
    "A2ASendMessageRequest",
    "A2ASendMessageResponse",
    "A2AGetTaskResponse",
    "A2ACancelTaskRequest",
    "A2ACancelTaskResponse",
    "A2AListTasksResponse",
    "A2AErrorInfo",
    "A2AErrorResponse",
]
