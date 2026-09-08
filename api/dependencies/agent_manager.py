"""AgentManager：FastAPI 层的智能体 DI 容器。

设计原则（4c O1, 4d D1）：
- 实现 4c ``AgentManagerProtocol``（get / list_for_tenant / shutdown）；
- 按 (tenant_id, agent_name) 缓存智能体实例，避免重复构造；
- 4d 不强制注入到 A2A registry（保持 A2A registry 与 AgentManager 互不耦合）；
- 工厂函数 fail-fast：缺包或工厂缺失即抛 500（避免静默回退到 mock）。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from common.constants import AgentName
from common.exceptions import AppException

logger = logging.getLogger("api.dependencies.agent_manager")


# =====================================================
# 异常
# =====================================================
class AgentManagerError(AppException):
    """AgentManager 内部异常。"""

    code = "50001"
    http_status = 500


# =====================================================
# 智能体工厂
# =====================================================
def _create_agent(name: str, tenant_id: str) -> Any:
    """根据 name 构造业务智能体。"""
    if name == AgentName.SAFETY_AUDIT.value:
        from agents.safety_audit_agent import make_safety_audit_agent

        return make_safety_audit_agent(tenant_id=tenant_id)
    if name == AgentName.COMPLIANCE.value:
        from agents.compliance_agent import make_compliance_agent

        return make_compliance_agent(tenant_id=tenant_id)
    if name == AgentName.SITE_MONITOR.value:
        from agents.site_monitor_agent import make_site_monitor_agent

        return make_site_monitor_agent(tenant_id=tenant_id)
    raise AgentManagerError(
        f"未知智能体: {name}", details={"name": name, "tenant_id": tenant_id}
    )


# =====================================================
# AgentManager
# =====================================================
class AgentManager:
    """按 (tenant_id, agent_name) 缓存智能体实例。"""

    def __init__(self) -> None:
        self._instances: dict[tuple[str, str], Any] = {}
        self._lock = asyncio.Lock()
        # 业务智能体白名单（4d 阶段不开放编排器作为 HTTP 调用目标）
        self._supported: tuple[str, ...] = (
            AgentName.SAFETY_AUDIT.value,
            AgentName.COMPLIANCE.value,
            AgentName.SITE_MONITOR.value,
        )

    # ---------- Protocol ----------
    async def get(self, name: str, tenant_id: str) -> Any:
        if name not in self._supported:
            raise AgentManagerError(
                f"智能体不在白名单: {name}",
                details={"supported": list(self._supported)},
            )
        key = (tenant_id, name)
        if key in self._instances:
            return self._instances[key]
        async with self._lock:
            if key not in self._instances:
                try:
                    self._instances[key] = _create_agent(name, tenant_id)
                except AppException:
                    raise
                except Exception as e:  # noqa: BLE001
                    raise AgentManagerError(
                        f"智能体构造失败: {name}",
                        details={"name": name, "tenant_id": tenant_id, "error": str(e)},
                    ) from e
        return self._instances[key]

    def list_for_tenant(self, tenant_id: str) -> list[Any]:
        return [a for (t, _), a in self._instances.items() if t == tenant_id]

    def list_supported(self) -> list[str]:
        return list(self._supported)

    async def shutdown(self) -> None:
        async with self._lock:
            self._instances.clear()

    # ---------- 辅助 ----------
    def stats(self) -> dict[str, int]:
        return {
            "total_instances": len(self._instances),
            "tenants": len({t for (t, _) in self._instances.keys()}),
        }


# =====================================================
# 全局单例 + 测试钩子
# =====================================================
_manager: AgentManager | None = None
_manager_lock = threading.Lock()


def init_agent_manager() -> AgentManager:
    """进程级单例初始化（lifespan 中调用）。"""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = AgentManager()
        return _manager


def get_agent_manager() -> AgentManager:
    """获取单例。未初始化时自动初始化（保证 FastAPI 启动前也能使用）。"""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = AgentManager()
    return _manager


def reset_agent_manager() -> None:
    """重置单例（仅测试使用）。"""
    global _manager
    with _manager_lock:
        if _manager is not None:
            # 不 await shutdown（同步上下文）；新 AgentManager 隔离即可
            _manager = None


__all__ = [
    "AgentManager",
    "AgentManagerError",
    "init_agent_manager",
    "get_agent_manager",
    "reset_agent_manager",
]
