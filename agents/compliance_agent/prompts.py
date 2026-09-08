"""合规校验智能体专用提示词模板。"""

from __future__ import annotations

import logging

from core.llm import PromptTemplate, get_prompt_manager

logger = logging.getLogger(__name__)

PROMPT_FIRE_REVIEW: str = "compliance.fire_review"
PROMPT_SEISMIC_REVIEW: str = "compliance.seismic_review"
PROMPT_ENERGY_REVIEW: str = "compliance.energy_review"
PROMPT_GREEN_REVIEW: str = "compliance.green_review"


_FIRE_REVIEW_TEMPLATE: str = """\
# 角色
你是一名资深建筑防火设计审查专家。

# 项目背景
{project}

# 设计文件关键参数
{design_doc}

# 适用法规
{regulations}

# 任务
请按以下结构给出防火审查意见：
1. 关键风险点（按优先级排序）
2. 整改建议（每条对应可执行的措施）
3. 需要进一步核实的事项
4. 引用依据（GB 50016 + 具体条款号）

# 输出要求
- 使用简体中文；
- 引用条款请给出文件号 + 条款号；
- 不确定的内容请明确说明"需进一步核实"，禁止编造。
"""


_SEISMIC_REVIEW_TEMPLATE: str = """\
# 角色
你是一名建筑结构抗震设计审查专家。

# 项目背景
{project}

# 设计文件关键参数
{design_doc}

# 适用法规
{regulations}

# 任务
请按以下结构给出抗震审查意见：
1. 设防烈度合理性
2. 结构体系与高度限值核查
3. 层间位移角与构造措施
4. 引用依据（GB 50011 + 条款号）

# 输出要求
- 简体中文；
- 必须给出具体文件号与版本；
- 不确定处请说明"无法判断，需补充图纸"。
"""


_ENERGY_REVIEW_TEMPLATE: str = """\
# 角色
你是一名建筑节能设计审查专家。

# 项目背景
{project}

# 设计文件关键参数
{design_doc}

# 适用法规
{regulations}

# 任务
请按以下结构给出节能审查意见：
1. 围护结构传热系数核查
2. 冷热源系统能效
3. 可再生能源利用
4. 引用依据（GB 50189 + 条款号）

# 输出要求
- 简体中文；
- 引用条款与计算数据需可追溯；
- 不要新增未经核实的事实。
"""


_GREEN_REVIEW_TEMPLATE: str = """\
# 角色
你是一名绿色建筑评价专家。

# 项目背景
{project}

# 设计文件关键参数
{design_doc}

# 适用法规
{regulations}

# 任务
请按以下结构给出绿色建筑审查意见：
1. 安全耐久
2. 健康舒适
3. 生活便利
4. 资源节约
5. 环境宜居
6. 引用依据（GB/T 50378 + 条款号）

# 输出要求
- 简体中文；
- 引用条款与评分项需可追溯；
- 不要新增未经核实的事实。
"""


def _register_all() -> None:
    pm = get_prompt_manager()
    for name, text in (
        (PROMPT_FIRE_REVIEW, _FIRE_REVIEW_TEMPLATE),
        (PROMPT_SEISMIC_REVIEW, _SEISMIC_REVIEW_TEMPLATE),
        (PROMPT_ENERGY_REVIEW, _ENERGY_REVIEW_TEMPLATE),
        (PROMPT_GREEN_REVIEW, _GREEN_REVIEW_TEMPLATE),
    ):
        pm.register(
            PromptTemplate(name=name, text=text, version="1.0"),
            overwrite=True,
        )
    logger.info("compliance_agent 提示词模板已注册 (4/4)")


_register_all()


def list_prompts() -> list[str]:
    return [
        PROMPT_FIRE_REVIEW, PROMPT_SEISMIC_REVIEW,
        PROMPT_ENERGY_REVIEW, PROMPT_GREEN_REVIEW,
    ]


__all__ = [
    "PROMPT_FIRE_REVIEW",
    "PROMPT_SEISMIC_REVIEW",
    "PROMPT_ENERGY_REVIEW",
    "PROMPT_GREEN_REVIEW",
    "list_prompts",
]
