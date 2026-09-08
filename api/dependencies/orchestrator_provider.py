"""编排器 DI 容器：把 core.orchestrator.Orchestrator 注入到 FastAPI 路由。

设计要点：
- 4d 让 API 路由直接调 Orchestrator（trigger workflow / list / get_run）；
- 单例持有 task_queue + agent_manager + workflow_engine；
- lifespan 启动 Orchestrator，订阅事件；停止时 unsub。
- 测试可通过 ``reset_orchestrator`` 强制重新构造。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

logger = logging.getLogger("api.dependencies.orchestrator_provider")


# =====================================================
# 全局单例
# =====================================================
_orch: Any | None = None
_orch_lock = threading.Lock()
_init_lock = asyncio.Lock()


def init_orchestrator(
    *,
    task_queue: Any | None = None,
    agent_manager: Any | None = None,
    workflow_engine: Any | None = None,
    event_bus: Any | None = None,
) -> Any:
    """构造并启动 Orchestrator 单例（lifespan 调用）。

    任一依赖为 None 时使用默认实现：
    - task_queue   -> services.task_queue.TaskQueue()
    - agent_manager-> api.dependencies.agent_manager.get_agent_manager()
    - workflow_engine -> core.orchestrator.workflow_engine.WorkflowEngine()
    - event_bus    -> core.events.get_event_bus()
    """
    global _orch
    from core.events import get_event_bus
    from core.orchestrator import Orchestrator, WorkflowEngine
    from services.task_queue import TaskQueue

    from api.dependencies.agent_manager import get_agent_manager

    with _orch_lock:
        tq = task_queue or TaskQueue()
        am = agent_manager or get_agent_manager()
        we = workflow_engine or WorkflowEngine()
        eb = event_bus or get_event_bus()
        _orch = Orchestrator(
            task_queue=tq,
            agent_manager=am,
            workflow_engine=we,
            event_bus=eb,
        )
    # 启动：订阅事件（异步，fire-and-forget）
    try:
        # L3 修补：get_event_loop() 在 3.12 已弃用且无线程 loop 时行为不明确；
        # get_running_loop() 仅在存在运行中 loop 时成功，语义更精确。
        asyncio.get_running_loop().create_task(_orch.start())
    except RuntimeError:
        # 没有运行中的 loop（同步上下文）时 new 一个跑完启动
        asyncio.run(_orch.start())
    return _orch


def get_orchestrator() -> Any:
    """获取单例 Orchestrator。"""
    global _orch
    if _orch is None:
        with _orch_lock:
            if _orch is None:
                init_orchestrator()
    return _orch


async def shutdown_orchestrator() -> None:
    """停止 Orchestrator（lifespan 关闭阶段调用）。"""
    global _orch
    if _orch is None:
        return
    try:
        await _orch.stop()
    except Exception as e:  # noqa: BLE001
        logger.warning("Orchestrator 停止失败: %s", e)
    with _orch_lock:
        _orch = None


def reset_orchestrator() -> None:
    """重置单例（仅测试）。不会 await stop。"""
    global _orch
    with _orch_lock:
        _orch = None


__all__ = [
    "init_orchestrator",
    "get_orchestrator",
    "shutdown_orchestrator",
    "reset_orchestrator",
]
