"""A2A 消息结构（Message / Part / Task / Artifact）。

设计要点：
- 业务数据（payload）通过 dict 透传，平台不解析其具体语义；
- 任务状态机：PENDING -> RUNNING -> COMPLETED/FAILED/CANCELLED
  非法迁移抛 TaskStateConflictError；
- 时间字段一律 UTC ISO-8601。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from common.exceptions import TaskStateConflictError
from common.timeutils import to_iso, utc_now


# =====================================================
# 任务状态机
# =====================================================
class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# 合法迁移表：from -> {to}
_ALLOWED_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.PENDING: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.RUNNING: {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}


def is_valid_transition(src: TaskState, dst: TaskState) -> bool:
    return dst in _ALLOWED_TRANSITIONS.get(src, set())


def assert_valid_transition(src: TaskState, dst: TaskState) -> None:
    if not is_valid_transition(src, dst):
        raise TaskStateConflictError(
            f"任务状态非法迁移 {src.value} -> {dst.value}",
            details={"from": src.value, "to": dst.value},
        )


# =====================================================
# 消息部分（text / file / data）
# =====================================================
class MessagePart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(default="text", description="text | file | data")
    text: str | None = None
    file_uri: str | None = None
    data: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.type}
        if self.text is not None:
            out["text"] = self.text
        if self.file_uri is not None:
            out["file_uri"] = self.file_uri
        if self.data is not None:
            out["data"] = self.data
        return out


# =====================================================
# 消息
# =====================================================
class A2AMessage(BaseModel):
    """A2A 消息体（业务载荷由 parts 列表承载）。"""

    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(..., description="消息唯一 ID（msg_ 前缀）")
    tenant_id: str = Field(..., description="租户 ID（多租户隔离）")
    role: str = Field(default="user", description="user | agent | system")
    parts: list[MessagePart] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: to_iso(utc_now()))


# =====================================================
# 任务与产物
# =====================================================
class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    type: str = Field(default="text")
    title: str | None = None
    text: str | None = None
    data: dict[str, Any] | None = None


class Task(BaseModel):
    """A2A 任务：智能体处理消息的运行实例。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="任务 ID（task_ 前缀）")
    agent_name: str = Field(..., description="承接此任务的智能体名")
    tenant_id: str
    state: TaskState = TaskState.PENDING
    message_id: str | None = None
    error: dict[str, Any] | None = None
    artifacts: list[Artifact] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: to_iso(utc_now()))
    updated_at: str = Field(default_factory=lambda: to_iso(utc_now()))

    def transition(self, new_state: TaskState, *, error: dict[str, Any] | None = None) -> None:
        """按状态机迁移；失败抛 TaskStateConflictError。"""
        assert_valid_transition(self.state, new_state)
        self.state = new_state
        if error is not None:
            self.error = error
        self.updated_at = to_iso(utc_now())

    def is_terminal(self) -> bool:
        return self.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED)
