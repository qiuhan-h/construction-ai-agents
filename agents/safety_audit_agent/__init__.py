"""施工安全审核智能体（safety_audit_agent）。

公开 API：
- SafetyAuditAgent        主类（A2A BaseAgent 子类）
- SafetyAuditLangChainAgent   LangChain 风格入口
- SafetyAuditMCPHandler   MCP 业务处理器
- build_a2a_router        构造 FastAPI A2A 路由
- install()               一次性安装 MCP 工具并返回 handler

使用：
    from agents.safety_audit_agent import SafetyAuditAgent, make_safety_audit_agent
    from agents.safety_audit_agent.mcp_handlers import install

    agent = make_safety_audit_agent(tenant_id="tnt_x")
    install()  # 把 safety.search_case / safety.match_regulation 注册到 MCP
"""

from agents.safety_audit_agent.agent import (
    SafetyAuditAgent,
    make_safety_audit_agent,
)
from agents.safety_audit_agent.langchain_agent import (
    SafetyAuditLangChainAgent,
)
from agents.safety_audit_agent.prompts import (
    PROMPT_DRAWING_REVIEW,
    PROMPT_PLAN_REVIEW,
    PROMPT_REPORT_DRAFT,
)

__all__ = [
    # 主类
    "SafetyAuditAgent",
    "make_safety_audit_agent",
    # LangChain 入口
    "SafetyAuditLangChainAgent",
    # 提示词
    "PROMPT_PLAN_REVIEW",
    "PROMPT_DRAWING_REVIEW",
    "PROMPT_REPORT_DRAFT",
]
