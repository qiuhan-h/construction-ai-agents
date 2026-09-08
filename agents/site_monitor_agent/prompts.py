"""现场监控智能体专用提示词模板。"""

from __future__ import annotations

import logging

from core.llm import PromptTemplate, get_prompt_manager

logger = logging.getLogger(__name__)

PROMPT_ALERT_JUDGE: str = "site_monitor.alert_judge"
PROMPT_DAILY_REPORT: str = "site_monitor.daily_report"
PROMPT_TREND_REPORT: str = "site_monitor.trend_report"


def _register_all() -> None:
    pm = get_prompt_manager()
    for name, text in (
        (PROMPT_ALERT_JUDGE, "# 角色\n你是一名施工现场安全监控专家。"),
        (PROMPT_DAILY_REPORT, "# 角色\n你是一名施工日报撰写人。"),
        (PROMPT_TREND_REPORT, "# 角色\n你是一名施工趋势分析专家。"),
    ):
        pm.register(PromptTemplate(name=name, text=text, version="1.0"), overwrite=True)
    logger.info("site_monitor_agent 提示词模板已注册 (3/3)")


_register_all()


def list_prompts() -> list[str]:
    return [PROMPT_ALERT_JUDGE, PROMPT_DAILY_REPORT, PROMPT_TREND_REPORT]


__all__ = ["PROMPT_ALERT_JUDGE", "PROMPT_DAILY_REPORT", "PROMPT_TREND_REPORT", "list_prompts"]
