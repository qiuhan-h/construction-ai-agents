"""阶段六·子阶段 6d 验收：Dockerfile.edge + BIM 连接器 API。

验收项：
- [A] scan_stage6d 文件清单全部就位
- [B] BIM API 端点：3 端点 200（TR-10.1/10.2/10.3）
- [C] BIM Schema 字段精简（TR-10.4）
- [D] Dockerfile.edge 多阶段 + healthcheck + EDGE_MODE + 非 root（TR-10.5）
- [E] BIM 连接器降级：缺凭据 → mock 不报错（TR-10.6）
- [F] 进度偏差检测：delayed/ahead 计数 + ProgressTracker（TR-10.7）
- [G] 回归：verify_stage1/2/3 + 6a + 6b + 6c 无回归

执行：python verify_stage6d.py
退出码：0 = 全部通过；非 0 = 有失败项。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3] / "construction-ai-agents"
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PASSED = 0
FAILED = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
    else:
        FAILED += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


# =====================================================
# [A] 文件清单
# =====================================================
def check_scan() -> None:
    print("\n[A] 文件清单 scan_stage6d")
    r = subprocess.run(
        [sys.executable, str(TOOLS_DIR.parent / "scan" / "scan_stage6d.py")],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    check("scan_stage6d 退出码 0", r.returncode == 0,
          "全部文件就位非空" if r.returncode == 0 else "存在缺失/空壳")


# =====================================================
# [B] BIM API 端点
# =====================================================
def check_bim_api() -> None:
    print("\n[B] BIM API 端点（TR-10.1/10.2/10.3）")
    from api.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev-tnt_v6d-user1"}

    # TR-10.1: project tree
    resp = client.get("/api/v1/bim/projects/proj-v6d/tree", headers=headers)
    check("GET /bim/projects/{id}/tree → 200（TR-10.1）",
          resp.status_code == 200, f"status={resp.status_code}")
    if resp.status_code == 200:
        tree = resp.json().get("data", [])
        check("tree 返回 list 且含 IfcBuilding",
              isinstance(tree, list) and len(tree) > 0
              and tree[0].get("type") == "IfcBuilding")

    # TR-10.2: element
    resp2 = client.get("/api/v1/bim/elements/elem-v6d", headers=headers)
    check("GET /bim/elements/{id} → 200（TR-10.2）",
          resp2.status_code == 200, f"status={resp2.status_code}")
    if resp2.status_code == 200:
        elem = resp2.json().get("data", {})
        check("element_id 匹配",
              elem.get("element_id") == "elem-v6d")
        check("element 含 properties",
              "properties" in elem)

    # TR-10.3: progress
    resp3 = client.get("/api/v1/bim/progress/proj-v6d", headers=headers)
    check("GET /bim/progress/{id} → 200（TR-10.3）",
          resp3.status_code == 200, f"status={resp3.status_code}")
    if resp3.status_code == 200:
        prog = resp3.json().get("data", {})
        check("progress 含 items 列表",
              isinstance(prog.get("items"), list) and len(prog["items"]) > 0)
        check("progress 含 delayed 计数",
              isinstance(prog.get("delayed"), int) and prog["delayed"] > 0)
        check("progress source = mock",
              prog.get("source") == "mock")


# =====================================================
# [C] BIM Schema 字段精简（TR-10.4）
# =====================================================
def check_bim_schemas() -> None:
    print("\n[C] BIM Schema 字段精简（TR-10.4）")
    from api.schemas.bim_schemas import (
        BIMElement,
        BIMProgressItem,
        BIMProgressResponse,
        BIMProjectTreeNode,
    )

    check("BIMElement 字段 ≤ 5",
          len(BIMElement.model_fields) <= 5, f"{len(BIMElement.model_fields)}")
    check("BIMProgressItem 字段 ≤ 6",
          len(BIMProgressItem.model_fields) <= 6,
          f"{len(BIMProgressItem.model_fields)}")
    check("BIMProgressResponse 字段 ≤ 6",
          len(BIMProgressResponse.model_fields) <= 6,
          f"{len(BIMProgressResponse.model_fields)}")
    check("BIMProjectTreeNode 字段 ≤ 4",
          len(BIMProjectTreeNode.model_fields) <= 4,
          f"{len(BIMProjectTreeNode.model_fields)}")


# =====================================================
# [D] Dockerfile.edge（TR-10.5）
# =====================================================
def check_dockerfile_edge() -> None:
    print("\n[D] Dockerfile.edge（TR-10.5）")
    dockerfile = ROOT / "deployment" / "docker" / "Dockerfile.edge"
    check("Dockerfile.edge 存在", dockerfile.is_file())
    if not dockerfile.is_file():
        return
    content = dockerfile.read_text(encoding="utf-8")

    check("多阶段构建（AS builder）", "AS builder" in content)
    check("FROM python:3.12-slim", "python:3.12-slim" in content)
    check("HEALTHCHECK", "HEALTHCHECK" in content)
    check("EDGE_MODE 环境变量", "EDGE_MODE" in content)
    check("非 root 用户（USER caai）", "USER caai" in content)
    check("单 worker（--workers 1）", "--workers" in content)
    check("uvicorn 入口", "uvicorn" in content and "api.main:app" in content)


# =====================================================
# [E] BIM 连接器降级（TR-10.6）
# =====================================================
def check_bim_degradation() -> None:
    print("\n[E] BIM 连接器降级（TR-10.6）")
    import asyncio

    # BIMConnector mock 模式（强制 _client=None 走 mock 路径）
    from agents.site_monitor_agent.bim_integration import BIMConnector

    conn = BIMConnector(base_url="https://bim.invalid", token=None)
    conn._client = None  # 强制 mock 模式
    tree = asyncio.run(conn.get_project_tree("proj-degrade"))
    check("BIMConnector.get_project_tree mock 不报错",
          isinstance(tree, list) and len(tree) > 0, f"{len(tree)} roots")

    elem = asyncio.run(conn.get_element("elem-degrade"))
    check("BIMConnector.get_element 返回 mock dict",
          isinstance(elem, dict) and "element_id" in elem)

    # BIMRealConnector 占位凭据降级
    from agents.site_monitor_agent.bim_integration import (
        make_bim_real_connector,
    )

    real = make_bim_real_connector(
        client_id="your-client-id", client_secret="xxx", hub_id="",
    )
    check("make_bim_real_connector 占位凭据 → 返回对象（不抛异常）",
          real is not None and hasattr(real, "get_project_tree"))


# =====================================================
# [F] 进度偏差检测（TR-10.7）
# =====================================================
def check_progress_tracker() -> None:
    print("\n[F] 进度偏差检测（TR-10.7）")
    from agents.site_monitor_agent.bim_integration import ProgressTracker

    tracker = ProgressTracker(deviation_threshold=10.0)
    plan = [
        {"element_id": "e1", "name": "梁A", "pct": 80.0},
        {"element_id": "e2", "name": "梁B", "pct": 50.0},
        {"element_id": "e3", "name": "柱C", "pct": 100.0},
    ]
    actual = [
        {"element_id": "e1", "name": "梁A", "pct": 60.0},   # -20% 滞后
        {"element_id": "e2", "name": "梁B", "pct": 75.0},   # +25% 超前
        {"element_id": "e3", "name": "柱C", "pct": 100.0},  # 0%
    ]
    items = tracker.compute(plan, actual)
    check("compute 返回 3 项", len(items) == 3)

    dev = {it.element_id: it.deviation for it in items}
    check("e1 偏差 -20（滞后）", dev.get("e1") == -20.0)
    check("e2 偏差 +25（超前）", dev.get("e2") == 25.0)
    check("e3 偏差 0（正常）", dev.get("e3") == 0.0)

    alerts = tracker.deviation_alerts(
        items, tenant_id="tnt_v6d", project_id="proj_v6d"
    )
    check("deviation_alerts 返回 2 条（1 critical + 1 warning）",
          len(alerts) == 2)
    levels = {a.level for a in alerts}
    check("含 CRITICAL 级别", "critical" in levels)
    check("含 WARNING 级别", "warning" in levels)


# =====================================================
# [G] 回归
# =====================================================
def check_regression() -> None:
    print("\n[G] 回归 verify_stage1/2/3 + 6a + 6b + 6c")
    scripts = [
        "verify_stage1.py",
        "verify_stage2.py",
        "verify_stage3.py",
        "verify_stage6a.py",
        "verify_stage6b.py",
        "verify_stage6c.py",
    ]
    for script in scripts:
        r = subprocess.run(
            [sys.executable, str(TOOLS_DIR / script)],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        check(f"{script} 退出码 0", r.returncode == 0,
              "无回归" if r.returncode == 0 else "有失败")


def main() -> int:
    print("=" * 60)
    print("阶段六·6d 验收：Dockerfile.edge + BIM 连接器 API")
    print("=" * 60)
    check_scan()
    check_bim_api()
    check_bim_schemas()
    check_dockerfile_edge()
    check_bim_degradation()
    check_progress_tracker()
    check_regression()
    print("\n" + "=" * 60)
    print(f"6d 自检结果: {PASSED} 通过, {FAILED} 失败")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
