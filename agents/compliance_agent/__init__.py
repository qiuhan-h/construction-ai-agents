"""施工合规校验智能体（compliance_agent）。

公开 API：
- ComplianceAgent                主类（A2A BaseAgent 子类）
- ComplianceLangChainAgent        LangChain 风格入口
- ComplianceMCPHandler            MCP 业务处理器
- build_a2a_router                 构造 FastAPI A2A 路由
- install()                        一次性安装 MCP 工具并返回 handler

使用：
    from agents.compliance_agent import (
        ComplianceAgent, make_compliance_agent,
    )
    from agents.compliance_agent.mcp_handlers import install

    agent = make_compliance_agent(tenant_id="tnt_x")
    install()  # 把 compliance.search_regulation / list_violations 等注册到 MCP
"""

from agents.compliance_agent.agent import (
    ComplianceAgent,
    make_compliance_agent,
)
from agents.compliance_agent.langchain_agent import (
    ComplianceLangChainAgent,
)
from agents.compliance_agent.prompts import (
    PROMPT_ENERGY_REVIEW,
    PROMPT_FIRE_REVIEW,
    PROMPT_GREEN_REVIEW,
    PROMPT_SEISMIC_REVIEW,
)

__all__ = [
    # 主类
    "ComplianceAgent",
    "make_compliance_agent",
    # LangChain 入口
    "ComplianceLangChainAgent",
    # 提示词
    "PROMPT_FIRE_REVIEW",
    "PROMPT_SEISMIC_REVIEW",
    "PROMPT_ENERGY_REVIEW",
    "PROMPT_GREEN_REVIEW",
]
