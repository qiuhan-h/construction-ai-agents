"""LangChain 业务链子包（5b.6 实做，依 shu_zhuang_tu.txt 第 184-188 行）。

子包结构（对齐 ``shu_zhuang_tu.txt``）::

    chains/
      ├── __init__.py           本文件：协议 + 公共组件 + 工厂注册表
      ├── safety_chain.py      安全审核链（方案/图纸/结构 → verdict/findings/suggestions）
      ├── compliance_chain.py   合规校验链（法规比对 → passed/violations）
      └── monitoring_chain.py   监控分析链（告警 → action/reasoning/notify）

设计（5b.6 边界）：
- 本 ``__init__.py`` 只做"协议 + 共享组件 + 工厂注册表"，
  具体 chain 的 prompt + 注册调用在子模块；
- ``BusinessChain`` 协议：``name`` + ``async run(tenant_id, payload) -> dict``；
- ``MockBusinessChain``：缺 langchain SDK 时降级；按 name 分支返回结构化 mock；
- ``LCTBusinessChain``：真 LangChain LLMChain 封装，缺包自动降级；
- ``register_chain / get_chain / list_chains``：工厂注册表 + 单例 cache。

不依赖：
- 不引入额外第三方包（langchain 在调用时再 import；缺包不抛 ImportError）；
- 不接向量库（向量库在 5b.2，由调用方注入）。

入口约定（5b.6 推荐）::

    from core.langchain.chains import get_chain, BusinessChain
    chain = get_chain("safety_audit")
    out = await chain.run(tenant_id, {"document": "..."})
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

ChainName = Literal["safety_audit", "compliance", "site_monitor"]
_VALID_NAMES: set[str] = {"safety_audit", "compliance", "site_monitor"}


# =====================================================
# 协议
# =====================================================
@runtime_checkable
class BusinessChain(Protocol):
    """业务链统一协议。"""

    name: str

    async def run(
        self,
        tenant_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """执行链，返回结构化 dict。"""
        ...


# =====================================================
# 共享 payload
# =====================================================
@dataclass
class ChainContext:
    """链式调用上下文（payload 容器）。"""

    tenant_id: str
    inputs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


# =====================================================
# Mock 实现（缺 langchain 时降级；测试也用）
# 子模块（safety_chain / compliance_chain / monitoring_chain）会
# 通过 ``register_mock_response`` 注册各自的 mock 返回值。
# =====================================================
_MOCK_RESPONSES: dict[str, Callable[[str], dict[str, Any]]] = {}


def register_mock_response(
    name: str,
    factory: Callable[[str], dict[str, Any]],
) -> None:
    """注册 chain 的 mock 响应工厂（子模块 import 时调用）。

    Args:
        name: chain 名（safety_audit / compliance / site_monitor）。
        factory: 接受 ``tenant_id`` 返回 mock dict 的可调用对象。
    """
    _MOCK_RESPONSES[name] = factory


class MockBusinessChain:
    """不依赖任何第三方 SDK 的兜底 chain。

    行为：按 ``name`` 从 ``_MOCK_RESPONSES`` 取注册的 mock 响应工厂；
    缺失时返回通用 mock。真实 LLM 调用由 ``LCTBusinessChain`` 提供。
    """

    backend_name: str = "mock"

    def __init__(self, name: str) -> None:
        if name not in _VALID_NAMES:
            raise ValueError(f"未知 chain name: {name}")
        self.name = name

    async def run(
        self,
        tenant_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        factory = _MOCK_RESPONSES.get(self.name)
        if factory is not None:
            resp = factory(tenant_id)
            resp.setdefault("tenant_id", tenant_id)
            resp.setdefault("backend", self.backend_name)
            return resp
        # 兜底通用 mock
        return {
            "ok": True,
            "tool": self.name,
            "backend": self.backend_name,
            "mock": True,
            "echo": dict(payload),
            "tenant_id": tenant_id,
        }


# =====================================================
# LangChain 真实现（缺包自动降级到 Mock）
# =====================================================
def _langchain_available() -> bool:
    try:
        import langchain  # type: ignore  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


class LCTBusinessChain:
    """基于 LangChain LLMChain 的真业务链。

    缺包时**绝不抛 ImportError**——构造时检测到没装 langchain，
    自动降级为 MockBusinessChain，但属性 / 接口保持一致。
    """

    def __init__(self, name: str, *, model: str | None = None) -> None:
        if name not in _VALID_NAMES:
            raise ValueError(f"未知 chain name: {name}")
        self.name = name
        self._model = model or os.environ.get("LLM_MODEL", "gpt-3.5-turbo")
        self._impl: BusinessChain
        if not _langchain_available():
            logger.warning(
                "langchain SDK 未安装 → %s chain 降级为 MockBusinessChain",
                name,
            )
            self._impl = MockBusinessChain(name)
            self.backend_name = "mock"
            return
        # 真 LangChain 路径
        # PromptTemplate：langchain 1.0+ 在 langchain_core.prompts，旧版在 langchain.prompts
        prompt_cls = None
        for _pt_path in ("langchain_core.prompts", "langchain.prompts"):
            try:
                _pt_mod = __import__(_pt_path, fromlist=["PromptTemplate"])
                prompt_cls = getattr(_pt_mod, "PromptTemplate")
                break
            except Exception:  # noqa: BLE001
                continue
        if prompt_cls is None:
            logger.warning("langchain PromptTemplate 不可用：%s chain 降级为 MockBusinessChain", name)
            self._impl = MockBusinessChain(name)
            self.backend_name = "mock"
            return
        self._prompt_cls = prompt_cls

        # 执行模式：旧版 LLMChain（langchain <1.0）或新版 LCEL（prompt | llm，1.0+）
        self._llm_chain_cls = None
        self._use_lcel = False
        try:
            from langchain.chains import LLMChain  # type: ignore

            self._llm_chain_cls = LLMChain
            self.backend_name = "langchain"
        except Exception:  # noqa: BLE001  langchain 1.0 移除 LLMChain → 走 LCEL
            self._use_lcel = True
            self.backend_name = "langchain-lcel"
        self._llm = None  # 实际 LLM 客户端由注入器提供；本类不直连
        self._impl = self  # 真链路

    async def run(
        self,
        tenant_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if isinstance(self._impl, MockBusinessChain):
            return await self._impl.run(tenant_id, payload)
        # 真 LangChain 路径：用 LLMChain 生成（同步调用 → 放线程池）
        import asyncio  # noqa: F401
        import json

        # 6a.3：LLM 实例由注入器统一创建（provider=mock/openai/anthropic/vllm，
        # 由 settings.llm_provider 控制）。缺失第三方 SDK 或未配置 API Key 时，
        # 注入器自动降级为本地占位 LLM，保证链路可跑通；此处不再硬编码占位模型。
        try:
            from core.llm.injector import get_injector

            llm = get_injector().get_llm()
        except Exception as e:  # noqa: BLE001  注入器自身异常不应炸掉链路
            logger.warning("LLM 注入失败（%s）→ fallback MockBusinessChain", e)
            return await MockBusinessChain(self.name).run(tenant_id, payload)

        # prompt 由子模块通过 register_prompt 注册
        prompt_template = _PROMPTS.get(self.name, "{document}")
        prompt = self._prompt_cls.from_template(prompt_template)  # type: ignore
        # P0-3 修补：只传 prompt 模板声明的变量，避免 _validate_inputs 抛
        # ValueError（如模板需要 {project_name}/{artifact_kind}/{document}
        # 但调用方只传 {document}）。缺失变量用空串填充。
        expected = set(getattr(prompt, "input_variables", []) or ["document"])
        if expected == {"document"}:
            # 模板只用 {document}：把整个 payload 序列化进 document
            inputs = {"document": payload.get("document") or
                      json.dumps(payload, ensure_ascii=False, default=str)}
        else:
            # 多变量模板：按 expected 取，缺失给空串
            inputs = {k: payload.get(k, "") for k in expected}

        if self._use_lcel:
            # langchain 1.0+ LCEL：runnable = prompt | llm
            try:
                runnable = prompt | llm
                result = await asyncio.to_thread(runnable.invoke, inputs)
                # ChatModel 返回 AIMessage（有 .content）；占位/纯文本 LLM 返回 str
                text = getattr(result, "content", None) or str(result)
            except Exception as e:  # noqa: BLE001
                logger.warning("LCEL 链执行失败（%s）→ fallback mock", e)
                return await MockBusinessChain(self.name).run(tenant_id, payload)
        else:
            # 旧版 LLMChain
            chain = self._llm_chain_cls(llm=llm, prompt=prompt)
            text = await asyncio.to_thread(chain.run, **inputs)
        return {
            "raw": text,
            "tenant_id": tenant_id,
            "backend": self.backend_name,
        }


# =====================================================
# Prompt 模板注册表（子模块 import 时填充）
# =====================================================
_PROMPTS: dict[str, str] = {}


def register_prompt(name: str, prompt: str) -> None:
    """注册 chain 的 prompt 模板（子模块 import 时调用）。"""
    _PROMPTS[name] = prompt


# =====================================================
# 注册表 + 工厂
# =====================================================
_ChainFactory = Callable[[], BusinessChain]
_REGISTRY: dict[str, _ChainFactory] = {}
_registry_lock = threading.RLock()
_default_cache: dict[str, BusinessChain] = {}


def register_chain(name: str, factory: _ChainFactory) -> None:
    """注册自定义 chain 工厂（5b.6 公共扩展点）。

    子模块（safety_chain / compliance_chain / monitoring_chain）
    在 import 时调用本函数完成默认注册。
    """
    with _registry_lock:
        _REGISTRY[name] = factory
        _default_cache.pop(name, None)


def _ensure_default_registry() -> None:
    """惰性填充默认注册表（避免 import 时强依赖 langchain）。

    触发子模块 import：子模块各自调用 ``register_chain`` + ``register_prompt``
    + ``register_mock_response``。
    """
    if _REGISTRY:
        return
    with _registry_lock:
        if _REGISTRY:
            return
        # 触发子模块 import（子模块内部完成注册）
        try:
            from core.langchain.chains import safety_chain as _safety  # type: ignore  # noqa: F401
            from core.langchain.chains import compliance_chain as _comp  # type: ignore  # noqa: F401
            from core.langchain.chains import monitoring_chain as _mon  # type: ignore  # noqa: F401
        except ImportError as e:
            logger.warning("chains 子模块 import 失败，仅保留 MockBusinessChain 兜底: %s", e)
        except Exception as e:  # noqa: BLE001
            # L6 修补：子模块注册期还可能抛 ImportError 以外的异常
            # （属性/类型/依赖版本不匹配等）；注册表必须存活并落到下方
            # 兜底工厂，不能让单个子模块的注册错误炸掉整个 chains 包。
            logger.warning("chains 子模块注册异常，回退默认 LCTBusinessChain: %r", e)
        # 兜底：子模块未注册的，注册默认 LCTBusinessChain 工厂
        for name in _VALID_NAMES:
            if name not in _REGISTRY:
                def _factory(_n: str = name) -> BusinessChain:
                    return LCTBusinessChain(_n)
                _REGISTRY[name] = _factory


def get_chain(
    name: str,
    *,
    use_cache: bool = True,
) -> BusinessChain:
    """按 name 获取业务链。

    异常：
    - ``ValueError``：name 不在白名单（防止拼写错静默 fallback）。
    - ``ModuleNotFoundError``：底层 chain 工厂抛（目前实现永不抛）。
    """
    if name not in _VALID_NAMES:
        raise ValueError(
            f"未知 chain name: {name}；白名单={sorted(_VALID_NAMES)}"
        )
    _ensure_default_registry()
    with _registry_lock:
        if use_cache and name in _default_cache:
            return _default_cache[name]
        if name not in _REGISTRY:
            raise ValueError(f"chain '{name}' 未注册")
        chain = _REGISTRY[name]()
        _default_cache[name] = chain
        return chain


def list_chains() -> list[str]:
    """返回已注册的 chain 名。"""
    _ensure_default_registry()
    with _registry_lock:
        return sorted(_REGISTRY.keys())


def reset_default_chains() -> None:
    """重置单例 cache（测试用）。"""
    with _registry_lock:
        _default_cache.clear()


def langchain_available() -> bool:
    """暴露给业务层 / 健康检查。"""
    return _langchain_available()


__all__ = [
    "BusinessChain",
    "ChainContext",
    "ChainName",
    "LCTBusinessChain",
    "MockBusinessChain",
    "get_chain",
    "langchain_available",
    "list_chains",
    "register_chain",
    "register_mock_response",
    "register_prompt",
    "reset_default_chains",
]
