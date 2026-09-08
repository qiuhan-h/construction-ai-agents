"""法规数据加载器：从 data/regulations/*.md 加载 + 注册 MCP 资源。

文件命名约定：{code}-{version}.md（如 GB50016-2014.md）
首行 markdown 标题 = 法规名；后续内容 = 全文。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegulationSummary:
    code: str
    version: str
    name: str
    effective_date: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def uri(self) -> str:
        return f"regulation://{self.code}/{self.version}"


_FILENAME_PATTERN = re.compile(r"^([A-Z]+\d+(?:[-/][A-Z0-9]+)?)-(\d{4})\.md$")

# code → 默认 categories 映射（4a checker 需要）
_CATEGORY_BY_CODE: dict[str, list[str]] = {
    "GB50016": ["fire"],
    "GB50011": ["seismic"],
    "GB50189": ["energy"],
    "GB50378": ["green"],
    "JGJ80": ["fire", "general"],          # 建筑施工高处作业安全技术规范
    "JGJ59": ["general"],                 # 建筑施工安全检查标准
    "GB50009": ["general"],                # 荷载规范（safety_audit 用）
}


class RegulationLoader:
    """从 data/regulations/*.md 加载法规元数据 + 暴露 MCP 资源。"""

    def __init__(self, data_dir: str | Path = "data/regulations"):
        self._data_dir = Path(data_dir)
        self._cache: list[dict[str, Any]] = []
        # 6a 增强：结构化规则条目字典（clause_id → 规则摘要），供下游查询使用
        self._regulations: dict[str, Any] = {}

    def bootstrap(self) -> list[dict[str, Any]]:
        """扫描目录 + 构建缓存。返回所有法规元数据列表。"""
        self._cache = self._scan()
        # 同步填充 _regulations 字典（code-version → 法规摘要）
        for item in self._cache:
            key = f"{item['code']}-{item['version']}"
            self._regulations[key] = item
        # 6a 增强：从结构化规则文件加载
        try:
            from agents.compliance_agent.regulation_engine.rule_checker import RuleChecker
            checker = RuleChecker()
            for rule in checker._rules:
                if rule.clause_id not in self._regulations:
                    self._regulations[rule.clause_id] = {
                        "code": rule.clause_id,
                        "name": rule.title,
                        "source": "yaml_rules",
                        "severity": rule.severity,
                    }
        except Exception:
            pass  # RuleChecker 不可用时保持原行为
        return list(self._cache)

    def list_all(self) -> list[dict[str, Any]]:
        """返回当前缓存的法规元数据（不重新扫描）。"""
        return list(self._cache)

    def get(self, code: str, version: str) -> dict[str, Any] | None:
        for r in self._cache:
            if r["code"] == code and r["version"] == version:
                return r
        return None

    def add(self, *, code: str, version: str, name: str | None = None,
            summary: str | None = None, categories: list[str] | None = None,
            **meta: Any) -> dict[str, Any]:
        """手动添加/覆盖一条法规。"""
        cats = categories if categories is not None else _CATEGORY_BY_CODE.get(code, ["general"])
        rec = {
            "code": code, "version": version,
            "name": name or f"{code}-{version}",
            "summary": summary or "",
            "categories": list(cats),
            "file_path": None,
            "metadata": meta,
        }
        # 去重更新
        self._cache = [r for r in self._cache
                      if not (r["code"] == code and r["version"] == version)]
        self._cache.append(rec)
        return rec

    def deprecate(self, code: str, version: str, reason: str) -> bool:
        for r in self._cache:
            if r["code"] == code and r["version"] == version:
                md = r.setdefault("metadata", {})
                md["deprecated"] = True
                md["deprecate_reason"] = reason
                return True
        return False

    def replace(self, old: tuple[str, str], new: tuple[str, str]) -> bool:
        """old=(code, version) 替换为 new=(code, version)。
        标记 old 为 deprecated；new 自动 add。"""
        ok = self.deprecate(old[0], old[1], reason=f"replaced by {new[0]}-{new[1]}")
        self.add(code=new[0], version=new[1])
        return ok

    def _scan(self) -> list[dict[str, Any]]:
        """扫描 data/regulations/ 目录，解析元数据。"""
        if not self._data_dir.exists():
            logger.info("法规目录不存在: %s", self._data_dir)
            return []
        out: list[dict[str, Any]] = []
        for path in sorted(self._data_dir.glob("*.md")):
            m = _FILENAME_PATTERN.match(path.name)
            if not m:
                logger.debug("跳过非法命名的法规文件: %s", path.name)
                continue
            code, version = m.group(1), m.group(2)
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as e:
                logger.warning("读取法规失败 %s: %s", path, e)
                continue
            first_line = text.splitlines()[0].lstrip("# ").strip() if text else ""
            out.append({
                "code": code, "version": version,
                "name": first_line or f"{code}-{version}",
                "summary": text[:200],
                "categories": _CATEGORY_BY_CODE.get(code, ["general"]),
                "file_path": str(path),
                "metadata": {},
            })
        logger.info("扫描法规目录: %s → %d 条", self._data_dir, len(out))
        return out
