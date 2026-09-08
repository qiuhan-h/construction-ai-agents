"""监控分析链（5b.6 实做，对齐 shu_zhuang_tu.txt 第 187 行）。

职责：
- 注册 ``site_monitor`` 业务链 + prompt + mock 响应；
- 业务逻辑：实时告警 → action + reasoning + next_check_minutes + notify_channels；
- 缺 langchain SDK 时降级 ``MockBusinessChain``（用注册的 mock 响应）。

注册链名：``site_monitor``
"""

from __future__ import annotations

from core.langchain.chains import (
    LCTBusinessChain,
    register_chain,
    register_mock_response,
    register_prompt,
)


# =====================================================
# Prompt 模板
# =====================================================
MONITORING_PROMPT = (
    "你是施工现场监控分析专家，处理实时告警。\n"
    "告警上下文：\n{alert_payload}\n"
    "历史同类告警：\n{history}\n"
    "请输出 JSON（花括号内为字段格式，需原样输出花括号）：\n"
    '{{"action": "立即处置|持续观察|上报", "reasoning": "判断依据", '
    '"next_check_minutes": 数字, "notify_channels": ["dingtalk", "sms"]}}'
)


def _mock_site_monitor_response(tenant_id: str) -> dict:
    """Mock 响应：塔吊风速超阈值。"""
    return {
        "action": "立即处置",
        "reasoning": "塔吊风速超阈值且回转异常，3 分钟内派人现场检查",
        "next_check_minutes": 5,
        "notify_channels": ["dingtalk", "sms"],
    }


def _register() -> None:
    """注册 site_monitor 业务链（import 时调用一次）。"""
    register_prompt("site_monitor", MONITORING_PROMPT)
    register_mock_response("site_monitor", _mock_site_monitor_response)
    register_chain("site_monitor", lambda: LCTBusinessChain("site_monitor"))


_register()


__all__ = ["MONITORING_PROMPT"]
