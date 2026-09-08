"""LLM 提示词模板子包（阶段六 6a.3）。

提供中英双语 system prompt 构造器，供直接使用
``core.llm.provider.OpenAICompatibleProvider.chat()`` 的调用方
（非 LangChain 路径）使用。LangChain 路径的 prompt 模板仍在
``core/langchain/chains/*_chain.py`` 中通过 ``register_prompt`` 注册。
"""

from core.llm.prompts.compliance_prompt import (
    COMPLIANCE_SYSTEM_PROMPT_EN,
    COMPLIANCE_SYSTEM_PROMPT_ZH,
    build_compliance_messages,
)
from core.llm.prompts.safety_prompt import (
    SAFETY_SYSTEM_PROMPT_EN,
    SAFETY_SYSTEM_PROMPT_ZH,
    build_safety_messages,
)

__all__ = [
    "SAFETY_SYSTEM_PROMPT_ZH",
    "SAFETY_SYSTEM_PROMPT_EN",
    "build_safety_messages",
    "COMPLIANCE_SYSTEM_PROMPT_ZH",
    "COMPLIANCE_SYSTEM_PROMPT_EN",
    "build_compliance_messages",
]
