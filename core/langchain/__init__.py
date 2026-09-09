"""core.langchain 包级 API（5b.6 实做 + 子包聚合）。

层级：
- ``chains/``           — 5b.6 实做的业务链子包（对齐 shu_zhuang_tu.txt §184-188）
  - ``chains/__init__.py``       协议 + MockBusinessChain + LCTBusinessChain +
                                  工厂注册表（get_chain/register_chain/list_chains）
  - ``chains/safety_chain.py``   安全审核链（方案/图纸/结构 → verdict/findings/suggestions）
  - ``chains/compliance_chain.py`` 合规校验链（法规比对 → passed/violations）
  - ``chains/monitoring_chain.py`` 监控分析链（告警 → action/reasoning/notify）
- ``memory/``          — ConversationMemory / VectorMemory（5b.6 不动）
- ``tools/``           — 5b.6 实做的业务工具子包（对齐 shu_zhuang_tu.txt §193-198）
  - ``tools/__init__.py``       适配层 + 工厂注册表（BusinessTool / MCPToolAdapter /
                                  LangChainToolAdapter / to_langchain_tool / get_tool）
  - ``tools/calculation.py``    计算工具（荷载/风险/结构校核 → MCP calculation.*）
  - ``tools/document_parse.py`` 文档解析工具（方案/图纸/文档校验 → MCP validation.*）
  - ``tools/gis_tools.py``       GIS 工具（geofence / 空间监测 → MCP analysis.*）
  - ``tools/vector_search.py``   向量检索工具（5b.2 ChromaDB 接入）

5b.6 入口约定：
    from core.langchain import get_chain, BusinessChain
    chain = get_chain("safety_audit")
    out = await chain.run(tenant_id, {"document": "..."})

    from core.langchain import get_tool, to_langchain_tool
    biz = get_tool("calculation.load")
    lc_tool = to_langchain_tool(biz)
"""

from __future__ import annotations

# 5b.6 顶层入口 - 业务链
from core.langchain.chains import (
    BusinessChain,
    ChainContext,
    LCTBusinessChain,
    MockBusinessChain,
    get_chain,
    langchain_available,
    list_chains,
    register_chain,
    reset_default_chains,
)

# 5b.6 顶层入口 - 业务工具
from core.langchain.tools import (
    BusinessTool,
    LangChainToolAdapter,
    MCPToolAdapter,
    MockTool,
    get_business_tool,
    get_business_tools,
    get_tool,
    list_tools,
    register_tool,
    reset_default_tools,
    to_langchain_tool,
)

__all__ = [
    # chains
    "BusinessChain",
    "ChainContext",
    "LCTBusinessChain",
    "MockBusinessChain",
    "get_chain",
    "langchain_available",
    "list_chains",
    "register_chain",
    "reset_default_chains",
    # tools
    "BusinessTool",
    "LangChainToolAdapter",
    "MCPToolAdapter",
    "MockTool",
    "get_business_tool",
    "get_business_tools",
    "get_tool",
    "list_tools",
    "register_tool",
    "reset_default_tools",
    "to_langchain_tool",
]
