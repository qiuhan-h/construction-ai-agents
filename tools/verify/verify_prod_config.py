"""生产配置 fail-fast 校验（7a-2）。

用途：APP_ENV=prod 时，检查关键配置项是否仍为占位值；
      有占位 → exit 1 + 错误清单；全部非占位 → exit 0。
      APP_ENV != prod → 直接 exit 0（仅校验生产）。

验收标准（release_plan_stage7.md 7a-2）：
  - JWT 密钥仍为占位 → 拒绝启动
  - DATABASE_URL / REDIS_URL / LLM_API_KEY 为空或占位 → 拒绝启动
  - LLM_PROVIDER=mock 在 prod 下 → 警告（可选阻断）

用法：
    APP_ENV=prod python tools/verify_prod_config.py
    python tools/verify_prod_config.py          # 非 prod 直接通过
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# 占位标记常量（与 settings.py 保持一致）
_PLACEHOLDER = "需要补充实际链接"


def _is_placeholder(value: str) -> bool:
    """判断字符串是否为占位值。"""
    if not value:
        return True
    return value.strip() in {"", _PLACEHOLDER, "xxx", "your-client-id"}


def _check_secret(secret_val: str) -> bool:
    """检查 SecretStr 解包后的值是否为占位。"""
    return _is_placeholder(secret_val)


def main() -> int:
    """主校验入口。返回 exit code（0=通过，1=失败）。"""
    from config import get_settings

    settings = get_settings()

    # 非 prod 模式直接通过
    if settings.app_env != "prod":
        print(f"[SKIP] APP_ENV={settings.app_env}（仅 prod 模式校验）")
        return 0

    errors: list[str] = []

    # ---------- 必须非占位的关键配置 ----------
    # JWT 密钥
    jwt_val = settings.api_jwt_secret.get_secret_value()
    if _check_secret(jwt_val):
        errors.append("API_JWT_SECRET 仍为占位或空（生产必须 32 字节以上随机串）")

    # 数据库
    if _is_placeholder(settings.database_url):
        errors.append("DATABASE_URL 仍为占位或空（生产必须填写 PostgreSQL 连接串）")

    # Redis
    if _is_placeholder(settings.redis_url):
        errors.append("REDIS_URL 仍为占位或空（生产必须填写 Redis 地址）")

    if _is_placeholder(settings.celery_broker_url):
        errors.append("CELERY_BROKER_URL 仍为占位或空")

    if _is_placeholder(settings.celery_result_backend):
        errors.append("CELERY_RESULT_BACKEND 仍为占位或空")

    # 时序库（生产建议填写，但传感器功能可降级）
    if _is_placeholder(settings.tsdb_url):
        errors.append(
            "TSDB_URL 仍为占位或空（生产如需传感器时序数据须填写 InfluxDB 地址）"
        )

    # LLM
    if _is_placeholder(settings.llm_base_url):
        errors.append("LLM_BASE_URL 仍为占位或空（生产必须填写 LLM 服务地址）")

    if _is_placeholder(settings.llm_default_model):
        errors.append("LLM_DEFAULT_MODEL 仍为占位或空")

    llm_key = settings.llm_api_key.get_secret_value()
    if _check_secret(llm_key):
        errors.append("LLM_API_KEY 仍为空（生产必须填写真实 API Key）")

    # LLM_PROVIDER=mock 在生产下发出警告（不阻断，但记录）
    if settings.llm_provider == "mock":
        errors.append(
            "LLM_PROVIDER=mock 在生产环境不产生真实调用（建议改为 openai/vllm）"
        )

    # ---------- 7b 通道扩展检查（警告项，可降级不阻断） ----------
    # APS / BIM
    aps_client_id = getattr(settings, "aps_client_id", None)
    aps_id_val = aps_client_id.get_secret_value() if aps_client_id and hasattr(aps_client_id, "get_secret_value") else (aps_client_id or "")
    if _is_placeholder(aps_id_val):
        errors.append(
            "APS_CLIENT_ID 占位或空（BIM 功能将降级 mock，生产建议填写）"
        )

    aps_secret = getattr(settings, "aps_client_secret", None)
    aps_secret_val = aps_secret.get_secret_value() if aps_secret and hasattr(aps_secret, "get_secret_value") else (aps_secret or "")
    if _is_placeholder(aps_secret_val):
        errors.append(
            "APS_CLIENT_SECRET 占位或空（BIM 功能将降级 mock）"
        )

    # MQTT
    mqtt_broker = getattr(settings, "mqtt_broker", "")
    if _is_placeholder(mqtt_broker):
        errors.append(
            "MQTT_BROKER 占位或空（MQTT 将降级 asyncio.Queue，现场监控无实时推送）"
        )

    # 钉钉
    dingtalk_webhook = getattr(settings, "dingtalk_webhook", "")
    if _is_placeholder(dingtalk_webhook):
        errors.append(
            "DINGTALK_WEBHOOK 占位或空（钉钉通知将降级 mock，告警无法送达）"
        )

    # 企微
    wecom_webhook = getattr(settings, "wecom_webhook", "")
    if _is_placeholder(wecom_webhook):
        errors.append(
            "WECOM_WEBHOOK 占位或空（企微通知将降级 mock，告警无法送达）"
        )

    # 阿里云短信
    aliyun_key = getattr(settings, "aliyun_sms_access_key_id", None)
    aliyun_key_val = aliyun_key.get_secret_value() if aliyun_key and hasattr(aliyun_key, "get_secret_value") else (aliyun_key or "")
    if _is_placeholder(aliyun_key_val):
        errors.append(
            "ALIYUN_SMS_ACCESS_KEY_ID 占位或空（短信通知将降级 mock）"
        )

    # ---------- 输出结果 ----------
    # 分为阻断项（必须填写）和警告项（可降级）
    blockers = [e for e in errors if "占位或空" in e and "降级" not in e and "建议" not in e]
    blockers += [e for e in errors if "必须" in e or "JWT" in e or "DATABASE_URL" in e or "REDIS_URL" in e or "CELERY" in e or "LLM_" in e]
    # 去重
    blockers = list(dict.fromkeys(blockers))
    warnings = [e for e in errors if e not in blockers]

    if blockers:
        print(f"[FAIL] 生产配置校验未通过，{len(blockers)} 项阻断：")
        for i, e in enumerate(blockers, 1):
            print(f"  {i}. {e}")
        if warnings:
            print(f"\n[WARN] {len(warnings)} 项警告（可降级不阻断）：")
            for i, e in enumerate(warnings, 1):
                print(f"  {i}. {e}")
        print()
        print("请在 .env 或 K8s Secret 中填写真实值后重试。")
        return 1

    if warnings:
        print(f"[WARN] 生产配置校验通过（有降级警告）：{len(warnings)} 项可降级：")
        for i, e in enumerate(warnings, 1):
            print(f"  {i}. {e}")
        print()
        print("这些通道在占位时自动降级，不影响启动。")
        return 0

    print("[OK] 生产配置校验通过：全部配置项均为非占位值。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
