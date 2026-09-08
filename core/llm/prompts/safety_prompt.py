"""安全审核智能体提示词（中英双语）。

用于 ``OpenAICompatibleProvider.chat()`` 直连路径，输出结构化 JSON。
"""
from __future__ import annotations

from core.llm.provider import ChatMessage

SAFETY_SYSTEM_PROMPT_ZH = (
    "你是一名资深建筑施工安全审核专家，熟悉 GB 50009（荷载）、GB 50010（混凝土结构）、"
    "GB 50016（防火）、GB 50011（抗震）、JGJ 59（建筑施工安全检查标准）等强制性条文。\n"
    "审核范围：施工方案 / 图纸 / 结构计算书 / 高危作业（深基坑、高支模、起重吊装、拆除爆破）。\n"
    "审核要求：\n"
    "1. 逐条核对强制性条文，给出条文编号；\n"
    "2. 区分 风险等级（critical / high / medium / low）；\n"
    "3. 结论仅可取：通过 / 有条件通过 / 不通过；\n"
    "4. 必须输出 JSON，字段：verdict、findings[{id,level,clause,summary}]、"
    "suggestions[整改建议]。"
)

SAFETY_SYSTEM_PROMPT_EN = (
    "You are a senior construction safety audit expert, proficient in GB 50009 (loads), "
    "GB 50010 (concrete structures), GB 50016 (fire protection), GB 50011 (seismic) and "
    "JGJ 59 (construction safety inspection).\n"
    "Scope: construction plans / drawings / structural calculations / high-risk works "
    "(deep excavation, high formwork, lifting, demolition).\n"
    "Rules:\n"
    "1. Check mandatory clauses one by one and cite the clause number;\n"
    "2. Classify risk level (critical/high/medium/low);\n"
    "3. Verdict must be one of: pass / conditional_pass / fail;\n"
    "4. Output JSON only: verdict, findings[{id,level,clause,summary}], suggestions[]."
)


def build_safety_messages(
    document: str,
    *,
    project_name: str = "",
    artifact_kind: str = "施工方案",
    lang: str = "zh",
) -> list[ChatMessage]:
    """构造安全审核对话消息（system + user）。

    Args:
        document: 待审核文档文本。
        project_name: 项目名（可选）。
        artifact_kind: 资料类型（施工方案/图纸/计算书）。
        lang: "zh" 或 "en"。
    """
    system = SAFETY_SYSTEM_PROMPT_ZH if lang.lower().startswith("zh") else SAFETY_SYSTEM_PROMPT_EN
    if lang.lower().startswith("zh"):
        user = (
            f"项目：{project_name or '未命名项目'}\n"
            f"资料类型：{artifact_kind}\n"
            f"待审核内容：\n{document}\n"
            "请输出审核 JSON。"
        )
    else:
        user = (
            f"Project: {project_name or 'unnamed'}\n"
            f"Artifact: {artifact_kind}\n"
            f"Document:\n{document}\n"
            "Return the audit JSON."
        )
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user),
    ]
