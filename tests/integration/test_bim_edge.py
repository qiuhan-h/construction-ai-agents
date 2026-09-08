"""集成测试：6d.1 BIM 数据 API + Dockerfile.edge。

覆盖 TR-10.1 ~ TR-10.7：
- TR-10.1: GET /api/v1/bim/projects/{id}/tree → 200
- TR-10.2: GET /api/v1/bim/elements/{id} → 200
- TR-10.3: GET /api/v1/bim/progress/{id} → 200 含偏差项
- TR-10.4: BIM Schema 字段精简
- TR-10.5: Dockerfile.edge 存在 + 多阶段 + healthcheck
- TR-10.6: BIM 连接器降级（缺凭据 → mock）
- TR-10.7: 进度偏差检测（delayed/ahead 计数）
"""

from __future__ import annotations

from pathlib import Path

import pytest

# 项目根：tests/integration/test_bim_edge.py → parents[2]
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DOCKERFILE_EDGE = _PROJECT_ROOT / "deployment" / "docker" / "Dockerfile.edge"


# =====================================================
# TR-10.1: BIM 项目树
# =====================================================
def test_bim_project_tree() -> None:
    """GET /api/v1/bim/projects/{id}/tree → 200 + 含 IfcBuilding。"""
    from api.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev-tnt_bimtest-user1"}

    resp = client.get(
        "/api/v1/bim/projects/proj-001/tree", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert str(data.get("code")) == "0"
    tree = data.get("data", [])
    assert isinstance(tree, list)
    assert len(tree) > 0
    assert tree[0].get("type") == "IfcBuilding"


# =====================================================
# TR-10.2: BIM 构件详情
# =================================================
def test_bim_element() -> None:
    """GET /api/v1/bim/elements/{id} → 200 + element_id 匹配。"""
    from api.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev-tnt_bimtest-user1"}

    resp = client.get(
        "/api/v1/bim/elements/elem-42", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json().get("data", {})
    assert data.get("element_id") == "elem-42"
    assert "properties" in data


# =====================================================
# TR-10.3: BIM 进度对比
# =====================================================
def test_bim_progress() -> None:
    """GET /api/v1/bim/progress/{id} → 200 + 含偏差项。"""
    from api.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev-tnt_bimtest-user1"}

    resp = client.get(
        "/api/v1/bim/progress/proj-001", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json().get("data", {})
    assert data.get("project_id") == "proj-001"
    items = data.get("items", [])
    assert len(items) > 0
    # 至少一个偏差项有 level 字段
    assert all("deviation" in it for it in items)
    assert all("level" in it for it in items)


# =====================================================
# TR-10.4: BIM Schema 字段精简
# =====================================================
def test_bim_schemas_field_count() -> None:
    """BIM Schema 字段数符合精简要求。"""
    from api.schemas.bim_schemas import (
        BIMElement,
        BIMProgressItem,
        BIMProgressResponse,
        BIMProjectTreeNode,
    )

    assert len(BIMElement.model_fields) <= 5, "BIMElement ≤ 5 字段"
    assert len(BIMProgressItem.model_fields) <= 6, "BIMProgressItem ≤ 6 字段"
    assert len(BIMProgressResponse.model_fields) <= 6, "BIMProgressResponse ≤ 6 字段"
    assert len(BIMProjectTreeNode.model_fields) <= 4, "BIMProjectTreeNode ≤ 4 字段"


# =====================================================
# TR-10.5: Dockerfile.edge
# =====================================================
def test_dockerfile_edge_exists() -> None:
    """Dockerfile.edge 存在且非空。"""
    assert _DOCKERFILE_EDGE.is_file(), f"Dockerfile.edge 不存在: {_DOCKERFILE_EDGE}"
    content = _DOCKERFILE_EDGE.read_text(encoding="utf-8")
    assert len(content) > 100, "Dockerfile.edge 内容过短"


def test_dockerfile_edge_multistage() -> None:
    """Dockerfile.edge 含多阶段构建（builder + runtime）。"""
    content = _DOCKERFILE_EDGE.read_text(encoding="utf-8")
    assert "AS builder" in content, "缺少 builder 阶段"
    assert "FROM python:3.12-slim" in content


def test_dockerfile_edge_healthcheck() -> None:
    """Dockerfile.edge 含 healthcheck。"""
    content = _DOCKERFILE_EDGE.read_text(encoding="utf-8")
    assert "HEALTHCHECK" in content


def test_dockerfile_edge_edge_env() -> None:
    """Dockerfile.edge 设 EDGE_MODE 环境变量。"""
    content = _DOCKERFILE_EDGE.read_text(encoding="utf-8")
    assert "EDGE_MODE" in content


def test_dockerfile_edge_nonroot() -> None:
    """Dockerfile.edge 使用非 root 用户。"""
    content = _DOCKERFILE_EDGE.read_text(encoding="utf-8")
    assert "useradd" in content
    assert "USER caai" in content


# =====================================================
# TR-10.6: BIM 连接器降级
# =====================================================
def test_bim_connector_mock_degradation() -> None:
    """BIMConnector 缺 httpx → mock 模式（返回数据不报错）。"""
    from agents.site_monitor_agent.bim_integration import BIMConnector

    conn = BIMConnector(base_url="https://bim.invalid", token=None)
    # httpx 可用时 _client 不为 None；不可用时降级 mock
    # 无论哪种情况，get_project_tree 不应抛异常
    import asyncio

    tree = asyncio.run(conn.get_project_tree("proj-test"))
    assert isinstance(tree, list)


def test_bim_real_connector_placeholder_degradation() -> None:
    """BIMRealConnector 缺凭据 → 降级 mock（不报错）。"""
    from agents.site_monitor_agent.bim_integration import (
        make_bim_real_connector,
    )

    # 占位凭据 → 返回降级对象（不报错）
    real = make_bim_real_connector(
        client_id="your-client-id",
        client_secret="xxx",
        hub_id="",
    )
    # make_bim_real_connector 在凭据占位时返回 None（降级信号）
    assert real is None or hasattr(real, "get_project_tree")


# =====================================================
# TR-10.7: 进度偏差检测
# =====================================================
def test_progress_tracker_deviation() -> None:
    """ProgressTracker 检测偏差并分级。"""
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
        {"element_id": "e3", "name": "柱C", "pct": 100.0},  # 0% 正常
    ]
    items = tracker.compute(plan, actual)
    assert len(items) == 3

    # 偏差值
    deviations = {it.element_id: it.deviation for it in items}
    assert deviations["e1"] == -20.0  # 滞后
    assert deviations["e2"] == 25.0   # 超前
    assert deviations["e3"] == 0.0    # 正常

    # 告警（超阈值）
    alerts = tracker.deviation_alerts(
        items, tenant_id="tnt_test", project_id="proj_test"
    )
    assert len(alerts) == 2  # e1 critical + e2 warning


def test_bim_progress_delayed_ahead_counts() -> None:
    """进度端点返回 delayed / ahead 计数。"""
    from api.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev-tnt_bimtest-user1"}

    resp = client.get(
        "/api/v1/bim/progress/proj-counts", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json().get("data", {})
    assert data.get("total", 0) > 0
    assert data.get("delayed", 0) > 0, "应至少有一个滞后构件"
    assert isinstance(data.get("ahead"), int)
    assert data.get("source") == "mock"
