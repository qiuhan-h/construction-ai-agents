"""集成测试：6c.1 移动端 API + 钉钉/企微内嵌。

覆盖 TR-8.1 ~ TR-8.5：
- TR-8.1: GET /api/v1/mobile/dashboard 响应体 < 5120 bytes
- TR-8.2: DingTalkApp.oauth_callback state mismatch → 403
- TR-8.3: DingTalkApp.oauth_callback timestamp 过期（>300s）→ 403
- TR-8.4: MobileDashboard schema 字段 ≤ 15 个
- TR-8.5: wechatpy 未安装时 WeComApp.push_notification 返回 True（mock 降级）
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException


# =====================================================
# TR-8.4: MobileDashboard 字段数 ≤ 15
# =====================================================
def test_mobile_dashboard_schema_field_count() -> None:
    """MobileDashboard schema 字段 ≤ 15 个（精简）。"""
    from api.schemas.mobile_schemas import MobileDashboard

    fields = MobileDashboard.model_fields
    assert len(fields) <= 15, f"MobileDashboard 字段数 {len(fields)} > 15"
    # 确认核心字段存在
    assert "alerts" in fields
    assert "projects" in fields
    assert "open_alerts" in fields


def test_mobile_alert_list_item_schema_fields() -> None:
    """MobileAlertListItem 字段精简。"""
    from api.schemas.mobile_schemas import MobileAlertListItem

    fields = MobileAlertListItem.model_fields
    assert len(fields) <= 8, f"MobileAlertListItem 字段数 {len(fields)} > 8"


def test_mobile_project_card_schema_fields() -> None:
    """MobileProjectCard 字段精简。"""
    from api.schemas.mobile_schemas import MobileProjectCard

    fields = MobileProjectCard.model_fields
    assert len(fields) <= 8, f"MobileProjectCard 字段数 {len(fields)} > 8"


# =====================================================
# TR-8.1: 响应体 < 5KB
# =====================================================
def test_mobile_dashboard_response_under_5kb() -> None:
    """GET /api/v1/mobile/dashboard 响应体 < 5120 bytes。"""
    from api.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)

    # dev token 模式
    response = client.get(
        "/api/v1/mobile/dashboard",
        headers={"Authorization": "Bearer dev-tnt_mobile-user1"},
    )
    assert response.status_code == 200
    body = response.content
    assert len(body) < 5120, f"响应体 {len(body)} bytes >= 5120 (5KB)"
    data = response.json()
    assert data["code"] == "0"
    assert "data" in data


def test_mobile_alerts_response() -> None:
    """GET /api/v1/mobile/alerts 返回列表。"""
    from api.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)

    response = client.get(
        "/api/v1/mobile/alerts",
        headers={"Authorization": "Bearer dev-tnt_mobile-user1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "0"
    assert isinstance(data["data"], list)


def test_mobile_projects_response() -> None:
    """GET /api/v1/mobile/projects 返回列表。"""
    from api.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)

    response = client.get(
        "/api/v1/mobile/projects",
        headers={"Authorization": "Bearer dev-tnt_mobile-user1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "0"
    assert isinstance(data["data"], list)


# =====================================================
# TR-8.2: DingTalk state mismatch → 403
# =====================================================
def test_dingtalk_oauth_state_mismatch_403() -> None:
    """DingTalkApp.oauth_callback state 不匹配 → HTTPException 403。"""
    from services.embedded_apps.dingtalk_app import DingTalkApp

    app = DingTalkApp()
    now = time.time()
    with pytest.raises(HTTPException) as exc_info:
        app.oauth_callback(
            code="test_code",
            state="wrong_state",
            timestamp=now,
            expected_state="correct_state",
        )
    assert exc_info.value.status_code == 403
    assert "state" in exc_info.value.detail["message"].lower()


# =====================================================
# TR-8.3: DingTalk timestamp 过期 → 403
# =====================================================
def test_dingtalk_oauth_timestamp_expired_403() -> None:
    """DingTalkApp.oauth_callback timestamp >300s → HTTPException 403。"""
    from services.embedded_apps.dingtalk_app import DingTalkApp, OAUTH_STATE_TTL

    app = DingTalkApp()
    # 生成 state
    state = app.generate_state("session_test")
    # timestamp 400s 前（> 300s TTL）
    expired_timestamp = time.time() - 400
    with pytest.raises(HTTPException) as exc_info:
        app.oauth_callback(
            code="test_code",
            state=state,
            timestamp=expired_timestamp,
            session_id="session_test",
        )
    assert exc_info.value.status_code == 403
    assert "过期" in exc_info.value.detail["message"] or "timestamp" in exc_info.value.detail["message"].lower()


def test_dingtalk_oauth_valid_state_passes() -> None:
    """DingTalkApp.oauth_callback 正确 state + 新鲜 timestamp → 成功。"""
    from services.embedded_apps.dingtalk_app import DingTalkApp

    app = DingTalkApp()
    state = app.generate_state("session_ok")
    now = time.time()
    result = app.oauth_callback(
        code="test_code",
        state=state,
        timestamp=now,
        session_id="session_ok",
    )
    assert "userid" in result
    assert result["userid"]  # 非空


# =====================================================
# TR-8.5: wechatpy 未安装 → WeComApp.push_notification 返回 True
# =====================================================
def test_wecom_push_notification_mock_degradation() -> None:
    """wechatpy 未安装时 WeComApp.push_notification 返回 True（mock 降级）。"""
    from services.embedded_apps.wecom_app import WeComApp

    app = WeComApp(corp_id="", agent_id="", secret="")  # 空配置 → 强制 mock
    result = app.push_notification(
        user_ids=["user1", "user2"],
        title="测试通知",
        content="这是一条测试消息",
    )
    assert result is True


def test_wecom_oauth_callback_mock_degradation() -> None:
    """WeComApp.oauth_callback 空配置 → mock 降级返回 userid。"""
    from services.embedded_apps.wecom_app import WeComApp

    app = WeComApp(corp_id="", agent_id="", secret="")
    result = app.oauth_callback("test_code")
    assert "userid" in result
    assert result["userid"]  # 非空


def test_dingtalk_push_notification_mock_degradation() -> None:
    """DingTalkApp.push_notification 空配置 → mock 降级返回 True。"""
    from services.embedded_apps.dingtalk_app import DingTalkApp

    app = DingTalkApp(app_key="", app_secret="", agent_id="")
    result = app.push_notification(
        user_ids=["user1"],
        title="安全告警",
        content="现场检测到隐患",
    )
    assert result is True
