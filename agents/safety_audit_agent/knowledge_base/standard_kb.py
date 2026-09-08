"""标准知识库 — GB 条文结构化检索接口。

包装 RuleChecker，提供 clause_id / severity / 关键词 三种检索维度，
供 LLM 辅助解释时调用。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

try:
    from agents.compliance_agent.regulation_engine.rule_checker import (
        RuleChecker,
        StructuredRule,
    )
except ImportError:  # pragma: no cover
    RuleChecker = None  # type: ignore[assignment]
    StructuredRule = None  # type: ignore[assignment]


@dataclass(frozen=True)
class KnowledgeEntry:
    """单条条文检索结果。"""
    clause_id: str
    title: str
    severity: str
    field: str
    operator: str
    expected: object
    reason: str
    suggestion: str


class StandardKnowledgeBase:
    """GB 条文结构化知识库。

    用法::

        kb = StandardKnowledgeBase()
        entries = kb.search(keyword="耐火")       # 关键词搜索
        entries = kb.by_severity("critical")      # 严重度过滤
        entries = kb.by_clause("GB50016-2014-5.1.1-1")  # 精确查找
    """

    def __init__(self) -> None:
        self._checker = RuleChecker() if RuleChecker is not None else None

    def all(self) -> list[KnowledgeEntry]:
        """返回全部已加载条文。"""
        if self._checker is None:
            return []
        return [self._to_entry(r) for r in self._checker._rules]

    def search(self, keyword: str) -> list[KnowledgeEntry]:
        """按关键词检索 title / reason / suggestion。"""
        kw = keyword.lower()
        return [
            self._to_entry(r) for r in self._checker._rules
            if kw in (r.title + r.reason + r.suggestion + r.clause_id).lower()
        ]

    def by_severity(self, severity: str) -> list[KnowledgeEntry]:
        """按严重度筛选。"""
        sev = severity.lower()
        return [self._to_entry(r) for r in self._checker._rules if r.severity == sev]

    def by_clause(self, clause_id: str) -> KnowledgeEntry | None:
        """精确查找。"""
        for r in self._checker._rules:
            if r.clause_id == clause_id:
                return self._to_entry(r)
        return None

    def by_field(self, field_name: str) -> list[KnowledgeEntry]:
        """按检查字段名筛选（含点号分隔的嵌套字段）。"""
        return [self._to_entry(r) for r in self._checker._rules if r.field == field_name]

    def count(self) -> int:
        return len(self._checker._rules) if self._checker else 0

    @staticmethod
    def _to_entry(rule: StructuredRule) -> KnowledgeEntry:
        return KnowledgeEntry(
            clause_id=rule.clause_id,
            title=rule.title,
            severity=rule.severity,
            field=rule.field,
            operator=rule.operator,
            expected=rule.value,
            reason=rule.reason,
            suggestion=rule.suggestion,
        )
