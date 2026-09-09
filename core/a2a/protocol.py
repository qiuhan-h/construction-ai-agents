"""A2A 协议核心定义（版本、方法、错误码、消息帧）。

协议设计原则（与 Google A2A 思路对齐，便于后续替换 SDK）：
- JSON-RPC 2.0 风格帧：{ jsonrpc, id, method, params } / { result } / { error }
- 显式协议版本协商；版本不兼容立即失败（50004）
- 错误码统一映射到 common.error_codes（5xxx 段）
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from common.error_codes import ErrorCode, ErrorCodes

# =====================================================
# 协议常量
# =====================================================
PROTOCOL_VERSION: str = "1.0"
JSONRPC_VERSION: str = "2.0"

# 协议兼容性：主版本必须一致，次版本向后兼容
SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = ("1.0",)


# =====================================================
# 方法枚举（Agent Card 发现 / 消息发送 / 任务管理）
# =====================================================
class A2AMethod(str, Enum):
    DISCOVERY = "agent.discover"            # 获取智能体清单或指定 agent 的 Card
    SEND_MESSAGE = "agent.send_message"     # 发送消息（同步或异步触发）
    GET_TASK = "agent.get_task"             # 查询任务状态
    CANCEL_TASK = "agent.cancel_task"       # 取消任务
    LIST_TASKS = "agent.list_tasks"         # 列出任务（可选）


# =====================================================
# 错误码（与 common.error_codes 5xxx 段对齐）
# =====================================================
class A2AErrorCode:
    """A2A 错误码常量集合（与 common.error_codes 对应）。"""

    AGENT_NOT_FOUND = ErrorCodes.A2A_AGENT_NOT_FOUND
    MESSAGE_INVALID = ErrorCodes.A2A_MESSAGE_INVALID
    CALL_FAILED = ErrorCodes.A2A_CALL_FAILED
    PROTOCOL_VERSION_MISMATCH = ErrorCodes.A2A_PROTOCOL_VERSION_MISMATCH
    TASK_NOT_FOUND = ErrorCodes.A2A_TASK_NOT_FOUND
    TIMEOUT = ErrorCodes.A2A_TIMEOUT
    NETWORK_ERROR = ErrorCodes.A2A_NETWORK_ERROR


def make_error(code: ErrorCode, message: str | None = None,
               data: dict[str, Any] | None = None) -> dict[str, Any]:
    """构造 A2A JSON-RPC 标准 error 字段。"""
    payload: dict[str, Any] = {
        "code": code.code,
        "message": message or code.message,
    }
    if data:
        payload["data"] = data
    return payload


def check_protocol_version(peer_version: str | None) -> None:
    """检查对端协议版本是否兼容；不兼容则抛出异常。

    兼容规则：peer_version 主版本号必须命中 SUPPORTED_PROTOCOL_VERSIONS。
    """
    from common.exceptions import A2AProtocolVersionMismatchError  # 局部导入避免循环

    if not peer_version:
        raise A2AProtocolVersionMismatchError(
            "对端未声明协议版本",
            details={"supported": list(SUPPORTED_PROTOCOL_VERSIONS)},
        )
    # 主版本比较（"1.2" → "1"）
    peer_major = peer_version.split(".", 1)[0]
    if peer_version not in SUPPORTED_PROTOCOL_VERSIONS and not any(
        v.split(".", 1)[0] == peer_major for v in SUPPORTED_PROTOCOL_VERSIONS
    ):
        raise A2AProtocolVersionMismatchError(
            f"协议版本不兼容：peer={peer_version}",
            details={"supported": list(SUPPORTED_PROTOCOL_VERSIONS)},
        )
