"""设计文档校验：必填字段 + 格式。"""

from __future__ import annotations

import logging
from typing import Any

from common.constants import ViolationSeverity
from models.domain import Violation

logger = logging.getLogger(__name__)


# 必填文档字段
_REQUIRED_FIELDS = ("project_name", "design_unit", "design_date", "reviewer_signature")
# 最小文档长度（字符）
_MIN_DOC_LENGTH = 100


class DocumentValidator:
    """设计文档元数据 + 文本长度校验。"""

    def __init__(self) -> None:
        self._required_fields = _REQUIRED_FIELDS
        self._min_length = _MIN_DOC_LENGTH

    async def validate(
        self, doc_meta: dict[str, Any] | None, *, tenant_id: str = "",
    ) -> list[Violation]:
        # 注意：None 表示"无文档"，直接返回空；空 dict 仍触发必填检查
        if doc_meta is None:
            return []
        violations: list[Violation] = []
        violations.extend(self._check_required_fields(doc_meta, tenant_id=tenant_id))
        violations.extend(self._check_text_length(doc_meta, tenant_id=tenant_id))
        return violations

    def _check_required_fields(
        self, meta: dict[str, Any], *, tenant_id: str = "",
    ) -> list[Violation]:
        out: list[Violation] = []
        for f in self._required_fields:
            v = meta.get(f)
            if v is None or (isinstance(v, str) and not v.strip()):
                out.append(self._mk_violation(
                    f"设计文档必填字段缺失: {f}",
                    severity="medium",
                    tenant_id=tenant_id,
                ))
        return out

    def _check_text_length(
        self, meta: dict[str, Any], *, tenant_id: str = "",
    ) -> list[Violation]:
        out: list[Violation] = []
        body = meta.get("body", "")
        if isinstance(body, str) and len(body.strip()) < self._min_length:
            out.append(self._mk_violation(
                f"文档正文长度 {len(body)} < {self._min_length}",
                severity="low",
                tenant_id=tenant_id,
            ))
        return out

    @staticmethod
    def _mk_violation(
        description: str, severity: str = "low", *, tenant_id: str = "",
    ) -> Violation:
        sev_map = {
            "low": ViolationSeverity.LOW,
            "medium": ViolationSeverity.MEDIUM,
            "high": ViolationSeverity.HIGH,
            "critical": ViolationSeverity.CRITICAL,
        }
        return Violation(
            tenant_id=tenant_id,
            inspection_id="",
            regulation_id="DOC-META",
            regulation_version="1.0",
            clause="-",
            description=description,
            severity=sev_map.get(severity, ViolationSeverity.LOW),
            rectification="补全文档字段",
        )
