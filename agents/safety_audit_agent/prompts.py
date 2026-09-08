"""施工安全审核智能体的专用提示词模板。

注意：
- 模板通过 core.llm.prompt_manager.PromptManager.register 注册；
- 命名空间 "safety." 前缀，与 core.llm 默认模板区分；
- 阶段三提供 3 个模板：plan_review / drawing_review / report_draft。
- 模块被 import 时会自动注册（_register_all）。
"""

from __future__ import annotations

import logging

from core.llm import PromptTemplate, get_prompt_manager

logger = logging.getLogger("agents.safety_audit_agent.prompts")

PROMPT_PLAN_REVIEW: str = "safety.plan_review"
PROMPT_DRAWING_REVIEW: str = "safety.drawing_review"
PROMPT_REPORT_DRAFT: str = "safety.report_draft"


# =====================================================
# 模板定义
# =====================================================
_PLAN_REVIEW_TEMPLATE: str = """\
# 角色
你是一名资深施工安全审核专家，专注于脚手架/深基坑/起重吊装/模板等专项方案审查。

# 项目背景
{project}

# 阶段
{stage}

# 已知风险（来自方案解析）
{hazards}

# 荷载参数
{loads}

# 任务
请按以下结构给出审查意见：
1. 关键风险点（按优先级）
2. 整改建议（每条对应可执行的措施）
3. 需要进一步核实的事项
4. 引用依据（请关联到具体法规/标准版本）

# 输出要求
- 使用简体中文；
- 引用条款请给出文件号（如 JGJ 80-2016）+ 条款号；
- 不确定的内容请明确说明"需进一步核实"，禁止编造；
- 重点关注"人/机/料/法/环"五个维度。
"""


_DRAWING_REVIEW_TEMPLATE: str = """\
# 角色
你是一名建筑结构与施工图纸审核专家。

# 图纸元数据
{drawing_meta}

# 相关规范
{regulation_versions}

# 任务
请按以下结构给出图纸审查意见：
1. 图纸完整性（标题栏、版本、签字、设计单位）
2. 关键构件（梁/板/柱/剪力墙）的合理性提示
3. 与规范的符合性初判
4. 需要补充或澄清的事项

# 输出要求
- 简体中文；
- 必须给出具体文件号与版本；
- 不确定处请说明"无法判断，需补充图纸"。
"""


_REPORT_DRAFT_TEMPLATE: str = """\
# 角色
你是一名施工安全审查报告撰写人，需要把机器生成的审查要点润色为正式报告。

# 项目与方案
{project}

# 关键计算结果
{calculations}

# 风险列表（LEC）
{risks}

# 相关案例
{cases}

# 整改建议（机器生成）
{recommendations}

# 任务
请基于以上信息撰写一份正式审查报告的 Markdown 草稿，包含：
1. 报告标题与摘要
2. 审查依据（法规/标准列表）
3. 审查过程（计算 / 风险 / 案例）
4. 审查结论（pass / conditional_pass / fail 三选一，附理由）
5. 整改建议清单（按严重度排序）
6. 附注（数据来源 / 限制说明）

# 输出要求
- 简体中文；
- 引用条款与计算数据需可追溯；
- 不要新增未经核实的事实。
"""


# =====================================================
# 注册入口
# =====================================================
def _register_all() -> None:
    pm = get_prompt_manager()
    pm.register(
        PromptTemplate(
            name=PROMPT_PLAN_REVIEW,
            text=_PLAN_REVIEW_TEMPLATE,
            version="1.0",
        ),
        overwrite=True,
    )
    pm.register(
        PromptTemplate(
            name=PROMPT_DRAWING_REVIEW,
            text=_DRAWING_REVIEW_TEMPLATE,
            version="1.0",
        ),
        overwrite=True,
    )
    pm.register(
        PromptTemplate(
            name=PROMPT_REPORT_DRAFT,
            text=_REPORT_DRAFT_TEMPLATE,
            version="1.0",
        ),
        overwrite=True,
    )
    logger.info("safety_audit_agent 提示词模板已注册 (3/3)")


_register_all()


# =====================================================
# 公开 API
# =====================================================
def list_prompts() -> list[str]:
    """返回已注册的安全审核专用模板名。"""
    return [PROMPT_PLAN_REVIEW, PROMPT_DRAWING_REVIEW, PROMPT_REPORT_DRAFT]


__all__ = [
    "PROMPT_PLAN_REVIEW",
    "PROMPT_DRAWING_REVIEW",
    "PROMPT_REPORT_DRAFT",
    "list_prompts",
]
