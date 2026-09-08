"""结构化规则引擎：条文 → 机器可判定逻辑。

加载 rules/*.yml 中的规则，对设计文档执行自动检查。
输出 Violation 对象列表，每条含条文编号 + 判定结果 + 不合规原因 + 修改建议。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import]
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

from common.exceptions import AgentError

__all__ = [
    "Violation",
    "StructuredRule",
    "RuleChecker",
    "OperatorError",
]


class OperatorError(AgentError):
    """不支持的比较运算符。"""


@dataclass
class StructuredRule:
    """单条结构化规则（从 YAML 解析）。"""

    clause_id: str
    title: str
    severity: str  # critical / high / medium / low
    field: str
    operator: str
    value: Any
    unit: str = ""
    target_element: str = ""
    reason: str = ""
    suggestion: str = ""

    SUPPORTED_OPS = {">=", "<=", "==", "!=", ">", "<", "in", "not_in"}

    def evaluate(self, design_doc: dict[str, Any]) -> "RuleResult":
        """执行规则判定。"""
        actual = self._resolve_value(design_doc)
        if actual is None:
            return RuleResult(
                passed=False,
                reason=f"字段 '{self.field}' 未提供",
                suggestion=f"请提供 {self.field} 的值",
            )
        passed = self._compare(actual, self.value)
        if passed:
            return RuleResult(passed=True, reason="", suggestion="")
        return RuleResult(
            passed=False,
            reason=self.reason or f"{self.field} {self.operator} {self.value} 失败（实际值 {actual}）",
            suggestion=self.suggestion,
        )

    def _resolve_value(self, doc: dict[str, Any]) -> Any:
        """支持点号分隔的嵌套字段访问（如 fire_wall.fire_resistance_rating）。"""
        parts = self.field.split(".")
        cur: Any = doc
        for p in parts:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                return None
        return cur

    def _compare(self, actual: Any, expected: Any) -> bool:
        op = self.operator
        if op not in self.SUPPORTED_OPS:
            raise OperatorError(f"不支持的运算符: {op}")
        if op == ">=":
            return actual >= expected
        if op == "<=":
            return actual <= expected
        if op == "==":
            return actual == expected
        if op == "!=":
            return actual != expected
        if op == ">":
            return actual > expected
        if op == "<":
            return actual < expected
        # "in" 支持两种语义：
        #   1) expected 为 [lo, hi] 两元素列表 → 区间判定 lo <= actual <= hi
        #   2) expected 为一般可迭代对象       → 成员判定 actual in expected
        if op == "in":
            if (
                isinstance(expected, (list, tuple))
                and len(expected) == 2
                and all(isinstance(x, (int, float)) for x in expected)
            ):
                lo, hi = min(expected), max(expected)
                try:
                    return lo <= actual <= hi
                except TypeError:
                    pass
            try:
                return actual in expected
            except TypeError:
                return False
        if op == "not_in":
            if (
                isinstance(expected, (list, tuple))
                and len(expected) == 2
                and all(isinstance(x, (int, float)) for x in expected)
            ):
                lo, hi = min(expected), max(expected)
                try:
                    return not (lo <= actual <= hi)
                except TypeError:
                    pass
            try:
                return actual not in expected
            except TypeError:
                return True
        return False


@dataclass
class RuleResult:
    """单条规则判定结果。"""
    passed: bool
    reason: str = ""
    suggestion: str = ""


@dataclass
class Violation:
    """违规记录（与 violation_repository.Violation 同名但为独立领域模型）。"""
    clause_id: str
    title: str
    severity: str
    field: str = ""
    operator: str = ""
    expected: Any = None
    reason: str = ""
    suggestion: str = ""


class RuleChecker:
    """结构化规则引擎。

    用法::

        checker = RuleChecker()
        violations = checker.check(design_doc={"fire_resistance_rating": 1.5})
        for v in violations:
            print(v.clause_id, v.severity, v.reason)
    """

    def __init__(self, rules_dir: str | Path | None = None):
        self._rules_dir = Path(rules_dir) if rules_dir else self._default_rules_dir()
        self._rules: list[StructuredRule] = self._load_all()

    # ------------------------------------------------------------------
    # 文件发现
    # ------------------------------------------------------------------
    @staticmethod
    def _default_rules_dir() -> Path:
        """返回包内 rules/ 目录路径。"""
        here = Path(__file__).resolve().parent
        return here / "rules"

    def _load_all(self) -> list[StructuredRule]:
        rules: list[StructuredRule] = []
        if not self._rules_dir.is_dir() or yaml is None:
            return rules
        for yf in sorted(self._rules_dir.glob("*.yml")):
            rules.extend(self._load_one(yf))
        return rules

    def _load_one(self, path: Path) -> list[StructuredRule]:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        if not data or "rules" not in data:
            return []
        result: list[StructuredRule] = []
        for item in data["rules"]:
            try:
                result.append(StructuredRule(**item))
            except TypeError:
                # 字段不完整跳过（规则 YAML 格式错误不崩溃）
                continue
        return result

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def check(self, design_doc: dict[str, Any]) -> list[Violation]:
        """对设计文档执行全部规则检查，返回违规列表。"""
        violations: list[Violation] = []
        for rule in self._rules:
            result = rule.evaluate(design_doc)
            if not result.passed:
                violations.append(
                    Violation(
                        clause_id=rule.clause_id,
                        title=rule.title,
                        severity=rule.severity,
                        field=rule.field,
                        operator=rule.operator,
                        expected=rule.value,
                        reason=result.reason,
                        suggestion=result.suggestion,
                    )
                )
        return violations

    def rules_count(self) -> int:
        return len(self._rules)

    def rules_by_severity(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self._rules:
            out[r.severity] = out.get(r.severity, 0) + 1
        return out
