"""策略引擎：RBAC 快路径 + ABAC 后置（6b.2 升级）。

串联模式：
1. RBAC 先判定（role × resource × action 矩阵）；
2. RBAC 拒绝 → 直接返回 False，不走 ABAC（减少开销）；
3. RBAC 通过 → ABAC 追加（时间窗 / 敏感度 / 租户隔离 / 自定义规则）；
4. ABAC 全规则 AND 逻辑，任一 False → deny。

5c 阶段：role-based（RBAC）。
6b.2：扩展为 ABAC（加入 subject/resource/environment 属性）。
"""

from __future__ import annotations

import logging
from typing import Any

from core.security.permissions import check_permission

logger = logging.getLogger("core.security.policies")


class PolicyEngine:
    """策略引擎：评估访问请求是否允许。

    6b.2 升级为 RBAC → ABAC 双引擎串联：
    - RBAC 快路径：矩阵查找 O(1)，拒绝时直接返回；
    - ABAC 后置：仅在 RBAC 通过后追加，基于属性评估。
    """

    def evaluate(
        self,
        role: str,
        resource: str,
        action: str,
        *,
        tenant_id: str = "",
        context: dict[str, Any] | None = None,
        subject_attrs: dict[str, Any] | None = None,
        resource_attrs: dict[str, Any] | None = None,
        env_attrs: dict[str, Any] | None = None,
    ) -> bool:
        """评估访问请求。

        返回 True 表示策略允许；False 表示拒绝。

        参数：
        - role/resource/action: RBAC 三元组
        - tenant_id: 请求方租户 ID（兼容旧接口）
        - context: 兼容旧接口的上下文 dict（提取 tenant_id 做隔离）
        - subject_attrs: ABAC 主体属性（role, tenant_id, clearance, ...）
        - resource_attrs: ABAC 资源属性（tenant_id, sensitivity, ...）
        - env_attrs: ABAC 环境属性（now, time_window_enabled, ...）
        """
        # 1) RBAC 快路径
        if not check_permission(role, resource, action):
            logger.debug("RBAC 拒绝: %s/%s/%s", role, resource, action)
            return False

        # 2) 兼容旧接口：context 中的 tenant_id 隔离检查
        ctx = context or {}
        ctx_tenant = ctx.get("tenant_id", "")
        if ctx_tenant and tenant_id and ctx_tenant != tenant_id:
            return False

        # 3) ABAC 后置（仅在提供了 subject_attrs 或 resource_attrs 时触发）
        if subject_attrs is None and resource_attrs is None:
            # 无 ABAC 属性 → 仅 RBAC 结果
            return True

        # 构建 ABAC 属性
        subject = dict(subject_attrs or {})
        subject.setdefault("role", role)
        subject.setdefault("tenant_id", tenant_id or ctx_tenant)

        res = dict(resource_attrs or {})
        res.setdefault("resource", resource)

        env = dict(env_attrs or {})

        # 4) 调用 ABAC 引擎
        from core.security.abac_engine import get_abac_engine

        return get_abac_engine().evaluate(subject, res, action, env)


_engine: PolicyEngine | None = None


def get_policy_engine() -> PolicyEngine:
    global _engine
    if _engine is None:
        _engine = PolicyEngine()
    return _engine


def reset_policy_engine() -> None:
    """测试用：重置单例。"""
    global _engine
    _engine = None


__all__ = ["PolicyEngine", "get_policy_engine", "reset_policy_engine"]
