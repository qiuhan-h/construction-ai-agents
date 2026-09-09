"""core.mcp 顶层公共 API。

公开导出：
- 服务端：MCPServer, MCPService, get_mcp_service, build_fastapi_router
- 客户端：MCPClient
- 资源/工具/提示词注册器：register_resource, register_tool, register_prompt
- 错误异常：MCPError, MCPResourceNotFoundError, MCPToolNotFoundError, MCPToolExecutionError,
  MCPProtocolVersionMismatchError, MCPPromptNotFoundError
"""

from common.exceptions import (
    MCPError,
    MCPPromptNotFoundError,
    MCPProtocolVersionMismatchError,
    MCPResourceNotFoundError,
    MCPToolExecutionError,
    MCPToolNotFoundError,
)
from core.mcp.client import MCPClient
from core.mcp.server import (
    MCPServer,
    MCPService,
    build_fastapi_router,
    get_mcp_service,
    register_prompt,
    register_resource,
    register_tool,
    reset_mcp_service,
)

__all__ = [
    # 服务端
    "MCPServer",
    "MCPService",
    "get_mcp_service",
    "reset_mcp_service",
    "build_fastapi_router",
    "register_resource",
    "register_tool",
    "register_prompt",
    # 客户端
    "MCPClient",
    # 异常
    "MCPError",
    "MCPResourceNotFoundError",
    "MCPToolNotFoundError",
    "MCPToolExecutionError",
    "MCPProtocolVersionMismatchError",
    "MCPPromptNotFoundError",
]
