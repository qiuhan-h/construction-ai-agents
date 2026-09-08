"""规则数据类与运算符工具（4a 合规 / 4b 告警 共用）。

公共基类 BaseRule + compare 工具是 4a ComplianceRule 与 4b AlertRule 共享的；
4a / 4b 各自继承 BaseRule 增加业务字段。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .operator import compare

# 严重度合法值（4a/4b 一致）
VALID_SEVERITIES: tuple[str, ...] = (
    "low", "medium", "high", "critical",
)


@dataclass(frozen=True)
class BaseRule:
    """所有规则的公共基类（id/severity/operator/threshold）。"""

    id: str
    severity: str         # low/medium/high/critical
    operator: str         # </<=/>/>=/==/!=
    threshold: Any        # 数值或字符串

    def __post_init__(self) -> None:
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(
                f"规则 {self.id} severity 非法: {self.severity}，"
                f"应在 {VALID_SEVERITIES} 内"
            )
        if self.operator not in {"<", "<=", ">", ">=", "==", "!="}:
            raise ValueError(
                f"规则 {self.id} operator 非法: {self.operator}"
            )


@dataclass(frozen=True)
class ComplianceRule(BaseRule):
    """4a 合规规则：在 design_doc[field] 上比较值。"""

    code: str               # GB 编号（如 "GB50016"）
    version: str            # 版本（如 "2014"）
    clause: str             # 条款号（如 "3.3.1"）
    field: str              # design_doc 直接字段名（不带 dotted path）
    message: str            # 违规说明


@dataclass(frozen=True)
class AlertRule(BaseRule):
    """4b 告警规则：在 metric 上比较值。"""

    metric: str              # e.g. "sensor.tower_crane.load_ratio"
    window_seconds: int = 60  # 滑动窗口（首版 unused）


# 向后兼容别名
Rule = ComplianceRule  # 阶段三 compatibility（4a 内部使用 ComplianceRule）


__all__ = [
    "BaseRule",
    "ComplianceRule",
    "AlertRule",
    "Rule",                  # 别名
    "VALID_SEVERITIES",
    "compare",
]
