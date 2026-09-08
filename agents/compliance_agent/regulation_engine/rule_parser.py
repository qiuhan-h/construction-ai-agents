"""规则解析：JSON / YAML DSL → ComplianceRule 数据类列表。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from core.rules.rule import ComplianceRule

logger = logging.getLogger(__name__)

# 必需字段（DSL schema）
_REQUIRED_FIELDS = (
    "id", "code", "version", "clause", "severity",
    "field", "operator", "threshold", "message",
)


class RuleParseError(ValueError):
    """规则解析失败。"""


def parse_rule_dict(d: dict[str, Any]) -> ComplianceRule:
    """从 dict 解析一条 ComplianceRule。"""
    missing = [f for f in _REQUIRED_FIELDS if f not in d]
    if missing:
        raise RuleParseError(f"规则字段缺失: {missing}（id={d.get('id', '?')}）")
    try:
        return ComplianceRule(
            id=str(d["id"]),
            code=str(d["code"]),
            version=str(d["version"]),
            clause=str(d["clause"]),
            severity=str(d["severity"]),
            field=str(d["field"]),
            operator=str(d["operator"]),
            threshold=d["threshold"],
            message=str(d["message"]),
        )
    except (TypeError, ValueError) as e:
        raise RuleParseError(f"规则解析失败（id={d.get('id', '?')}）: {e}") from e


def parse_rule_file(path: str | Path) -> list[ComplianceRule]:
    """从 JSON / YAML 文件解析规则列表。"""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"规则文件不存在: {p}")
    text = p.read_text(encoding="utf-8")
    # 优先按 JSON 解析；失败回退 YAML
    data: Any
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
            data = yaml.safe_load(text)
        except ImportError as e:
            raise RuleParseError("PyYAML 未安装且 JSON 解析失败") from e
    if not isinstance(data, list):
        raise RuleParseError(f"规则文件顶层必须是列表，得到 {type(data).__name__}")
    out: list[ComplianceRule] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise RuleParseError(f"规则 #{i} 不是 dict")
        out.append(parse_rule_dict(item))
    logger.info("解析规则文件 %s: %d 条", p, len(out))
    return out
