"""提示词模板管理：版本化、严格变量校验、集中维护。

约定：
- 模板文本使用 str.format 占位符（{plan_type} 等）；
- render() 严格校验缺失/多余变量，避免把未替换的占位符发给 LLM；
- 模板带版本号，报告中引用提示词版本可复盘输出差异。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from common.exceptions import ValidationError


@dataclass(frozen=True)
class PromptTemplate:
    """一个提示词模板（含版本）。"""

    name: str
    text: str
    version: str = "1.0"
    variables: tuple[str, ...] = field(default_factory=tuple)  # 为空时从 text 自动解析


class PromptManager:
    """提示词模板注册表。"""

    def __init__(self) -> None:
        self._templates: dict[str, PromptTemplate] = {}

    def register(self, template: PromptTemplate, *, overwrite: bool = False) -> None:
        if template.name in self._templates and not overwrite:
            raise ValidationError(
                f"提示词模板已注册: {template.name}",
                details={"name": template.name},
            )
        self._templates[template.name] = template

    def get(self, name: str) -> PromptTemplate:
        try:
            return self._templates[name]
        except KeyError as exc:
            raise ValidationError(
                f"提示词模板未注册: {name}",
                details={"registered": sorted(self._templates)},
            ) from exc

    def list_names(self) -> list[str]:
        return sorted(self._templates)

    def render(self, name: str, **variables: str) -> str:
        """渲染模板。缺失或多余变量均抛 ValidationError。"""
        tpl = self.get(name)
        expected = set(tpl.variables) if tpl.variables else _extract_placeholders(tpl.text)
        provided = set(variables)
        missing = expected - provided
        extra = provided - expected
        if missing or extra:
            raise ValidationError(
                f"提示词变量不匹配: {name}",
                details={"missing": sorted(missing), "extra": sorted(extra)},
            )
        try:
            return tpl.text.format(**variables)
        except (KeyError, IndexError, ValueError) as exc:
            raise ValidationError(
                f"提示词渲染失败: {name}",
                details={"error": str(exc)},
            ) from exc


def _extract_placeholders(text: str) -> set[str]:
    """解析 str.format 占位符 {var}（忽略无名的花括号内容做粗略容错）。"""
    import re

    return {m for m in re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", text)}


# ---------------------------------------------------------------------------
# 内置 system 模板（智能体人格/角色基线，业务模板在各自智能体包内注册）
# ---------------------------------------------------------------------------

_BUILTIN_SYSTEM = (
    "你是一名资深建筑工程安全专家，负责{task_name}工作。"
    "你引用法规与标准时必须给出具体文件名称与条款号；"
    "不确定的内容必须明确说明不确定，禁止编造条款或数据；"
    "输出必须使用简体中文，结构清晰，可直接用于正式报告。"
)


def _build_default_manager() -> PromptManager:
    manager = PromptManager()
    manager.register(
        PromptTemplate(
            name="system.construction_expert",
            text=_BUILTIN_SYSTEM,
            version="1.0",
            variables=("task_name",),
        )
    )
    return manager


_manager: PromptManager | None = None


def get_prompt_manager() -> PromptManager:
    """全局提示词管理器单例。"""
    global _manager
    if _manager is None:
        _manager = _build_default_manager()
    return _manager
