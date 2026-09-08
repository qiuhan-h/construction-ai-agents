"""复用 stage3 report_signer 的薄包装（4b 不重复实现）。"""

from __future__ import annotations

from agents.safety_audit_agent.outputs.report_signer import (
    SignInfo,
    sign_report_content,
    verify_signature,
)


def sign_for_alert(alert_content: str, tenant_id: str,
                  *, secret: str | None = None) -> SignInfo:
    """对告警/日报内容签章（与 stage3 review_report 共用 HMAC 工具）。"""
    return sign_report_content(alert_content, tenant_id, secret=secret)


__all__ = ["SignInfo", "sign_for_alert", "verify_signature"]
