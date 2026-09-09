"""规则运算符工具：实际值 vs 阈值。"""

from __future__ import annotations

from typing import Any


def compare(actual: Any, operator: str, threshold: Any) -> bool:
    """实际值与阈值按 operator 比较。

    支持的 operator：<, <=, >, >=, ==, !=
    数值：直接比较
    字符串：== / != 按字面比较，其它按字符串"长度"或字典序（与 dict 一致）
    None：== None 仅当 threshold == None；其它 operator 一律 False
    """
    if operator == "==":
        return actual == threshold
    if operator == "!=":
        return actual != threshold
    # 数值比较；字符串用 >, <, >=, <= 时按 Python 默认序
    try:
        a = _coerce(actual)
        t = _coerce(threshold)
        if a is None or t is None:
            return False
        if operator == "<":
            return a < t
        if operator == "<=":
            return a <= t
        if operator == ">":
            return a > t
        if operator == ">=":
            return a >= t
    except TypeError:
        return False
    return False


def _coerce(v: Any) -> Any:
    """尽量转 float；不能转就保留原值。"""
    if v is None:
        return None
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return v
    return v


__all__ = ["compare"]
