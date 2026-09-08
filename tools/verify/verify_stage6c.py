"""阶段六·子阶段 6c 验收：移动端 API + 内嵌应用 + 响应式 Streamlit 页面。

验收项：
- [A] scan_stage6c 文件清单全部就位
- [B] 6c.1 移动端 API：3 端点 200 + dashboard < 5KB（TR-8.1）
- [C] 6c.1 移动端 Schema：字段精简（TR-8.4）
- [D] 6c.1 钉钉/企微内嵌：OAuth state/timestamp 防重放 + mock 降级（TR-8.2/8.3/8.5）
- [E] 6c.2 API 客户端移动端方法（TR-9.2）
- [F] 6c.2 移动端页面注册（TR-9.1）
- [G] 6c.2 响应式 CSS + 卡片组件（TR-9.3/9.4/9.5/9.6）
- [H] 回归：verify_stage1/2/3 + 6a + 6b 无回归

执行：python verify_stage6c.py
退出码：0 = 全部通过；非 0 = 有失败项。
"""
from __future__ import annotations

import subprocess
import sys
import time
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
    print("\n[A] 文件清单 scan_stage6c")
    r = subprocess.run(
        [sys.executable, str(TOOLS_DIR.parent / "scan" / "scan_stage6c.py")],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    check("scan_stage6c 退出码 0", r.returncode == 0,
          "全部文件就位非空" if r.returncode == 0 else "存在缺失/空壳")


# =====================================================
# [B] 6c.1 移动端 API 端点
# =====================================================
def check_mobile_api() -> None:
    print("\n[B] 6c.1 移动端 API 端点")
    from api.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev-tnt_verify6c-user1"}

    # TR-8.1: dashboard 200 + < 5KB
    resp = client.get("/api/v1/mobile/dashboard", headers=headers)
    check("GET /mobile/dashboard → 200", resp.status_code == 200,
          f"status={resp.status_code}")
    body_len = len(resp.content)
    check("dashboard 响应体 < 5120 bytes（TR-8.1）",
          body_len < 5120, f"{body_len} bytes")
    data = resp.json()
    check("dashboard 响应 code=0", str(data.get("code")) == "0")

    # /alerts 200
    resp2 = client.get("/api/v1/mobile/alerts", headers=headers)
    check("GET /mobile/alerts → 200", resp2.status_code == 200)
    check("alerts 返回 list",
          isinstance(resp2.json().get("data"), list))

    # /projects 200
    resp3 = client.get("/api/v1/mobile/projects", headers=headers)
    check("GET /mobile/projects → 200", resp3.status_code == 200)
    check("projects 返回 list",
          isinstance(resp3.json().get("data"), list))


# =====================================================
# [C] 6c.1 移动端 Schema 字段精简
# =====================================================
def check_mobile_schemas() -> None:
    print("\n[C] 6c.1 移动端 Schema 字段精简")
    from api.schemas.mobile_schemas import (
        MobileAlertListItem,
        MobileDashboard,
        MobileProjectCard,
    )

    # TR-8.4: MobileDashboard ≤ 15 字段
    fields = MobileDashboard.model_fields
    check("MobileDashboard 字段 ≤ 15（TR-8.4）",
          len(fields) <= 15, f"{len(fields)} 字段")
    for required in ("alerts", "projects", "open_alerts"):
        check(f"MobileDashboard 含 {required}", required in fields)

    # MobileAlertListItem ≤ 8 字段
    alert_fields = MobileAlertListItem.model_fields
    check("MobileAlertListItem 字段 ≤ 8",
          len(alert_fields) <= 8, f"{len(alert_fields)} 字段")

    # MobileProjectCard ≤ 8 字段
    proj_fields = MobileProjectCard.model_fields
    check("MobileProjectCard 字段 ≤ 8",
          len(proj_fields) <= 8, f"{len(proj_fields)} 字段")


# =====================================================
# [D] 6c.1 钉钉/企微内嵌应用
# =====================================================
def check_embedded_apps() -> None:
    print("\n[D] 6c.1 钉钉/企微内嵌应用")
    from fastapi import HTTPException

    # ---- 钉钉 ----
    from services.embedded_apps.dingtalk_app import DingTalkApp

    app = DingTalkApp()

    # TR-8.2: state 不匹配 → 403
    now = time.time()
    state_mismatch = False
    try:
        app.oauth_callback(
            code="c", state="wrong", timestamp=now,
            expected_state="correct",
        )
    except HTTPException as e:
        state_mismatch = e.status_code == 403
    check("DingTalk state 不匹配 → 403（TR-8.2）", state_mismatch)

    # TR-8.3: timestamp 过期 → 403
    valid_state = app.generate_state("session_6c")
    expired = time.time() - 400  # > 300s TTL
    ts_expired = False
    try:
        app.oauth_callback(
            code="c", state=valid_state, timestamp=expired,
            session_id="session_6c",
        )
    except HTTPException as e:
        ts_expired = e.status_code == 403
    check("DingTalk timestamp 过期 → 403（TR-8.3）", ts_expired)

    # 正确 state + 新鲜 timestamp → 成功
    fresh_state = app.generate_state("session_ok")
    result = app.oauth_callback(
        code="c", state=fresh_state, timestamp=time.time(),
        session_id="session_ok",
    )
    check("DingTalk 正确 state → 返回 userid", bool(result.get("userid")))

    # 钉钉 push 降级
    dt_app = DingTalkApp(app_key="", app_secret="", agent_id="")
    dt_push = dt_app.push_notification(["u1"], "t", "c")
    check("DingTalk push 空配置 → mock True", dt_push is True)

    # ---- 企微 ----
    from services.embedded_apps.wecom_app import WeComApp

    # TR-8.5: wechatpy 缺失 → mock 降级 True
    wc_app = WeComApp(corp_id="", agent_id="", secret="")
    wc_push = wc_app.push_notification(["u1"], "t", "c")
    check("WeCom push 空配置 → mock True（TR-8.5）", wc_push is True)

    wc_oauth = wc_app.oauth_callback("test_code")
    check("WeCom oauth 空配置 → mock userid", bool(wc_oauth.get("userid")))


# =====================================================
# [E] 6c.2 API 客户端移动端方法
# =====================================================
def check_api_client_methods() -> None:
    print("\n[E] 6c.2 API 客户端移动端方法")
    from streamlit_app.utils.api_client import APIClient

    for method in ("mobile_dashboard", "mobile_alerts", "mobile_projects"):
        check(f"APIClient.{method} 存在（TR-9.2）",
              hasattr(APIClient, method) and callable(getattr(APIClient, method)))


# =====================================================
# [F] 6c.2 移动端页面注册
# =====================================================
def check_page_registration() -> None:
    print("\n[F] 6c.2 移动端页面注册（TR-9.1）")
    from streamlit_app.pages import _IMPLEMENTED, _PAGE_MODULES
    from streamlit_app.app import PAGES

    check("07_mobile 在 _PAGE_MODULES",
          "07_mobile" in _PAGE_MODULES)
    check("07_mobile 在 _IMPLEMENTED",
          "07_mobile" in _IMPLEMENTED)
    check("_PAGE_MODULES 映射正确",
          _PAGE_MODULES.get("07_mobile") == "streamlit_app.pages.07_mobile")

    page_ids = [p["id"] for p in PAGES]
    check("07_mobile 在 app.py PAGES 列表", "07_mobile" in page_ids)
    entry = next((p for p in PAGES if p["id"] == "07_mobile"), None)
    check("PAGES 条目标题含'移动'", entry is not None and "移动" in entry["title"])

    # 模块可导入 + render()
    import importlib
    module = importlib.import_module("streamlit_app.pages.07_mobile")
    check("07_mobile.render() 可调用", callable(getattr(module, "render", None)))


# =====================================================
# [G] 6c.2 响应式 CSS + 卡片组件
# =====================================================
def check_responsive_css_and_cards() -> None:
    print("\n[G] 6c.2 响应式 CSS + 卡片组件")
    from streamlit_app.components import mobile_card
    from pathlib import Path as _Path

    # ---- TR-9.3: CSS 文件 + 断点 ----
    css_path = (
        _Path(__file__).resolve().parents[3]
        / "construction-ai-agents"
        / "streamlit_app"
        / "assets"
        / "css"
        / "mobile.css"
    )
    check("mobile.css 存在", css_path.is_file())
    if css_path.is_file():
        content = css_path.read_text(encoding="utf-8")
        check("CSS 含 @media 响应式断点（TR-9.3）", "@media" in content)
        check("CSS 断点 ≥ 2 个", content.count("@media") >= 2)
        for cls in ("caai-kpi-card", "caai-alert-card", "caai-project-card"):
            check(f"CSS 含 {cls}", cls in content)

    # ---- TR-9.4: KPI 卡片 HTML ----
    with patch("streamlit.markdown") as mock_md:
        mobile_card.render_kpi_grid(
            [
                {"label": "告警", "value": 3, "tone": "danger"},
                {"label": "评分", "value": 88, "tone": "success"},
            ]
        )
        check("KPI 网格渲染 caai-kpi-card（TR-9.4）", mock_md.called)
        html = mock_md.call_args.args[0]
        check("KPI 含 tone 类名 caai-kpi-danger", "caai-kpi-danger" in html)
        check("KPI 含 tone 类名 caai-kpi-success", "caai-kpi-success" in html)

    # ---- TR-9.5: 告警分级色 ----
    with patch("streamlit.markdown") as mock_md:
        mobile_card.render_alert_list(
            [
                {"id": "a1", "level": "critical", "title": "告警A",
                 "source": "s", "status": "open", "occurred_at": "2026-09-05T10:00:00"},
                {"id": "a2", "level": "warning", "title": "告警B",
                 "source": "s", "status": "open", "occurred_at": "2026-09-05T11:00:00"},
            ]
        )
        html = mock_md.call_args.args[0]
        check("告警含 caai-level-critical（TR-9.5）",
              "caai-level-critical" in html)
        check("告警含 caai-level-warning", "caai-level-warning" in html)

    # ---- TR-9.6: 空数据降级 ----
    with patch("streamlit.markdown") as mock_md:
        mobile_card.render_kpi_grid([])
        check("空 KPI → 空状态（TR-9.6）",
              "caai-empty-state" in mock_md.call_args.args[0])

    with patch("streamlit.markdown") as mock_md:
        mobile_card.render_alert_list([])
        check("空告警 → 空状态",
              "caai-empty-state" in mock_md.call_args.args[0])

    with patch("streamlit.markdown") as mock_md:
        mobile_card.render_project_grid([])
        check("空项目 → 空状态",
              "caai-empty-state" in mock_md.call_args.args[0])


# =====================================================
# [H] 回归
# =====================================================
def check_regression() -> None:
    print("\n[H] 回归 verify_stage1/2/3 + 6a + 6b")
    scripts = [
        "verify_stage1.py",
        "verify_stage2.py",
        "verify_stage3.py",
        "verify_stage6a.py",
        "verify_stage6b.py",
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
    print("阶段六·6c 验收：移动端 API + 内嵌应用 + 响应式页面")
    print("=" * 60)
    check_scan()
    check_mobile_api()
    check_mobile_schemas()
    check_embedded_apps()
    check_api_client_methods()
    check_page_registration()
    check_responsive_css_and_cards()
    check_regression()
    print("\n" + "=" * 60)
    print(f"6c 自检结果: {PASSED} 通过, {FAILED} 失败")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
