"""ABAC 引擎（6b.2 属性级访问控制）。

设计：
- RBAC 快路径先判定 → RBAC 拒绝直接 False，不走 ABAC（减少开销）；
- ABAC 仅在 RBAC 通过后追加，基于 subject/resource/environment 属性评估；
- 内置策略：
  * 时间窗：工作时段 09:00–18:00（UTC+8）外拒绝（可配置关闭）；
  * 敏感度：resource.sensitivity=high + subject.clearance=low → 拒绝；
  * 自定义规则：注册 callable ``Rule``，灵活扩展；
- 超时保护：单次 evaluate >50ms → 默认 deny（fail-secure）；
- 无外部依赖：sqlparse 缺失不影响 ABAC。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("core.security.abac")

# ABAC 评估超时阈值（秒），超时 → deny
ABAC_TIMEOUT_SECONDS = 0.05

# 工作时段（小时，UTC+8）
WORK_HOUR_START = 9
WORK_HOUR_END = 18

# 敏感度/许可等级
CLEARANCE_LEVELS = {"low": 0, "medium": 1, "high": 2}
SENSITIVITY_LEVELS = {"low": 0, "medium": 1, "high": 2}


def _clearance_level(value: str) -> int:
    return CLEARANCE_LEVELS.get(value, 0)


def _sensitivity_level(value: str) -> int:
    return SENSITIVITY_LEVELS.get(value, 0)


class ABACRule:
    """ABAC 规则：callable 包装 + 名称 + 描述。"""

    def __init__(
        self,
        name: str,
        evaluator: Callable[[dict, dict, str, dict], bool],
        *,
        description: str = "",
    ) -> None:
        self.name = name
        self.evaluator = evaluator
        self.description = description

    def evaluate(
        self, subject: dict, resource: dict, action: str, env: dict
    ) -> bool:
        try:
            return bool(self.evaluator(subject, resource, action, env))
        except Exception as e:  # noqa: BLE001
            logger.warning("ABAC 规则 %s 异常 → deny: %s", self.name, e)
            return False


# =====================================================
# 内置规则
# =====================================================
def _rule_time_window(
    subject: dict, resource: dict, action: str, env: dict
) -> bool:
    """时间窗规则：工作时段外拒绝（可通过 env['time_window_enabled']=False 关闭）。"""
    if not env.get("time_window_enabled", True):
        return True
    now: datetime = env.get("now") or datetime.now(UTC)
    # UTC+8 工作时段
    hour = (now.hour + 8) % 24
    return WORK_HOUR_START <= hour < WORK_HOUR_END


def _rule_sensitivity(
    subject: dict, resource: dict, action: str, env: dict
) -> bool:
    """敏感度规则：resource.sensitivity > subject.clearance → 拒绝。"""
    sensitivity = resource.get("sensitivity")
    if not sensitivity:
        return True  # 无敏感度标记 → 放行
    clearance = subject.get("clearance", "low")
    return _clearance_level(clearance) >= _sensitivity_level(sensitivity)


def _rule_tenant_match(
    subject: dict, resource: dict, action: str, env: dict
) -> bool:
    """租户隔离规则：subject.tenant_id != resource.tenant_id → 拒绝。"""
    s_tenant = subject.get("tenant_id", "")
    r_tenant = resource.get("tenant_id", "")
    if not s_tenant or not r_tenant:
        return True  # 任一缺失 → 不拦截（由其他层负责）
    return s_tenant == r_tenant


# =====================================================
# ABAC 引擎
# =====================================================
class ABACEngine:
    """属性级访问控制引擎。

    串联模式：RBAC 先判定 → 通过后 ABAC 追加；
    ABAC 内全部规则 AND 逻辑（任一 False → deny）；
    超时 → deny（fail-secure）。
    """

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._rules: list[ABACRule] = []
        self._timeout = ABAC_TIMEOUT_SECONDS
        # 时钟可注入：默认 monotonic；测试注入受控时钟消除时序 flaky（K1 修复）
        self._clock: Callable[[], float] = clock or time.monotonic
        self._lock = threading.Lock()
        # 注册内置规则
        self.register_rule(
            "time_window", _rule_time_window, description="工作时段 09:00-18:00"
        )
        self.register_rule(
            "sensitivity",
            _rule_sensitivity,
            description="敏感度 vs 许可等级",
        )
        self.register_rule(
            "tenant_match",
            _rule_tenant_match,
            description="租户隔离",
        )

    def register_rule(
        self,
        name: str,
        evaluator: Callable[[dict, dict, str, dict], bool],
        *,
        description: str = "",
    ) -> None:
        """注册自定义 ABAC 规则。"""
        with self._lock:
            self._rules.append(ABACRule(name, evaluator, description=description))

    def remove_rule(self, name: str) -> bool:
        with self._lock:
            before = len(self._rules)
            self._rules = [r for r in self._rules if r.name != name]
            return len(self._rules) < before

    @property
    def rules(self) -> list[ABACRule]:
        return list(self._rules)

    def evaluate(
        self,
        subject_attrs: dict[str, Any],
        resource_attrs: dict[str, Any],
        action: str,
        env_attrs: dict[str, Any] | None = None,
    ) -> bool:
        """评估 ABAC 策略。

        参数：
        - subject_attrs: 主体属性（tenant_id, role, clearance, ...）
        - resource_attrs: 资源属性（tenant_id, sensitivity, ...）
        - action: 操作（read/write/invoke/...）
        - env_attrs: 环境属性（now, time_window_enabled, ...）

        返回 True 表示允许；False 表示拒绝。
        超时 → False（deny）。
        """
        env = env_attrs or {}
        start = self._clock()
        for rule in self.rules:
            elapsed = self._clock() - start
            if elapsed > self._timeout:
                logger.warning(
                    "ABAC 评估超时 (%.3fs > %.3fs) → deny", elapsed, self._timeout
                )
                return False
            if not rule.evaluate(subject_attrs, resource_attrs, action, env):
                logger.info(
                    "ABAC 规则 %s 拒绝 (action=%s, subject=%s, resource=%s)",
                    rule.name,
                    action,
                    subject_attrs.get("role"),
                    resource_attrs.get("id", resource_attrs.get("sensitivity")),
                )
                return False
            # 规则执行后再检查超时（慢规则可能在执行中超出）
            elapsed = self._clock() - start
            if elapsed > self._timeout:
                logger.warning(
                    "ABAC 规则 %s 执行后超时 (%.3fs > %.3fs) → deny",
                    rule.name,
                    elapsed,
                    self._timeout,
                )
                return False
        return True


# =====================================================
# 单例 + 测试重置
# =====================================================
_engine: ABACEngine | None = None
_engine_lock = threading.Lock()


def get_abac_engine() -> ABACEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = ABACEngine()
    return _engine


def reset_abac_engine() -> None:
    """测试用：重置单例。"""
    global _engine
    with _engine_lock:
        _engine = None


__all__ = [
    "ABACEngine",
    "ABACRule",
    "get_abac_engine",
    "reset_abac_engine",
    "ABAC_TIMEOUT_SECONDS",
]
