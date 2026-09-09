"""安全审核链（5b.6 实做，对齐 shu_zhuang_tu.txt 第 188 行）。

职责：
- 注册 ``safety_audit`` 业务链 + prompt + mock 响应；
- 业务逻辑：方案 / 图纸 / 结构安全审核 → verdict + findings + suggestions；
- 缺 langchain SDK 时降级 ``MockBusinessChain``（用注册的 mock 响应）。

注册链名：``safety_audit``
"""

from __future__ import annotations

from core.langchain.chains import (
    LCTBusinessChain,
    register_chain,
    register_mock_response,
    register_prompt,
)

# =====================================================
# Prompt 模板（中文 + LangChain 风格占位符）
# =====================================================
SAFETY_AUDIT_PROMPT = (
    "你是施工现场安全审核专家，负责对【{project_name}】的{artifact_kind}进行审核。\n"
    "审核要点：\n"
    "1) 是否符合 GB 50016 / GB 50011 / JGJ 59 等强制性条文；\n"
    "2) 高危作业（深基坑 / 高支模 / 起重吊装 / 拆除爆破）安全措施是否到位；\n"
    "3) 应急预案 / 人员资质 / 监测方案是否完备。\n"
    "输入：\n{document}\n"
    "请输出 JSON，包含 verdict(通过/有条件通过/不通过)、"
    "findings(风险点列表)、suggestions(整改建议)。"
)


def _mock_safety_audit_response(tenant_id: str) -> dict:
    """Mock 响应：高支模区域未提供监测点位图。"""
    return {
        "verdict": "有条件通过",
        "findings": [
            {
                "id": "f-001",
                "level": "warning",
                "summary": "高支模区域未提供监测点位图",
            },
        ],
        "suggestions": [
            "补充高支模区域监测点位布置图（间距 ≤ 6m）",
        ],
    }


def _register() -> None:
    """注册 safety_audit 业务链（import 时调用一次）。"""
    register_prompt("safety_audit", SAFETY_AUDIT_PROMPT)
    register_mock_response("safety_audit", _mock_safety_audit_response)
    register_chain("safety_audit", lambda: LCTBusinessChain("safety_audit"))


_register()


__all__ = ["SAFETY_AUDIT_PROMPT"]
