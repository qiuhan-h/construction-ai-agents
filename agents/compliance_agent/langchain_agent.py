"""施工合规校验智能体的 LangChain 风格入口（最小实现）。"""

from __future__ import annotations

import logging
from typing import Any

from core.a2a.message import A2AMessage, Task

from agents.compliance_agent.agent import ComplianceAgent

logger = logging.getLogger("agents.compliance_agent.langchain")


class ComplianceLangChainAgent:
    """LangChain 风格的合规智能体入口（包装 ComplianceAgent）。"""

    name = "compliance_agent"
    version = "0.1.0"

    def __init__(self, base_agent: ComplianceAgent) -> None:
        self._agent = base_agent
        self._chain: Any = None
        try:
            from langchain.chains import LLMChain  # type: ignore
            from langchain.prompts import PromptTemplate as LCPrompt  # type: ignore

            self._chain = LLMChain(
                llm=None,  # 不在 stage4 实际触发 LLM
                prompt=LCPrompt(
                    input_variables=["plan_summary"],
                    template="你是一名合规审查专家。请基于以下方案给出审查意见：\n{plan_summary}",
                ),
                output_key="review",
            )
            logger.info("LangChain 适配层已启用（chain 已构造）")
        except Exception as e:  # pragma: no cover
            logger.info("LangChain 未安装或初始化失败（%s），使用纯包装模式", e)
            self._chain = None

    async def run(self, message: A2AMessage, task: Task) -> A2AMessage:
        """统一入口：直接走 ComplianceAgent.handle()。"""
        return await self._agent.handle(message, task)

    @property
    def base_agent(self) -> ComplianceAgent:
        return self._agent

    @property
    def has_langchain(self) -> bool:
        return self._chain is not None


__all__ = ["ComplianceLangChainAgent"]
