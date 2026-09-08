"""现场监控智能体的 LangChain 风格入口（最小实现）。"""

from __future__ import annotations

import logging
from typing import Any

from core.a2a.message import A2AMessage, Task

from agents.site_monitor_agent.agent import SiteMonitorAgent

logger = logging.getLogger("agents.site_monitor_agent.langchain")


class SiteMonitorLangChainAgent:
    """LangChain 风格包装（缺失时降级）。"""

    name = "site_monitor_agent"
    version = "0.1.0"

    def __init__(self, base_agent: SiteMonitorAgent) -> None:
        self._agent = base_agent
        self._chain: Any = None
        try:
            from langchain.chains import LLMChain  # type: ignore
            from langchain.prompts import PromptTemplate as LCPrompt  # type: ignore

            self._chain = LLMChain(
                llm=None,
                prompt=LCPrompt(
                    input_variables=["sensor_data"],
                    template="你是一名现场监控专家。分析以下传感器数据：\n{sensor_data}",
                ),
                output_key="analysis",
            )
            logger.info("LangChain 适配层已启用")
        except Exception as e:  # pragma: no cover
            logger.info("LangChain 未安装（%s），使用纯包装", e)
            self._chain = None

    async def run(self, message: A2AMessage, task: Task) -> A2AMessage:
        return await self._agent.handle(message, task)

    @property
    def base_agent(self) -> SiteMonitorAgent:
        return self._agent

    @property
    def has_langchain(self) -> bool:
        return self._chain is not None


__all__ = ["SiteMonitorLangChainAgent"]
