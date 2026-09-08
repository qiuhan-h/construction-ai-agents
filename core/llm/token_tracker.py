"""Token 用量与成本统计。

- 按模型记录每次调用的 prompt/completion token 与费用；
- 支持按调用方（caller：智能体/任务 ID）聚合，用于成本归因；
- 单价表可运行时注册（不同供应商/计费周期不同），未注册模型只记量不计费；
- 线程安全（LLM 调用可能来自多线程 worker）。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime

from common.timeutils import utc_now

# 默认单价：元 / 1K tokens（input, output），仅用于量级估算。
# 模型列表不硬编码供应商具体名称，留空由 register_pricing 在启动时按实际模型注入
_DEFAULT_PRICING: dict[str, tuple[float, float]] = {}


@dataclass
class TokenUsageRecord:
    """一次 LLM 调用的用量记录。"""

    model: str
    prompt_tokens: int
    completion_tokens: int
    cost: float
    caller: str | None = None
    timestamp: datetime = field(default_factory=utc_now)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class TokenTracker:
    """进程内用量累加器（持久化留待可观测性模块接入）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: list[TokenUsageRecord] = []
        self._pricing: dict[str, tuple[float, float]] = dict(_DEFAULT_PRICING)

    def register_pricing(self, model: str, input_price: float, output_price: float) -> None:
        """注册/覆盖模型单价（元 / 1K tokens）。"""
        with self._lock:
            self._pricing[model] = (input_price, output_price)

    def record(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        caller: str | None = None,
    ) -> float:
        """记录一次调用，返回本次费用（元）。"""
        with self._lock:
            in_price, out_price = self._pricing.get(model, (0.0, 0.0))
            cost = (prompt_tokens / 1000) * in_price + (completion_tokens / 1000) * out_price
            self._records.append(
                TokenUsageRecord(
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost=cost,
                    caller=caller,
                )
            )
        return cost

    def total(
        self,
        model: str | None = None,
        caller: str | None = None,
    ) -> dict[str, float]:
        """聚合统计：可选按模型/调用方过滤。"""
        with self._lock:
            records = [
                r
                for r in self._records
                if (model is None or r.model == model)
                and (caller is None or r.caller == caller)
            ]
        return {
            "calls": float(len(records)),
            "prompt_tokens": float(sum(r.prompt_tokens for r in records)),
            "completion_tokens": float(sum(r.completion_tokens for r in records)),
            "total_tokens": float(sum(r.total_tokens for r in records)),
            "cost": round(sum(r.cost for r in records), 6),
        }

    def reset(self) -> None:
        """清空记录（测试用）。"""
        with self._lock:
            self._records.clear()


_tracker = TokenTracker()


def get_token_tracker() -> TokenTracker:
    """全局用量统计单例。"""
    return _tracker
