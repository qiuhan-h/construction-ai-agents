"""合规校验智能体提示词（中英双语）。

用于 ``OpenAICompatibleProvider.chat()`` 直连路径，结合法规上下文输出结构化 JSON。
"""
from __future__ import annotations

from core.llm.provider import ChatMessage

COMPLIANCE_SYSTEM_PROMPT_ZH = (
    "你是一名建筑合规校验专家，依据 GB 50016（防火）、GB 50011（抗震）、"
    "GB 50189（节能）、GB 50378（绿色建筑）、GB 50009（荷载）等现行规范，"
    "对设计文档进行条文级合规比对。\n"
    "校验要求：\n"
    "1. 每条不合规必须引用具体条文编号（clause）；\n"
    "2. 给出严重度 severity（critical / high / medium / low）；\n"
    "3. 说明不合格原因 reason 与整改建议 suggestion；\n"
    "4. 结论 conclusion 仅可取：合规 / 不合规 / 需人工复核；\n"
    "5. 必须输出 JSON，字段：conclusion、violations[{clause,severity,field,"
    "reason,suggestion}]、summary。"
)

COMPLIANCE_SYSTEM_PROMPT_EN = (
    "You are a building code compliance expert. Check design documents against "
    "GB 50016 (fire), GB 50011 (seismic), GB 50189 (energy), GB 50378 (green building) "
    "and GB 50009 (loads).\n"
    "Rules:\n"
    "1. Every violation must cite the exact clause number;\n"
    "2. Assign severity (critical/high/medium/low);\n"
    "3. Provide reason and remediation suggestion;\n"
    "4. Conclusion must be one of: compliant / non_compliant / manual_review;\n"
    "5. Output JSON only: conclusion, violations[{clause,severity,field,"
    "reason,suggestion}], summary."
)


def build_compliance_messages(
    document: str,
    *,
    regulations_context: str = "",
    lang: str = "zh",
) -> list[ChatMessage]:
    """构造合规校验对话消息（system + user）。

    Args:
        document: 设计文档文本（或结构化字段的 JSON 字符串）。
        regulations_context: 检索到的相关法规条文（由 RegulationIndex/RuleChecker 提供）。
        lang: "zh" 或 "en"。
    """
    system = (
        COMPLIANCE_SYSTEM_PROMPT_ZH if lang.lower().startswith("zh")
        else COMPLIANCE_SYSTEM_PROMPT_EN
    )
    if lang.lower().startswith("zh"):
        reg_block = f"参考法规条文：\n{regulations_context}\n" if regulations_context else ""
        user = f"{reg_block}待校验设计文档：\n{document}\n请输出合规校验 JSON。"
    else:
        reg_block = (
            f"Reference clauses:\n{regulations_context}\n" if regulations_context else ""
        )
        user = f"{reg_block}Design document:\n{document}\nReturn the compliance JSON."
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user),
    ]
