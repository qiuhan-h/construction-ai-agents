"""A2A 协议单元测试：消息 / 任务状态机 / JSON-RPC 响应信封。"""

from __future__ import annotations

import pytest

from common.ids import message_id
from core.a2a import make_error_response, make_success_response
from core.a2a.message import A2AMessage, MessagePart, Task, TaskState
from core.a2a.serializers import JSONRPCError


def test_message_part_text_and_data() -> None:
    part = MessagePart(type="text", text="hello")
    assert part.type == "text"
    assert part.text == "hello"
    data_part = MessagePart(type="data", data={"k": "v"})
    assert data_part.data == {"k": "v"}


def test_a2a_message_construction() -> None:
    msg = A2AMessage(
        message_id=message_id(),
        tenant_id="tnt_a2a",
        role="user",
        parts=[MessagePart(type="text", text="审查方案")],
        metadata={"project_id": "p1"},
    )
    assert msg.tenant_id == "tnt_a2a"
    assert msg.parts[0].text == "审查方案"
    assert msg.metadata["project_id"] == "p1"


def test_task_state_transitions() -> None:
    task = Task(
        task_id="t-1",
        agent_name="safety_audit_agent",
        tenant_id="tnt_a2a",
        state=TaskState.PENDING,
    )
    # 合法迁移：pending → running → completed
    task.transition(TaskState.RUNNING)
    assert task.state == TaskState.RUNNING
    task.transition(TaskState.COMPLETED)
    assert task.state == TaskState.COMPLETED
    assert task.is_terminal() is True


def test_task_invalid_transition_raises() -> None:
    task = Task(
        task_id="t-2",
        agent_name="safety_audit_agent",
        tenant_id="tnt_a2a",
        state=TaskState.COMPLETED,
    )
    # 终态再迁移应抛错（非法状态迁移）
    with pytest.raises(Exception):  # noqa: PT011, B017
        task.transition(TaskState.RUNNING)


def test_make_success_response_envelope() -> None:
    resp = make_success_response("req-1", {"ok": True})
    assert resp.id == "req-1"
    assert resp.result == {"ok": True}
    assert resp.error is None


def test_make_error_response_envelope() -> None:
    err = JSONRPCError(code="-32603", message="boom")
    resp = make_error_response("req-2", err)
    assert resp.id == "req-2"
    assert resp.result is None
    assert resp.error is not None
    assert resp.error.code == "-32603"
    assert resp.error.message == "boom"
