"""规则引擎：metric 阈值求值。"""

from __future__ import annotations

import logging

from core.rules.operator import compare
from core.rules.rule import AlertRule as _BaseAlertRule

logger = logging.getLogger(__name__)

# 4b 自己的 AlertRule 封装：与 stage4 共享 core/rules/rule.py 的基类
AlertRule = _BaseAlertRule


class RuleEngine:
    """对 (metric, value) 求值，返回触发的 Rule 列表。"""

    def __init__(self, rules: list[AlertRule] | None = None) -> None:
        self._rules: list[AlertRule] = list(rules or [])

    def add(self, rule: AlertRule) -> None:
        self._rules.append(rule)

    def remove(self, rule_id: str) -> bool:
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.id != rule_id]
        return len(self._rules) < before

    def evaluate(self, metric: str, value: float) -> list[AlertRule]:
        out: list[AlertRule] = []
        if not self._rules:
            logger.warning(
                "RuleEngine 无可用规则（metric=%s value=%s）；"
                "请通过 add() 或构造函数注入 AlertRule，否则不会触发任何告警",
                metric, value,
            )
            return out
        for r in self._rules:
            if r.metric != metric:
                continue
            if compare(value, r.operator, r.threshold):
                out.append(r)
        return out

    def list_rules(self) -> list[AlertRule]:
        return list(self._rules)


def default_alert_rules() -> list[AlertRule]:
    """施工现场默认告警阈值规则。

    H22 修补：``SiteMonitorAgent`` 原先构造空 ``RuleEngine()``，
    ``evaluate()`` 永远返回 []，规则引擎形同虚设。这里提供一组覆盖
    塔吊/风速/扬尘/噪声/高温/基坑位移的开箱即用阈值，运行时仍可由
    配置中心 / ThresholdManager 通过 ``add()`` / 构造参数覆盖。
    """
    return [
        # 塔吊荷载比（0~1）
        AlertRule(
            id="def_crane_load_crit", severity="critical", operator=">",
            threshold=0.9, metric="sensor.tower_crane.load_ratio",
        ),
        AlertRule(
            id="def_crane_load_high", severity="high", operator=">",
            threshold=0.75, metric="sensor.tower_crane.load_ratio",
        ),
        # 风速 m/s（>20 阵风/8 级停工，>12 预警）
        AlertRule(
            id="def_wind_crit", severity="critical", operator=">",
            threshold=20.0, metric="sensor.wind.speed",
        ),
        AlertRule(
            id="def_wind_high", severity="high", operator=">",
            threshold=12.0, metric="sensor.wind.speed",
        ),
        # 扬尘 PM2.5 μg/m³（重度/严重污染阈值）
        AlertRule(
            id="def_pm25_crit", severity="critical", operator=">",
            threshold=250.0, metric="env.pm25",
        ),
        AlertRule(
            id="def_pm25_high", severity="high", operator=">",
            threshold=150.0, metric="env.pm25",
        ),
        # 施工噪声 dB（昼间限值 70 / 夜间 55，85 为听力防护线）
        AlertRule(
            id="def_noise_high", severity="high", operator=">",
            threshold=85.0, metric="env.noise",
        ),
        # 高温作业 ℃（>40 停止室外作业）
        AlertRule(
            id="def_temp_high", severity="high", operator=">",
            threshold=40.0, metric="env.temperature",
        ),
        # 基坑位移 mm（累计 >30 报警）
        AlertRule(
            id="def_pit_disp_crit", severity="critical", operator=">",
            threshold=30.0, metric="sensor.pit.displacement_mm",
        ),
    ]
