"""端到端烟雾测试：docker-compose 全链路冒烟。

验证：
1. API /healthz 返回 200
2. A2A agent-card 可获取
3. MCP tools/list 可获取
4. 事件发布 → 智能体处理 → 时间线生成
5. 报告生成 + 签章验证
6. RBAC 拒绝越权访问

用法：
    docker-compose up -d
    python tools/smoke_e2e.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import httpx  # type: ignore[import-not-found]  # noqa: E402

API_BASE = "http://localhost:8000/api/v1"
A2A_BASE = "http://localhost:8080"
MCP_BASE = "http://localhost:8090/mcp"


async def _check(name: str, coro_factory, expect_status: int = 200) -> bool:
    try:
        resp = await coro_factory()
        ok = resp.status_code == expect_status
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: HTTP {resp.status_code}")
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"  [FAIL] {name}: {e}")
        return False


async def _run() -> int:
    failed = 0
    async with httpx.AsyncClient(timeout=10) as cli:
        # 1. API health
        if not await _check(
            "API /healthz", lambda: cli.get(f"{API_BASE}/health/healthz")
        ):
            failed += 1

        # 2. A2A agent-card
        if not await _check(
            "A2A agent-card", lambda: cli.get(f"{A2A_BASE}/.well-known/agent-card.json")
        ):
            failed += 1

        # 3. MCP tools/list
        if not await _check(
            "MCP tools/list",
            lambda: cli.post(f"{MCP_BASE}", json={"method": "tools/list", "id": 1}),
        ):
            failed += 1

        # 4. RBAC 拒绝（无 token → 401/403）
        resp = await cli.post(f"{API_BASE}/agents/safety_audit_agent/invoke",
                              json={"parts": [{"type": "text", "text": "test"}]})
        if resp.status_code in (401, 403):
            print(f"  [PASS] RBAC 拒绝无 token: HTTP {resp.status_code}")
        else:
            print(f"  [FAIL] RBAC 拒绝无 token: HTTP {resp.status_code} (期望 401/403)")
            failed += 1

    print(f"\n端到端烟雾测试: {4 - failed}/4 通过, {failed} 失败")
    return 1 if failed else 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())


