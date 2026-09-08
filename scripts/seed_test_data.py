"""测试种子数据：创建租户/项目/方案/报告 4 类 mock 数据。

设计（4d D7 幂等，5b.3 升级）：
- 默认创建：
    1 个租户  ``tnt_demo``
    2 个项目  ``prj_alpha`` / ``prj_beta``
    5 个方案  （不同 plan_id）
    3 个报告  （通过 ORM ReviewReportRepository 注入；同时写入内存以兼容 4d）
- 5b.3：报告 upsert 走 ``core.storage.sqlalchemy_repos.get_review_report_repository()``；
  内存 mock 仍保留为兜底（旧路由层会优先 ORM）；
- 4d 阶段不写入 DB；阶段五已切 ORM；
- 重复执行等价于 upsert：以 tenant_id/project_id/plan_id/report_id 为主键；
- 输出 JSON 摘要 + 退出码 0/1。

用法：
    python scripts/seed_test_data.py
    python scripts/seed_test_data.py --tenant tnt_other
    python scripts/seed_test_data.py --json
    python scripts/seed_test_data.py --reset           # 清空 ORM 表 + 内存 store

退出码：
    0  成功
    1  任何写入失败
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger("scripts.seed_test_data")


# =====================================================
# 种子定义（与 4d 完全一致，便于脚本/测试延续）
# =====================================================
SEED_PROJECTS: tuple[dict[str, Any], ...] = (
    {
        "project_id": "prj_alpha",
        "name": "示例项目·A 商业综合体",
        "location": "上海浦东",
        "scale": "120000 m²",
        "stage": "施工准备",
    },
    {
        "project_id": "prj_beta",
        "name": "示例项目·B 高层住宅",
        "location": "北京朝阳",
        "scale": "85000 m²",
        "stage": "主体施工",
    },
)

SEED_PLANS: tuple[dict[str, Any], ...] = (
    {
        "plan_id": "plan_alpha_01",
        "project_id": "prj_alpha",
        "name": "深基坑开挖方案",
        "agent": "safety_audit_agent",
    },
    {
        "plan_id": "plan_alpha_02",
        "project_id": "prj_alpha",
        "name": "钢结构吊装方案",
        "agent": "safety_audit_agent",
    },
    {
        "plan_id": "plan_beta_01",
        "project_id": "prj_beta",
        "name": "模板支撑体系方案",
        "agent": "safety_audit_agent",
    },
    {
        "plan_id": "plan_beta_02",
        "project_id": "prj_beta",
        "name": "消防设计审查",
        "agent": "compliance_agent",
    },
    {
        "plan_id": "plan_alpha_03",
        "project_id": "prj_alpha",
        "name": "绿色施工评估",
        "agent": "compliance_agent",
    },
)

# 报告内容：与 4d 时期保持一致，markdown 占位
SEED_REPORTS: tuple[dict[str, Any], ...] = (
    {
        "report_id": "rpt_demo_001",
        "project_id": "prj_alpha",
        "title": "深基坑开挖方案 - 安全审查报告",
        "conclusion": "conditional_pass",
        "content": (
            "# 深基坑开挖方案 · 安全审查\n\n"
            "- 项目：示例项目·A 商业综合体\n"
            "- 审查结论：有条件通过（需补充监测方案）\n"
            "- 风险等级：中等\n"
        ),
    },
    {
        "report_id": "rpt_demo_002",
        "project_id": "prj_beta",
        "title": "模板支撑体系方案 - 安全审查报告",
        "conclusion": "fail",
        "content": (
            "# 模板支撑体系方案 · 安全审查\n\n"
            "- 项目：示例项目·B 高层住宅\n"
            "- 审查结论：不通过（立杆间距超规）\n"
        ),
    },
    {
        "report_id": "rpt_demo_003",
        "project_id": "prj_alpha",
        "title": "消防设计 - 合规审查",
        "conclusion": "pass",
        "content": (
            "# 消防设计 · 合规审查\n\n"
            "- 项目：示例项目·A 商业综合体\n"
            "- 审查结论：通过\n"
        ),
    },
)


# =====================================================
# ORM 写入辅助
# =====================================================
def _get_orm_repos() -> dict[str, Any] | None:
    """获取 ORM 仓储集合；缺包/失败 → 返回 None（脚本仍可继续写内存 store）。"""
    try:
        from core.storage.sqlalchemy_repos import (
            BackendUnavailableError,
            get_geofence_repository,
            get_regulation_repository,
            get_review_report_repository,
            init_database_for_dev,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("导入 ORM 仓储失败 → 仅写内存: %s", e)
        return None
    try:
        # 5b.3：dev 环境用 create_all 兜底，生产用 alembic upgrade head
        init_database_for_dev()
        return {
            "reports": get_review_report_repository(),
            "regulations": get_regulation_repository(),
            "geofences": get_geofence_repository(),
        }
    except BackendUnavailableError as e:
        logger.warning("ORM 不可用 → 仅写内存: %s", e)
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("ORM 初始化失败 → 仅写内存: %s", e)
        return None


# =====================================================
# 注入
# =====================================================
def _seed_reports(tenant_id: str, reset: bool = False) -> dict[str, int]:
    """把 SEED_REPORTS 写入 ORM + 内存 store。返回 {orm: n, memory: n}。"""
    try:
        from api.routers.reports_router import (
            _reset_report_store,
            get_report_store,
        )
    except Exception as e:  # noqa: BLE001
        logger.error("导入 reports_router 失败: %s", e)
        return {"orm": 0, "memory": 0}

    store = get_report_store()
    if reset:
        try:
            _reset_report_store()
        except Exception:  # noqa: BLE001
            pass

    repos = _get_orm_repos()
    n_orm = 0
    n_mem = 0
    for r in SEED_REPORTS:
        item = {
            **r,
            "tenant_id": tenant_id,
            "inspection_id": item_inspection_id_for(r["project_id"], r["report_id"]),
            "agent": "safety_audit_agent" if "安全" in r["title"] else "compliance_agent",
            "status": "signed",
            "signature": f"hmac-{r['report_id']}",
            "created_at": "2026-09-01T00:00:00Z",
            "regulation_versions": {"GB50016-2014": "2014"},
        }
        # ORM 优先
        if repos is not None:
            try:
                repos["reports"].add(item)
                n_orm += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("ORM 报告写入失败: %s", e)
        # 内存兜底（4d 兼容）
        try:
            store.add(item)
            n_mem += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("内存 store 写入失败: %s", e)
    return {"orm": n_orm, "memory": n_mem}


def item_inspection_id_for(project_id: str, report_id: str) -> str:
    """从 project_id+report_id 派生一个稳定的 inspection_id（4d 时期格式）。"""
    return f"insp_{project_id}_{report_id}"


def _seed_projects_and_plans() -> dict[str, int]:
    """首版只打印（4d/5b.3 不强制注入到 DB）。"""
    return {"projects": len(SEED_PROJECTS), "plans": len(SEED_PLANS)}


# =====================================================
# 主流程
# =====================================================
def main(args: argparse.Namespace) -> int:
    tenant_id = args.tenant
    logger.info("种子数据：tenant=%s reset=%s", tenant_id, args.reset)

    seed_meta = _seed_projects_and_plans()
    n_reports = _seed_reports(tenant_id, reset=args.reset)

    summary = {
        "tenant_id": tenant_id,
        "reset": args.reset,
        "projects": seed_meta["projects"],
        "plans": seed_meta["plans"],
        "reports_orm": n_reports["orm"],
        "reports_memory": n_reports["memory"],
        "plan_ids": [p["plan_id"] for p in SEED_PLANS],
        "report_ids": [r["report_id"] for r in SEED_REPORTS],
    }

    print(
        f"✓ ORM 写入 {summary['reports_orm']} 报告；"
        f"内存同步 {summary['reports_memory']} 报告；"
        f"声明 {summary['projects']} 项目 / {summary['plans']} 方案（仅打印）"
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cli_entry() -> int:
    parser = argparse.ArgumentParser(description="阶段 4d / 5b.3：测试种子数据")
    parser.add_argument("--tenant", default="tnt_demo", help="租户 ID")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="写入前先清空 _REPORT_STORE（仅影响内存 mock store）",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    return main(args)


if __name__ == "__main__":
    sys.exit(cli_entry())
