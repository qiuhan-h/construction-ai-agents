"""施工安全审核智能体的 LangChain 风格入口（最小可用版）。

设计：
- 不强制依赖 langchain 包；如未安装，__init__ 时降级为纯包装 handle()；
- 启用时：构造简单 LLMChain（prompt + llm + output_parser 占位）；
- 业务侧统一通过 .run(message) 调用；底层仍走 SafetyAuditAgent.handle()，
  保证与 A2A 路径行为一致。

阶段四将替换为完整 LangChain Agent（含工具调用、记忆、流式）。
"""

from __future__ import annotations

import logging
from typing import Any

from core.a2a.message import A2AMessage, Task
from common.constants import AgentName

from agents.safety_audit_agent.agent import SafetyAuditAgent

logger = logging.getLogger("agents.safety_audit_agent.langchain")


class SafetyAuditLangChainAgent:
    """LangChain 风格的安全审核智能体入口（包装 SafetyAuditAgent）。"""

    name = AgentName.SAFETY_AUDIT.value
    version = "0.1.0"

    def __init__(self, base_agent: SafetyAuditAgent) -> None:
        self._agent = base_agent
        self._chain: Any = None
        try:
            from langchain.chains import LLMChain  # type: ignore
            from langchain.prompts import PromptTemplate as LCPrompt  # type: ignore

            self._chain = LLMChain(
                llm=None,  # 不在 stage3 实际触发 LLM
                prompt=LCPrompt(
                    input_variables=["plan_summary"],
                    template="你是一名施工安全审核专家。请基于以下方案给出审查意见：\n{plan_summary}",
                ),
                output_key="review",
            )
            logger.info("LangChain 适配层已启用（chain 已构造）")
        except Exception as e:  # pragma: no cover
            logger.info("LangChain 未安装或初始化失败（%s），使用纯包装模式", e)
            self._chain = None

    async def run(self, message: A2AMessage, task: Task) -> A2AMessage:
        """统一入口：直接走 SafetyAuditAgent.handle()。"""
        return await self._agent.handle(message, task)

    @property
    def base_agent(self) -> SafetyAuditAgent:
        return self._agent

    @property
    def has_langchain(self) -> bool:
        return self._chain is not None


__all__ = ["SafetyAuditLangChainAgent"]
