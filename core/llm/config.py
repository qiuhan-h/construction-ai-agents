"""LLM 模型配置：从全局 Settings 派生模型级调用参数。

密钥只从环境变量 / .env 注入（Settings.llm_api_key 为 SecretStr），
本模块不做任何硬编码兜底——缺失即显式失败（LLMNotConfiguredError）。
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import SecretStr

from common.exceptions import LLMNotConfiguredError
from config import get_settings


@dataclass(frozen=True)
class LLMModelConfig:
    """单次 LLM 调用的完整参数快照。"""

    model: str
    base_url: str
    api_key: SecretStr
    timeout: float
    max_retries: int
    temperature: float
    max_tokens: int


def get_llm_model_config(model: str | None = None) -> LLMModelConfig:
    """构造模型配置。model 为空时使用全局默认模型。

    Raises:
        LLMNotConfiguredError: 未配置 LLM_API_KEY 时（避免静默降级）。
    """
    settings = get_settings()
    api_key = settings.llm_api_key
    if not api_key.get_secret_value():
        raise LLMNotConfiguredError(
            "未配置 LLM_API_KEY，请在 .env 或环境变量中设置",
            details={"hint": "cp .env.example .env 后填写 LLM_API_KEY"},
        )
    return LLMModelConfig(
        model=model or settings.llm_default_model,
        base_url=settings.llm_base_url.rstrip("/"),
        api_key=api_key,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
