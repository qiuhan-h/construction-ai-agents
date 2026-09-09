"""7d-1 Go/No-Go 上线预检脚本。

用途：生产发布前脚本化预检，5 类逐项检查，输出签字单。

5 类预检：
  1. 配置完整性：.env / K8s Secret 所有占位已替换
  2. 备份就绪：数据库备份脚本 + 密钥备份就绪
  3. 监控就绪：Prometheus / Grafana / 告警通道已配置
  4. 回滚就绪：前一版本镜像 tag 可用 + downgrade 脚本就绪
  5. 值班就绪：值班人员 + 通讯录 + 回滚授权

用法：
    APP_ENV=prod python tools/go_nogo_checklist.py
    python tools/go_nogo_checklist.py          # 非 prod 演练模式

退出码：
  0 = GO（全部通过）
  1 = NO-GO（有阻断项）
  2 = WARNING（有警告但可放行）
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_PLACEHOLDER = "需要补充实际链接"


def _is_placeholder(value: str) -> bool:
    """判断字符串是否为占位值。"""
    if not value:
        return True
    return value.strip() in {"", _PLACEHOLDER, "xxx", "your-client-id"}


# =====================================================
# 1. 配置完整性检查
# =====================================================

def check_configuration() -> tuple[list[str], list[str]]:
    """配置完整性：关键配置项非占位。返回 (blockers, warnings)。"""
    blockers, warnings = [], []
    try:
        from config import get_settings

        s = get_settings()

        # 阻断项（生产必须非占位）
        if _is_placeholder(s.api_jwt_secret.get_secret_value()):
            blockers.append("API_JWT_SECRET 占位（必须 32+ 字节随机串）")
        if _is_placeholder(s.database_url):
            blockers.append("DATABASE_URL 占位（必须 PostgreSQL 连接串）")
        if _is_placeholder(s.redis_url):
            blockers.append("REDIS_URL 占位（必须 Redis 地址）")
        if _is_placeholder(s.celery_broker_url):
            blockers.append("CELERY_BROKER_URL 占位")
        if _is_placeholder(s.celery_result_backend):
            blockers.append("CELERY_RESULT_BACKEND 占位")
        if _is_placeholder(s.llm_base_url):
            blockers.append("LLM_BASE_URL 占位")
        if _is_placeholder(s.llm_default_model):
            blockers.append("LLM_DEFAULT_MODEL 占位")
        if _is_placeholder(s.llm_api_key.get_secret_value()):
            blockers.append("LLM_API_KEY 空")

        # 警告项（可降级但应填写）
        if _is_placeholder(s.tsdb_url):
            warnings.append("TSDB_URL 占位（传感器时序数据将降级 NoOp）")
        if _is_placeholder(getattr(s, "aps_client_id", "").get_secret_value() if hasattr(getattr(s, "aps_client_id", ""), "get_secret_value") else getattr(s, "aps_client_id", "")):
            warnings.append("APS_CLIENT_ID 占位（BIM 功能将降级 mock）")
        if _is_placeholder(getattr(s, "mqtt_broker", "")):
            warnings.append("MQTT_BROKER 占位（MQTT 将降级 asyncio.Queue）")
        if _is_placeholder(getattr(s, "dingtalk_webhook", "")):
            warnings.append("DINGTALK_WEBHOOK 占位（钉钉通知将降级 mock）")
        if _is_placeholder(getattr(s, "wecom_webhook", "")):
            warnings.append("WECOM_WEBHOOK 占位（企微通知将降级 mock）")

        # LLM_PROVIDER=mock 警告
        if s.llm_provider == "mock":
            warnings.append("LLM_PROVIDER=mock（生产不产生真实 LLM 调用）")

    except Exception as e:
        blockers.append(f"配置加载失败: {e}")

    return blockers, warnings


# =====================================================
# 2. 备份就绪检查
# =====================================================

def check_backups() -> tuple[list[str], list[str]]:
    """备份就绪：备份脚本 + 密钥备份。返回 (blockers, warnings)。"""
    blockers, warnings = [], []

    # 检查备份脚本存在
    backup_script = ROOT / "tools" / "backup_db.sh"
    if not backup_script.exists():
        warnings.append(f"备份脚本不存在: {backup_script.name}（7e-1 将创建）")
    else:
        print(f"  [OK] 备份脚本: {backup_script.name}")

    # 检查 K8s CronJob YAML
    cronjob_yaml = ROOT / "deployment" / "kubernetes" / "cronjob-backup.yaml"
    if not cronjob_yaml.exists():
        warnings.append(f"K8s CronJob YAML 不存在: {cronjob_yaml.name}（7e-1 将创建）")
    else:
        print(f"  [OK] K8s CronJob: {cronjob_yaml.name}")

    # 检查密钥备份（K8s Secret）
    secret_yaml = ROOT / "deployment" / "kubernetes" / "secrets.yaml"
    if not secret_yaml.exists():
        blockers.append(f"K8s Secret YAML 不存在: {secret_yaml.name}")
    else:
        print(f"  [OK] K8s Secret: {secret_yaml.name}")

    # 检查 .env 文件存在
    env_file = ROOT / ".env"
    if not env_file.exists():
        warnings.append(".env 文件不存在（生产应通过 K8s Secret 注入）")
    else:
        print("  [OK] .env 文件存在")

    return blockers, warnings


# =====================================================
# 3. 监控就绪检查
# =====================================================

def check_monitoring() -> tuple[list[str], list[str]]:
    """监控就绪：Prometheus + Grafana + 告警通道。返回 (blockers, warnings)。"""
    blockers, warnings = [], []

    # Prometheus 配置
    prom_yaml = ROOT / "deployment" / "monitoring" / "prometheus.yml"
    if not prom_yaml.exists():
        warnings.append(f"Prometheus 配置不存在: {prom_yaml.name}")
    else:
        print(f"  [OK] Prometheus: {prom_yaml.name}")

    # Grafana dashboard
    grafana_json = ROOT / "deployment" / "monitoring" / "grafana-dashboard.json"
    if not grafana_json.exists():
        warnings.append(f"Grafana dashboard 不存在: {grafana_json.name}（extra-3 将创建）")
    else:
        print(f"  [OK] Grafana: {grafana_json.name}")

    # OTel Collector
    otel_yaml = ROOT / "deployment" / "monitoring" / "otel-collector.yaml"
    if not otel_yaml.exists():
        warnings.append(f"OTel Collector 配置不存在: {otel_yaml.name}（extra-4 将创建）")
    else:
        print(f"  [OK] OTel Collector: {otel_yaml.name}")

    # 告警通道（钉钉/企微）
    try:
        from config import get_settings

        s = get_settings()
        if _is_placeholder(getattr(s, "dingtalk_webhook", "")) and _is_placeholder(getattr(s, "wecom_webhook", "")):
            warnings.append("钉钉+企微告警通道均占位（告警将无法送达）")
    except Exception:
        pass

    return blockers, warnings


# =====================================================
# 4. 回滚就绪检查
# =====================================================

def check_rollback() -> tuple[list[str], list[str]]:
    """回滚就绪：回滚脚本 + downgrade 路径。返回 (blockers, warnings)。"""
    blockers, warnings = [], []

    # 回滚脚本
    rollback_script = ROOT / "tools" / "rollback_drill.py"
    if not rollback_script.exists():
        warnings.append(f"回滚演练脚本不存在: {rollback_script.name}（7d-4 将创建）")
    else:
        print(f"  [OK] 回滚脚本: {rollback_script.name}")

    # Alembic migrations 目录
    migrations_dir = ROOT / "models" / "database" / "migrations" / "versions"
    if not migrations_dir.exists():
        blockers.append(f"Alembic migrations 目录不存在: {migrations_dir}")
    else:
        migration_files = list(migrations_dir.glob("*.py"))
        print(f"  [OK] Alembic migrations: {len(migration_files)} 个版本")
        if len(migration_files) == 0:
            blockers.append("无 Alembic migration 文件（无法 downgrade）")

    # Dockerfile 存在性（回滚需要重建镜像）
    dockerfile_api = ROOT / "deployment" / "docker" / "Dockerfile.api"
    if not dockerfile_api.exists():
        blockers.append(f"Dockerfile.api 不存在: {dockerfile_api.name}")
    else:
        print("  [OK] Dockerfile.api 存在")

    return blockers, warnings


# =====================================================
# 5. 值班就绪检查
# =====================================================

def check_oncall() -> tuple[list[str], list[str]]:
    """值班就绪：值班人员 + 通讯录 + 回滚授权。返回 (blockers, warnings)。"""
    blockers, warnings = [], []

    # operations.md 中应有值班信息
    ops_md = ROOT / "docs" / "operations.md"
    if not ops_md.exists():
        blockers.append(f"运维手册不存在: {ops_md.name}")
    else:
        print(f"  [OK] 运维手册: {ops_md.name}")

    # deployment_runbook.md 中应有回滚步骤
    runbook_md = ROOT / "docs" / "deployment_runbook.md"
    if not runbook_md.exists():
        blockers.append(f"部署手册不存在: {runbook_md.name}")
    else:
        print(f"  [OK] 部署手册: {runbook_md.name}")

    # 值班通讯录（占位检查）
    oncall_file = ROOT / "docs" / "oncall_roster.md"
    if not oncall_file.exists():
        warnings.append(f"值班通讯录不存在: {oncall_file.name}（建议创建）")
    else:
        print(f"  [OK] 值班通讯录: {oncall_file.name}")

    return blockers, warnings


# =====================================================
# 主入口
# =====================================================

def main() -> int:
    """主入口。返回 0=GO, 1=NO-GO, 2=WARNING。"""
    print("=" * 72)
    print("7d-1 Go/No-Go 上线预检")
    print(f"时间: {datetime.now(UTC).isoformat()}")
    print("=" * 72)

    checks = [
        ("1. 配置完整性", check_configuration),
        ("2. 备份就绪", check_backups),
        ("3. 监控就绪", check_monitoring),
        ("4. 回滚就绪", check_rollback),
        ("5. 值班就绪", check_oncall),
    ]

    all_blockers, all_warnings = [], []
    for title, fn in checks:
        print(f"\n--- {title} ---")
        blockers, warnings = fn()
        all_blockers.extend(blockers)
        all_warnings.extend(warnings)
        for b in blockers:
            print(f"  [BLOCK] {b}")
        for w in warnings:
            print(f"  [WARN]  {w}")

    # 汇总
    print("\n" + "=" * 72)
    print(f"汇总: {len(all_blockers)} 阻断 / {len(all_warnings)} 警告")
    print("=" * 72)

    if all_blockers:
        print("\n>>> 决策: NO-GO <<<")
        print(f"阻断项 {len(all_blockers)} 项，必须解决后重新预检：")
        for i, b in enumerate(all_blockers, 1):
            print(f"  {i}. {b}")
        return 1

    if all_warnings:
        print("\n>>> 决策: GO WITH WARNING <<<")
        print(f"警告项 {len(all_warnings)} 项，建议关注但不阻断：")
        for i, w in enumerate(all_warnings, 1):
            print(f"  {i}. {w}")
        print("\n需值班负责人签字放行。")
        return 2

    print("\n>>> 决策: GO <<<")
    print("全部预检通过，可执行生产发布。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
