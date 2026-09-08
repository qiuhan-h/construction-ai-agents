"""A2A JSON-RPC 帧的序列化与反序列化。

帧结构：
  请求  { jsonrpc, id, method, params }
  成功  { jsonrpc, id, result }
  错误  { jsonrpc, id, error: { code, message, data? } }

关键约束：
- 严格校验必填字段；缺失或类型不符抛 A2AMessageInvalidError；
- 协议版本字段 protocol_version 用于服务端握手；
- 不做隐式字段丢弃，extra 字段经 strict 模式抛错。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydanticValidationError

from common.exceptions import A2AMessageInvalidError
from core.a2a.message import A2AMessage
from core.a2a.protocol import JSONRPC_VERSION, PROTOCOL_VERSION


# =====================================================
# JSON-RPC 帧
# =====================================================
class JSONRPCRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: str = Field(default=JSONRPC_VERSION)
    id: str
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    protocol_version: str = Field(default=PROTOCOL_VERSION)


class JSONRPCError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    data: dict[str, Any] | None = None


class JSONRPCResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: str = Field(default=JSONRPC_VERSION)
    id: str
    result: Any | None = None
    error: JSONRPCError | None = None


# =====================================================
# params 包装：method 调用时的输入参数
# =====================================================
class SendMessageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: A2AMessage
    wait: bool = Field(default=False, description="是否同步等待结果（默认仅创建任务）")


class GetTaskParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str


class CancelTaskParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    reason: str | None = None


# =====================================================
# 编解码入口
# =====================================================
def encode_request(req: JSONRPCRequest) -> dict[str, Any]:
    """将 JSONRPCRequest 编码为 dict（用于 HTTP body）。"""
    return req.model_dump(exclude_none=True)


def decode_request(data: dict[str, Any]) -> JSONRPCRequest:
    """解析 HTTP body 为 JSONRPCRequest；非法抛 A2AMessageInvalidError。"""
    if not isinstance(data, dict):
        raise A2AMessageInvalidError(
            "A2A 帧必须是 JSON 对象",
            details={"type": type(data).__name__},
        )
    try:
        return JSONRPCRequest.model_validate(data)
    except PydanticValidationError as e:
        raise A2AMessageInvalidError(
            "A2A 请求帧字段不合法",
            details={"errors": e.errors()},
        ) from e


def encode_response(resp: JSONRPCResponse) -> dict[str, Any]:
    return resp.model_dump(exclude_none=True)


def make_success_response(req_id: str, result: Any) -> JSONRPCResponse:
    return JSONRPCResponse(id=req_id, result=result)


def make_error_response(req_id: str, error: JSONRPCError) -> JSONRPCResponse:
    return JSONRPCResponse(id=req_id, error=error)
