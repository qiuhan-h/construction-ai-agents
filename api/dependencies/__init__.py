"""api.dependencies 包：FastAPI 依赖注入项。

公开 API：
- AuthContext / get_auth_context  鉴权上下文（4d）
- AgentManager / get_agent_manager / init_agent_manager  智能体 DI（4d）
- get_orchestrator / init_orchestrator  编排器 DI（4d）
"""

from api.dependencies.agent_manager import (
    AgentManager,
    init_agent_manager,
    reset_agent_manager,
    get_agent_manager,
)
from api.dependencies.auth import (
    AuthContext,
    get_auth_context,
    reset_auth_state,
)
from api.dependencies.orchestrator_provider import (
    get_orchestrator,
    init_orchestrator,
    reset_orchestrator,
)

__all__ = [
    # auth
    "AuthContext",
    "get_auth_context",
    "reset_auth_state",
    # agent_manager
    "AgentManager",
    "init_agent_manager",
    "reset_agent_manager",
    "get_agent_manager",
    # orchestrator
    "get_orchestrator",
    "init_orchestrator",
    "reset_orchestrator",
]
