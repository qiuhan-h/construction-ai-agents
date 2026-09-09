"""合规校验链（5b.6 实做，对齐 shu_zhuang_tu.txt 第 186 行）。

职责：
- 注册 ``compliance`` 业务链 + prompt + mock 响应；
- 业务逻辑：法规库比对 → passed + violations（code/article/severity/suggestion）；
- 缺 langchain SDK 时降级 ``MockBusinessChain``（用注册的 mock 响应）。

注册链名：``compliance``
"""

from __future__ import annotations

from core.langchain.chains import (
    LCTBusinessChain,
    register_chain,
    register_mock_response,
    register_prompt,
)

# =====================================================
# Prompt 模板
# =====================================================
COMPLIANCE_PROMPT = (
    "你是建筑施工合规校验专家。\n"
    "对【{project_name}】的{check_kind}进行合规校验，比对法规库。\n"
    "输入：\n{regulation_codes}\n\n待校验内容：\n{content}\n"
    "输出 JSON（花括号内为字段格式，需原样输出花括号）：\n"
    '{{"passed": true或false, "violations": [{{"code": "规范编号", '
    '"article": "条文", "severity": "critical|high|medium|low", '
    '"suggestion": "整改建议"}}]}}'
)


def _mock_compliance_response(tenant_id: str) -> dict:
    """Mock 响应：防火墙耐火极限不足。"""
    return {
        "passed": False,
        "violations": [
            {
                "code": "GB50016-2014:8.3.1",
                "article": "防火墙构造",
                "severity": "critical",
                "suggestion": "防火墙耐火极限不足 3h，建议增设防火层",
            }
        ],
    }


def _register() -> None:
    """注册 compliance 业务链（import 时调用一次）。"""
    register_prompt("compliance", COMPLIANCE_PROMPT)
    register_mock_response("compliance", _mock_compliance_response)
    register_chain("compliance", lambda: LCTBusinessChain("compliance"))


_register()


__all__ = ["COMPLIANCE_PROMPT"]
