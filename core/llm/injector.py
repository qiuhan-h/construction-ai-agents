"""LLM 注入器：全项目唯一 LLM 实例创建入口（阶段六 6a.3）。

职责：
- 按 ``provider``（mock / openai / anthropic / vllm）创建 LangChain 兼容 llm 对象；
- 缺失第三方 SDK（langchain_openai / langchain_anthropic）或未配置 API Key 时，
  自动降级，绝不抛 ImportError / 配置错误打断链路：
    openai/vllm 降级顺序：langchain_openai.ChatOpenAI → httpx 适配器（复用
    core.llm.provider.OpenAICompatibleProvider 的重试/限流/token 统计）→ FakeListLLM；
    anthropic 降级顺序：langchain_anthropic.ChatAnthropic → FakeListLLM；
- 单例缓存（同 provider 复用同一实例）。

返回对象均可传给 ``LLMChain(llm=...)`` / ``prompt | llm`` 使用。
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)

ProviderName = str  # "mock" | "openai" | "anthropic" | "vllm"
_VALID_PROVIDERS = {"mock", "openai", "anthropic", "vllm"}

# FakeListLLM 占位响应（mock 模式下保证链路可跑通，返回结构化 JSON）
# 重复多份：FakeListLLM 按顺序消耗 responses，单次进程内多个 chain 共享时不耗尽
_MOCK_RESPONSES = [
    '{"ok": true, "verdict": "mock", "note": "FakeListLLM 占位响应（未配置真实 LLM）"}'
] * 16


def _has_real_api_key() -> bool:
    """判断是否配置了可用的 LLM API Key（非空且非占位符）。"""
    try:
        key = get_settings().llm_api_key.get_secret_value()
    except Exception:  # noqa: BLE001
        return False
    if not key:
        return False
    placeholders = {"需要补充实际链接", "your-api-key", "xxx", "changeme"}
    return key.strip() not in placeholders


# =====================================================
# httpx 适配器：把 OpenAICompatibleProvider 包装成 LangChain BaseLLM
# 复用 core.llm.provider 的重试 / 限流 / token 统计，无需 langchain_openai
# =====================================================
def _build_httpx_adapter() -> Any | None:
    """构造 OpenAI 兼容 httpx 直连适配器；失败返回 None。"""
    try:
        from langchain_core.language_models.llms import LLM
        from langchain_core.outputs import Generation, LLMResult
        from pydantic import ConfigDict

        from core.llm.config import get_llm_model_config
        from core.llm.provider import ChatMessage, OpenAICompatibleProvider
    except Exception as e:  # noqa: BLE001  langchain_core / httpx 缺失
        logger.debug("httpx 适配器依赖不可用：%s", e)
        return None

    class _HttpxOpenAIAdapter(LLM):
        """把 OpenAICompatibleProvider.chat() 适配为 LangChain LLM 接口。"""

        model_config = ConfigDict(arbitrary_types_allowed=True)

        model_name: str = ""
        _provider: OpenAICompatibleProvider = None  # type: ignore[assignment]

        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            cfg = get_llm_model_config()
            self.model_name = cfg.model
            self._provider = OpenAICompatibleProvider(cfg)

        @property
        def _llm_type(self) -> str:
            return "openai_compatible_httpx"

        def _call(self, prompt: str, stop: list[str] | None = None, **_: Any) -> str:
            resp = self._provider.chat(
                [ChatMessage(role="user", content=prompt)],
                caller="langchain_chain",
            )
            return resp.content

        def _generate(self, prompts: list[str], stop: list[str] | None = None,
                      run_manager: Any = None, **kwargs: Any) -> LLMResult:
            generations = []
            for p in prompts:
                text = self._call(p, stop=stop, **kwargs)
                generations.append([Generation(text=text)])
            return LLMResult(generations=generations)

    try:
        return _HttpxOpenAIAdapter()
    except Exception as e:  # noqa: BLE001  配置/网络初始化失败
        logger.warning("httpx 适配器构造失败，降级 mock：%s", e)
        return None


def _build_fake_llm() -> Any:
    """构造 FakeListLLM 占位（langchain 已装时可用；调用方应已确认 langchain 可用）。

    langchain 1.0+ 将 FakeListLLM 迁至 ``langchain_community.llms.fake``；
    旧版（<0.2）在 ``langchain.llms.fake``。两个路径都尝试。
    """
    errors: list[str] = []
    for module_path in (
        "langchain_community.llms.fake",
        "langchain.llms.fake",
    ):
        try:
            import importlib

            mod = importlib.import_module(module_path)
            fake_cls = getattr(mod, "FakeListLLM")
            return fake_cls(responses=list(_MOCK_RESPONSES))
        except ImportError as e:  # noqa: PERF203
            errors.append(f"{module_path}: {e}")
    raise ImportError("FakeListLLM 不可用（langchain / langchain_community 均未提供）: "
                      + "; ".join(errors))


class LLMInjector:
    """LLM 实例工厂（单例）。

    用法::

        from core.llm.injector import get_injector
        llm = get_injector().get_llm()                 # 按 settings.llm_provider
        llm = get_injector().get_llm("openai")         # 显式指定
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._lock = threading.RLock()

    def get_llm(self, provider: str | None = None) -> Any:
        """返回 LangChain 兼容 llm 对象；任何失败都降级 FakeListLLM。"""
        if provider is None:
            try:
                provider = get_settings().llm_provider
            except Exception:  # noqa: BLE001
                provider = "mock"
        provider = (provider or "mock").lower()
        if provider not in _VALID_PROVIDERS:
            logger.warning("未知 llm_provider=%s，降级 mock", provider)
            provider = "mock"

        # mock 占位 LLM 每次新建：FakeListLLM 按序消耗 responses，
        # 共享单例会在多个 chain 间耗尽；真实 provider 才缓存单例（复用连接）。
        if provider == "mock":
            return self._build("mock")

        with self._lock:
            if provider in self._cache:
                return self._cache[provider]
            llm = self._build(provider)
            self._cache[provider] = llm
            return llm

    # ------------------------------------------------------------------
    def _build(self, provider: str) -> Any:
        if provider == "mock":
            try:
                return _build_fake_llm()
            except Exception as e:  # noqa: BLE001
                logger.warning("FakeListLLM 不可用（langchain 未装？）：%s", e)
                return _NullLLM()

        if provider in ("openai", "vllm"):
            return self._build_openai_compatible(provider)

        if provider == "anthropic":
            return self._build_anthropic()

        return self._safe_fake(provider)

    def _build_openai_compatible(self, provider: str) -> Any:
        # ① 优先 langchain_openai.ChatOpenAI
        if _has_real_api_key():
            try:
                from langchain_openai import ChatOpenAI  # type: ignore

                settings = get_settings()
                kwargs: dict[str, Any] = {
                    "model": settings.llm_default_model,
                    "api_key": settings.llm_api_key.get_secret_value(),
                    "base_url": settings.llm_base_url,
                    "temperature": settings.llm_temperature,
                    "max_tokens": settings.llm_max_tokens,
                }
                if provider == "vllm":
                    # vLLM 自建推理端点（OpenAI 兼容）；base_url 可由 .env 覆盖
                    kwargs["base_url"] = settings.llm_base_url
                llm = ChatOpenAI(**kwargs)
                logger.info("LLM 注入：langchain_openai.ChatOpenAI（provider=%s, model=%s）",
                            provider, kwargs["model"])
                return llm
            except ImportError:
                logger.info("未安装 langchain_openai，尝试 httpx 适配器（provider=%s）", provider)
            except Exception as e:  # noqa: BLE001
                logger.warning("ChatOpenAI 构造失败：%s → 尝试 httpx 适配器", e)

            # ② httpx 适配器（复用 OpenAICompatibleProvider）
            adapter = _build_httpx_adapter()
            if adapter is not None:
                logger.info("LLM 注入：httpx OpenAI 兼容适配器（provider=%s）", provider)
                return adapter

        # ③ 降级 mock
        if not _has_real_api_key():
            logger.info("未配置 LLM_API_KEY，%s 降级 mock FakeListLLM", provider)
        else:
            logger.warning("%s LLM 构造全部失败，降级 mock FakeListLLM", provider)
        return self._safe_fake(provider)

    def _build_anthropic(self) -> Any:
        if _has_real_api_key():
            try:
                from langchain_anthropic import ChatAnthropic  # type: ignore

                settings = get_settings()
                llm = ChatAnthropic(
                    model=settings.llm_default_model or "claude-3-5-sonnet-20241022",
                    anthropic_api_key=settings.llm_api_key.get_secret_value(),
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                )
                logger.info("LLM 注入：langchain_anthropic.ChatAnthropic（model=%s）",
                            settings.llm_default_model)
                return llm
            except ImportError:
                logger.info("未安装 langchain_anthropic，anthropic 降级 mock")
            except Exception as e:  # noqa: BLE001
                logger.warning("ChatAnthropic 构造失败：%s → 降级 mock", e)
        else:
            logger.info("未配置 LLM_API_KEY，anthropic 降级 mock FakeListLLM")
        return self._safe_fake("anthropic")

    @staticmethod
    def _safe_fake(provider: str) -> Any:
        try:
            return _build_fake_llm()
        except Exception:  # noqa: BLE001  langchain 完全不可用
            return _NullLLM()


class _NullLLM:
    """langchain 完全缺失时的兜底（无第三方依赖）。

    LCTBusinessChain 在 langchain 不可用时本就会降级 MockBusinessChain，
    正常不会走到这里；仅作为注入器自身的最终防线。
    """

    backend_name = "null"

    def __call__(self, prompt: str, *_, **__) -> str:
        return _MOCK_RESPONSES[0]

    def predict(self, prompt: str, *_, **__) -> str:
        return _MOCK_RESPONSES[0]


_injector: LLMInjector | None = None
_injector_lock = threading.Lock()


def get_injector() -> LLMInjector:
    """全局 LLMInjector 单例。"""
    global _injector
    if _injector is None:
        with _injector_lock:
            if _injector is None:
                _injector = LLMInjector()
    return _injector


def reset_injector() -> None:
    """重置单例缓存（测试用）。"""
    global _injector
    with _injector_lock:
        _injector = None


__all__ = ["LLMInjector", "get_injector", "reset_injector", "ProviderName"]
