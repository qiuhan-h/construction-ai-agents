"""权限矩阵：role × resource → allowed actions。

F7 原则：默认拒绝 + 最小权限；未声明的 role/resource 组合 → deny。
"""

from __future__ import annotations

from typing import Any

# 角色枚举
ROLES = ("admin", "engineer", "reviewer", "viewer")

# 资源枚举
RESOURCES = (
    "safety_audit", "compliance", "site_monitor",
    "report", "gis", "agent_management", "workflow",
)

# 权限矩阵：role → {resource → set(actions)}
# None = 全部权限（admin）；空 set = 无权限
PERMISSIONS: dict[str, dict[str, set[str] | None]] = {
    "admin": {res: None for res in RESOURCES},  # 全权限
    "engineer": {
        "safety_audit": {"invoke", "read", "list"},
        "compliance": {"invoke", "read", "list"},
        "site_monitor": {"invoke", "read", "list"},
        "report": {"read", "list", "download"},
        "gis": {"read"},
        "agent_management": {"invoke", "read"},
        "workflow": {"trigger", "read"},
    },
    "reviewer": {
        "safety_audit": {"read", "list"},
        "compliance": {"read", "list"},
        "site_monitor": {"read", "list"},
        "report": {"read", "list", "download", "approve"},
        "gis": {"read"},
        "agent_management": {"read"},
        "workflow": {"read"},
    },
    "viewer": {
        "safety_audit": {"list"},
        "compliance": {"list"},
        "site_monitor": {"list"},
        "report": {"list"},
        "gis": {"read"},
        "agent_management": set(),
        "workflow": set(),
    },
}


def check_permission(role: str, resource: str, action: str) -> bool:
    """检查 role 对 resource 是否有 action 权限。

    返回 True 表示允许；False 表示拒绝（默认拒绝）。
    """
    perms = PERMISSIONS.get(role, {})
    actions = perms.get(resource)
    if actions is None:
        return True  # admin 全权限
    return action in actions


def list_permissions(role: str) -> dict[str, set[str] | None]:
    """返回 role 的完整权限矩阵（用于调试 / UI 展示）。"""
    return PERMISSIONS.get(role, {})
