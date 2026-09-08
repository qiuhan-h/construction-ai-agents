"""MCP 提示词：施工安全审核模板。

首版仅提供 1 个模板，参数化 stage / project / risks；
阶段三/四在 safety_audit_agent.prompts 中扩展更多模板。
"""

from __future__ import annotations

from typing import Any

from core.mcp.server import register_prompt

SAFETY_AUDIT_PROMPT_NAME: str = "safety.audit"


_SAFETY_AUDIT_TEMPLATE: str = """\
# 角色
你是一名资深施工安全审核专家，擅长识别方案中可能引发事故/隐患的薄弱环节。
# 当前阶段
{stage}
# 项目背景
{project}
# 已知风险
{risks}
# 任务
请按以下结构输出审查意见：
1. 关键风险点（按优先级）
2. 整改建议（每条对应可执行的措施）
3. 需要进一步核实的事项
4. 引用依据（请关联到具体法规/标准版本）
"""


@register_prompt(
    name=SAFETY_AUDIT_PROMPT_NAME,
    description="施工安全审核通用提示词模板（参数化）",
    arguments=[
        {"name": "stage", "required": True, "description": "施工阶段，如基坑/主体/装饰"},
        {"name": "project", "required": True, "description": "项目名称与简要说明"},
        {"name": "risks", "required": False, "description": "已知风险列表（可空）"},
    ],
)
async def render_safety_audit_prompt(
    stage: str, project: str, risks: str = ""
) -> dict[str, Any]:
    return {
        "messages": [
            {
                "role": "system",
                "content": "你严格按模板输出 JSON 之外的自然语言审查意见。",
            },
            {
                "role": "user",
                "content": _SAFETY_AUDIT_TEMPLATE.format(
                    stage=stage, project=project, risks=risks or "（无）"
                ),
            },
        ],
    }
