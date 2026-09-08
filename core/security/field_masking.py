"""字段级脱敏（6b.2 FieldMasker）。

规则矩阵 role → {field → action}：
  - hide   : 从输出中移除该字段（key 不保留）；
  - mask   : 值替换为固定掩码 ``"***"``；
  - partial : 值保留首尾字符、中间替换为 *（适用于手机号等）。

角色矩阵（spec FR-6b.2）：
  viewer    → budget hide / contractor mask / phone partial
  engineer  → budget mask / contractor partial / phone partial
  reviewer  → budget mask / phone partial
  admin     → 全显（不脱敏）

无外部依赖；深度递归 dict/list 嵌套。
"""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger("core.security.field_masking")

# 脱敏动作类型
HIDE = "hide"
MASK = "mask"
PARTIAL = "partial"

# 规则矩阵：role → {field → action}
MASKING_RULES: dict[str, dict[str, str]] = {
    "viewer": {
        "budget": HIDE,
        "contractor": MASK,
        "phone": PARTIAL,
        "cost": HIDE,
        "price": HIDE,
    },
    "engineer": {
        "budget": MASK,
        "contractor": PARTIAL,
        "phone": PARTIAL,
    },
    "reviewer": {
        "budget": MASK,
        "phone": PARTIAL,
    },
    "admin": {},  # 全显
}

# 掩码占位值
_MASK_VALUE = "***"
_PARTIAL_KEEP = 2  # 首尾各保留字符数


def _partial_mask(value: str) -> str:
    """部分掩码：保留首尾 _PARTIAL_KEEP 字符，中间替换为 *。"""
    if not value or len(value) <= _PARTIAL_KEEP * 2:
        return _MASK_VALUE
    return value[:_PARTIAL_KEEP] + "*" * (len(value) - _PARTIAL_KEEP * 2) + value[-_PARTIAL_KEEP:]


def _apply_action(value: Any, action: str) -> Any:
    if action == HIDE:
        return _HIDE_SENTINEL  # 特殊标记，外层负责删除 key
    if action == MASK:
        return _MASK_VALUE
    if action == PARTIAL:
        if isinstance(value, str):
            return _partial_mask(value)
        return _MASK_VALUE
    return value


# 哨兵：hide 动作的返回值（用于区分 None 值和 hide 动作）
_HIDE_SENTINEL = object()


class FieldMasker:
    """字段级脱敏器。"""

    def __init__(self, rules: dict[str, dict[str, str]] | None = None) -> None:
        self._rules = rules if rules is not None else MASKING_RULES

    def mask(self, data: Any, role: str) -> Any:
        """对 data 按 role 规则脱敏，返回副本（不修改原对象）。

        - dict：递归脱敏每个字段；
        - list：递归脱敏每个元素；
        - 标量：原样返回。
        """
        rules = self._rules.get(role, self._rules.get("viewer", {}))
        if not rules:  # admin 或未知角色 → 原样返回
            return copy.deepcopy(data)
        return self._mask_recursive(data, rules)

    def _mask_recursive(self, data: Any, rules: dict[str, str]) -> Any:
        if isinstance(data, dict):
            result: dict[str, Any] = {}
            for key, value in data.items():
                action = rules.get(key)
                if action == HIDE:
                    continue  # hide → key 不保留
                if action is not None:
                    masked = _apply_action(value, action)
                    if masked is _HIDE_SENTINEL:
                        continue
                    result[key] = masked
                else:
                    # 无规则 → 递归（可能嵌套 dict/list）
                    result[key] = self._mask_recursive(value, rules)
            return result
        if isinstance(data, list):
            return [self._mask_recursive(item, rules) for item in data]
        return data


# =====================================================
# 单例 + 测试重置
# =====================================================
_masker: FieldMasker | None = None


def get_field_masker() -> FieldMasker:
    global _masker
    if _masker is None:
        _masker = FieldMasker()
    return _masker


def reset_field_masker() -> None:
    global _masker
    _masker = None


__all__ = [
    "FieldMasker",
    "MASKING_RULES",
    "HIDE",
    "MASK",
    "PARTIAL",
    "get_field_masker",
    "reset_field_masker",
]
