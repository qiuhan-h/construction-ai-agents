"""初始化智能体：每租户注册到 AgentManager + 同步 A2A AgentRegistry。

设计（4d D7 幂等）：
- 不实际注入"租户"概念到全局 registry（4d 不要求）；
- 核心动作：对每个白名单智能体调用 ``make_xxx_agent(tenant_id=...)``，
  通过 AgentManager 触发懒加载（验证工厂可用），并打印卡信息。
- 默认同时注册到 ``core.a2a.server.get_registry()``，方便 A2A 路由也能查到。

用法：
    python scripts/init_agents.py --tenant tnt_demo
    python scripts/init_agents.py --tenant tnt_demo --tenants tnt_a,tnt_b
    python scripts/init_agents.py --list       # 仅列出白名单

退出码：
    0  全部成功
    1  任意一个智能体工厂失败
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import Any

# 允许以 `python scripts/init_agents.py` 形式直接运行
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from api.dependencies.agent_manager import (  # noqa: E402
    AgentManager,
    AgentManagerError,
    get_agent_manager,
)
from common.constants import AgentName  # noqa: E402

logger = logging.getLogger("scripts.init_agents")

# 业务智能体白名单（与 AgentManager._supported 对齐）
SUPPORTED_AGENTS: tuple[str, ...] = (
    AgentName.SAFETY_AUDIT.value,
    AgentName.COMPLIANCE.value,
    AgentName.SITE_MONITOR.value,
)


# =====================================================
# 注册到全局 A2A AgentRegistry（可选，不阻断主流程）
# =====================================================
def _register_to_a2a_registry(agent: Any) -> None:
    """把构造好的 agent 注入到 A2A AgentRegistry，方便 A2A 路由可用。"""
    try:
        from core.a2a.server import get_registry
    except Exception as e:  # noqa: BLE001
        logger.debug("A2A registry 不可用（跳过）: %s", e)
        return
    try:
        registry = get_registry()
        # AgentManager 内已经做过 register（auto_register=True），重复注册会被警告
        # 因此这里仅校验存在性，不强制再 register
        if agent.name not in {a.name for a in registry.list_agents()}:
            registry.register(agent)
    except Exception as e:  # noqa: BLE001
        logger.warning("同步到 A2A registry 失败（忽略）: %s", e)


# =====================================================
# 核心流程
# =====================================================
async def init_tenant(mgr: AgentManager, tenant_id: str) -> dict[str, Any]:
    """对单个租户触发所有白名单智能体的懒加载。"""
    results: dict[str, Any] = {"tenant_id": tenant_id, "agents": {}, "ok": True}
    for name in SUPPORTED_AGENTS:
        try:
            agent = await mgr.get(name, tenant_id)
        except AgentManagerError as e:
            results["ok"] = False
            results["agents"][name] = {
                "ok": False,
                "code": e.code,
                "message": e.message,
            }
            logger.error("租户 %s 智能体 %s 初始化失败: %s", tenant_id, name, e.message)
            continue
        except Exception as e:  # noqa: BLE001
            results["ok"] = False
            results["agents"][name] = {"ok": False, "error": str(e)}
            logger.exception("租户 %s 智能体 %s 构造异常", tenant_id, name)
            continue
        # 同步 A2A registry（不阻塞主流程）
        _register_to_a2a_registry(agent)
        results["agents"][name] = {
            "ok": True,
            "version": getattr(agent, "version", None),
            "skills": [s.skill_id for s in getattr(agent, "skills", [])],
        }
        logger.info(
            "✓ 已注册: %s tenant=%s version=%s skills=%s",
            name, tenant_id, agent.version, len(results["agents"][name]["skills"]),
        )
    return results


async def async_main(args: argparse.Namespace) -> int:
    if args.list:
        print("白名单智能体（AgentManager._supported）:")
        for n in SUPPORTED_AGENTS:
            print(f"  - {n}")
        return 0

    mgr = get_agent_manager()

    tenants = [t.strip() for t in (args.tenants or args.tenant).split(",") if t.strip()]
    if not tenants:
        print("未提供 --tenant / --tenants", file=sys.stderr)
        return 1

    overall_ok = True
    summary: list[dict[str, Any]] = []
    for t in tenants:
        r = await init_tenant(mgr, t)
        summary.append(r)
        if not r["ok"]:
            overall_ok = False
        print(
            f"[{t}] 智能体数={len(r['agents'])} ok={r['ok']} "
            f"supported={list(r['agents'].keys())}"
        )

    print()
    print("=" * 60)
    print(f"初始化完成: tenants={len(summary)} overall_ok={overall_ok}")
    print(f"  白名单: {list(SUPPORTED_AGENTS)}")
    return 0 if overall_ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="阶段 4d：初始化智能体（每租户）")
    parser.add_argument(
        "--tenant",
        default="tnt_default",
        help="单租户 ID（默认 tnt_default）",
    )
    parser.add_argument(
        "--tenants",
        default=None,
        help="多租户 ID，逗号分隔（与 --tenant 互斥）",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="仅打印白名单并退出",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    rc = asyncio.run(async_main(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
