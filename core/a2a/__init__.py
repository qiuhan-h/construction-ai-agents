"""core.a2a 公共 API。

公开导出：
- 协议：PROTOCOL_VERSION, A2AMethod, A2AErrorCode, make_error, check_protocol_version
- 消息：A2AMessage, MessagePart, Task, TaskState, Artifact, assert_valid_transition
- 序列化：JSONRPCRequest, JSONRPCResponse, decode_request, encode_response
- 名片：AgentCard, Skill, Capabilities
- 服务端：A2AServer, AgentRegistry, get_registry, reset_registry, build_fastapi_router
- 客户端：A2AClient, build_message
- 中间件：logging_middleware, auth_middleware, RateLimiter
"""

from core.a2a.agent_card import AgentCard, Capabilities, Skill
from core.a2a.client import A2AClient, build_message
from core.a2a.message import (
    A2AMessage,
    Artifact,
    MessagePart,
    Task,
    TaskState,
    assert_valid_transition,
    is_valid_transition,
)
from core.a2a.middleware import (
    RateLimiter,
    auth_middleware,
    logging_middleware,
    timing_middleware,
)
from core.a2a.protocol import (
    A2AErrorCode,
    A2AMethod,
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    check_protocol_version,
    make_error,
)
from core.a2a.serializers import (
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    decode_request,
    encode_response,
    make_error_response,
    make_success_response,
)
from core.a2a.server import (
    A2AAgentProtocol,
    A2AServer,
    AgentRegistry,
    build_fastapi_router,
    get_registry,
    reset_registry,
)

__all__ = [
    # 协议
    "PROTOCOL_VERSION",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "A2AMethod",
    "A2AErrorCode",
    "make_error",
    "check_protocol_version",
    # 消息
    "A2AMessage",
    "MessagePart",
    "Task",
    "TaskState",
    "Artifact",
    "is_valid_transition",
    "assert_valid_transition",
    # 序列化
    "JSONRPCRequest",
    "JSONRPCResponse",
    "JSONRPCError",
    "decode_request",
    "encode_response",
    "make_success_response",
    "make_error_response",
    # 名片
    "AgentCard",
    "Skill",
    "Capabilities",
    # 服务端
    "A2AAgentProtocol",
    "A2AServer",
    "AgentRegistry",
    "get_registry",
    "reset_registry",
    "build_fastapi_router",
    # 客户端
    "A2AClient",
    "build_message",
    # 中间件
    "logging_middleware",
    "timing_middleware",
    "auth_middleware",
    "RateLimiter",
]
