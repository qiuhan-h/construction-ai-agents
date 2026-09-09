"""LLM 接入层：OpenAI 兼容 Chat Completions 直连（httpx）。

设计原则：
- 不绑定任何特定模型厂商，仅依赖 OpenAI 兼容接口（阿里云百炼 / OpenAI / 自建等）；
- 模型与端点地址完全由 Settings 注入（不硬编码任何供应商信息）；
- 失败显式化：超时/限流/格式错误分别映射到不同异常，由上层（编排层）决策重试或降级；
- 指数退避重试仅针对瞬时故障（网络错误 / 429 / 5xx），4xx 业务错误直接抛错；
- 每次成功调用自动写入 TokenTracker（成本归因到 caller）。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from common.exceptions import (
    LLMAllProvidersFailedError,
    LLMError,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMResponseInvalidError,
    LLMTimeoutError,
)
from core.llm.config import LLMModelConfig, get_llm_model_config
from core.llm.token_tracker import get_token_tracker

logger = logging.getLogger(__name__)

_CHAT_PATH = "/chat/completions"


@dataclass
class ChatMessage:
    """单条对话消息。"""

    role: str  # system / user / assistant
    content: str


@dataclass
class LLMUsage:
    """本次调用的 token 用量。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    """LLM 调用结果。"""

    content: str
    model: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


class OpenAICompatibleProvider:
    """单个 OpenAI 兼容端点的提供者。"""

    def __init__(self, config: LLMModelConfig) -> None:
        self.config = config

    def _request_body(
        self, messages: list[ChatMessage], temperature: float | None, max_tokens: int | None
    ) -> dict[str, Any]:
        return {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "stream": False,
        }

    def _parse_response(self, payload: dict[str, Any]) -> LLMResponse:
        try:
            choice = payload["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseInvalidError(
                "LLM 响应结构异常",
                details={"payload_keys": list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__},
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseInvalidError("LLM 响应内容为空")
        usage_raw = payload.get("usage") or {}
        usage = LLMUsage(
            prompt_tokens=int(usage_raw.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage_raw.get("completion_tokens", 0) or 0),
            total_tokens=int(usage_raw.get("total_tokens", 0) or 0),
        )
        return LLMResponse(content=content, model=self.config.model, usage=usage, raw=payload)

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        caller: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """执行一次对话补全（含瞬时故障退避重试）。

        Raises:
            LLMTimeoutError: 所有重试均超时。
            LLMRateLimitError: 重试耗尽仍被限流。
            LLMError: 服务端 5xx / 4xx 业务错误 / 响应格式异常。
        """
        if not messages:
            raise LLMError("messages 不能为空", details={"model": self.config.model})

        headers = {
            "Authorization": f"Bearer {self.config.api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        body = self._request_body(messages, temperature, max_tokens)
        url = f"{self.config.base_url}{_CHAT_PATH}"

        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            if attempt > 0:
                delay = min(2 ** attempt, 30)
                logger.warning(
                    "LLM 调用重试 model=%s attempt=%d delay=%ss",
                    self.config.model, attempt, delay,
                )
                time.sleep(delay)
            try:
                with httpx.Client(timeout=self.config.timeout) as client:
                    resp = client.post(url, headers=headers, json=body)
            except httpx.TimeoutException as _:
                last_error = LLMTimeoutError(
                    f"LLM 请求超时（{self.config.timeout}s）",
                    details={"model": self.config.model, "attempts": attempt + 1},
                )
                logger.warning("LLM 超时: %s", last_error)
                continue
            except httpx.HTTPError as exc:
                last_error = LLMError(f"LLM 网络错误: {exc}", details={"model": self.config.model})
                continue

            if resp.status_code == 429:
                last_error = LLMRateLimitError(
                    "LLM 触发限流",
                    details={"model": self.config.model, "attempts": attempt + 1},
                )
                continue
            if resp.status_code >= 500:
                last_error = LLMError(
                    f"LLM 服务端错误 {resp.status_code}",
                    details={"model": self.config.model, "status": resp.status_code},
                )
                continue
            if resp.status_code >= 400:
                # 4xx（非 429）通常是请求/配置错误，重试无意义
                raise LLMError(
                    f"LLM 请求被拒绝 {resp.status_code}",
                    details={
                        "model": self.config.model,
                        "status": resp.status_code,
                        "body": resp.text[:500],
                    },
                )

            try:
                payload = resp.json()
            except (json.JSONDecodeError, ValueError) as exc:
                raise LLMResponseInvalidError(
                    "LLM 响应不是合法 JSON",
                    details={"model": self.config.model, "body": resp.text[:500]},
                ) from exc

            result = self._parse_response(payload)
            if result.usage.total_tokens:
                get_token_tracker().record(
                    result.model,
                    result.usage.prompt_tokens,
                    result.usage.completion_tokens,
                    caller=caller,
                )
            return result

        # 重试耗尽：保留最后一次的具体错误类型
        if isinstance(last_error, LLMRateLimitError):
            raise last_error
        if isinstance(last_error, LLMTimeoutError):
            raise last_error
        raise LLMError(
            f"LLM 调用失败（重试 {self.config.max_retries} 次后放弃）",
            details={"model": self.config.model},
        ) from last_error


class ProviderRouter:
    """多模型路由：按优先级降级链依次尝试，全部失败才抛错。

    默认路由：配置的默认模型。业务可通过 register 增加备用模型
    （如主力限流时切到同厂备选模型）。
    """

    def __init__(self, providers: list[OpenAICompatibleProvider]) -> None:
        if not providers:
            raise ValueError("ProviderRouter 至少需要一个 provider")
        self._providers = providers

    def register(self, model: str) -> ProviderRouter:
        """追加备用模型（配置沿用全局 Settings）。"""
        self._providers.append(OpenAICompatibleProvider(get_llm_model_config(model)))
        return self

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        caller: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """发起对话补全。

        model 指定时只使用该模型（失败不降级）；
        未指定时按降级链尝试全部模型。
        """
        if model is not None:
            for p in self._providers:
                if p.config.model == model:
                    return p.chat(messages, caller=caller, temperature=temperature, max_tokens=max_tokens)
            # 未注册的模型：临时构造 provider
            return OpenAICompatibleProvider(get_llm_model_config(model)).chat(
                messages, caller=caller, temperature=temperature, max_tokens=max_tokens
            )

        errors: list[str] = []
        for p in self._providers:
            try:
                return p.chat(messages, caller=caller, temperature=temperature, max_tokens=max_tokens)
            except LLMNotConfiguredError:
                raise
            except Exception as exc:  # noqa: BLE001  降级链需要吞掉一切失败
                errors.append(f"{p.config.model}: {exc}")
                logger.error("LLM 模型降级 model=%s error=%s", p.config.model, exc)
        raise LLMAllProvidersFailedError(
            "所有 LLM 模型均调用失败",
            details={"attempts": errors},
        )


_router: ProviderRouter | None = None


def get_router() -> ProviderRouter:
    """全局 Provider 路由单例（未配置 LLM_API_KEY 时延迟到首次调用才抛错）。"""
    global _router
    if _router is None:
        _router = ProviderRouter([OpenAICompatibleProvider(get_llm_model_config())])
    return _router
