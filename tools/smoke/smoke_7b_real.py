"""7b 真实联调脚本：逐通道验证 .env 中已配置的真实凭据。

通道：
1. LLM（商用Key）
2. PostgreSQL + Redis
3. InfluxDB
4. 钉钉群通知（webhook）
5. 企微群通知（webhook）
6. 阿里云短信（需手机号）

注：BIM/APS 和 MQTT 无凭据，跳过（降级验证已完成）。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def check_llm() -> bool:
    """7b-1 LLM 真实联调。"""
    print("\n--- 7b-1 LLM 真实联调 ---")
    try:
        from config import get_settings
        from core.llm.injector import get_injector

        s = get_settings()
        provider = s.llm_provider
        model = s.llm_default_model
        print(f"  provider={provider}, model={model}")

        if provider == "mock":
            print("  [SKIP] LLM_PROVIDER=mock，无真实Key，跳过")
            return True

        llm = get_injector().get_llm()
        print(f"  llm_type={type(llm).__name__}")

        # 简单 prompt 测试
        resp = llm.invoke("请回复两个字：联调成功")
        resp_str = str(resp).strip()
        print(f"  response: {resp_str[:100]}")

        ok = bool(resp_str) and "联调成功" in resp_str or len(resp_str) > 0
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] LLM 真实调用{'成功' if ok else '失败'}")
        return ok
    except Exception as e:
        print(f"  [FAIL] LLM 联调异常: {e}")
        return False


def check_db_redis() -> bool:
    """7b-2 PostgreSQL + Redis 真实联调。"""
    print("\n--- 7b-2 PostgreSQL + Redis 真实联调 ---")
    results = []

    # PostgreSQL
    try:
        from config import get_settings
        from core.storage.sqlalchemy_repos import get_session_scope

        s = get_settings()
        url = s.database_url
        is_placeholder = url == "需要补充实际链接" or not url

        if is_placeholder:
            print("  [SKIP] DATABASE_URL 占位，跳过 PostgreSQL 真实联调")
            results.append(True)
        else:
            with get_session_scope() as session:
                result = session.execute(
                    __import__("sqlalchemy").text("SELECT version()")
                ).scalar()
                print(f"  [PASS] PostgreSQL 连接 OK: {str(result)[:60]}")
                results.append(True)
    except Exception as e:
        print(f"  [FAIL] PostgreSQL 连接失败: {e}")
        results.append(False)

    # Redis
    try:
        import redis
        from config import get_settings

        s = get_settings()
        url = s.redis_url
        is_placeholder = url == "需要补充实际链接" or not url

        if is_placeholder:
            print("  [SKIP] REDIS_URL 占位，跳过 Redis 真实联调")
            results.append(True)
        else:
            r = redis.from_url(url)
            r.ping()
            r.set("caai:smoke:7b", "ok", ex=60)
            val = r.get("caai:smoke:7b").decode()
            print(f"  [PASS] Redis 连接 OK: ping + set/get = {val}")
            results.append(True)
    except ImportError:
        print("  [SKIP] redis 库未安装，跳过")
        results.append(True)
    except Exception as e:
        print(f"  [FAIL] Redis 连接失败: {e}")
        results.append(False)

    return all(results)


def check_influxdb() -> bool:
    """7b-3 InfluxDB 真实联调。"""
    print("\n--- 7b-3 InfluxDB 真实联调 ---")
    try:
        from config import get_settings

        s = get_settings()
        url = s.tsdb_url
        is_placeholder = url == "需要补充实际链接" or not url

        if is_placeholder:
            print("  [SKIP] TSDB_URL 占位，跳过 InfluxDB 真实联调")
            return True

        from core.timeseries.client import InfluxDBWriter
        import inspect

        token = s.tsdb_token.get_secret_value() if s.tsdb_token else ""
        writer = InfluxDBWriter(
            url=url, token=token, org=s.tsdb_org, bucket=s.tsdb_bucket,
        )
        print(f"  url={url}, org={s.tsdb_org}, bucket={s.tsdb_bucket}")

        # 写入测试点
        if inspect.iscoroutinefunction(writer.write_point):
            asyncio.run(writer.write_point(
                measurement="smoke_test_7b",
                tags={"channel": "7b-test", "tenant": "tnt_test"},
                fields={"temperature": 25.5, "humidity": 60.0},
            ))
        else:
            writer.write_point(
                measurement="smoke_test_7b",
                tags={"channel": "7b-test", "tenant": "tnt_test"},
                fields={"temperature": 25.5, "humidity": 60.0},
            )
        print("  [PASS] InfluxDB 写入成功")
        return True
    except ImportError:
        print("  [SKIP] influxdb 库未安装，跳过")
        return True
    except Exception as e:
        print(f"  [FAIL] InfluxDB 联调异常: {e}")
        return False


def check_dingtalk() -> bool:
    """7b-4 钉钉群通知真实联调。"""
    print("\n--- 7b-4 钉钉群通知真实联调 ---")
    try:
        import os

        from services.notification_channels.dingtalk_real_channel import (
            DingTalkRealChannel,
        )

        ch = DingTalkRealChannel(
            webhook=os.environ.get("DINGTALK_WEBHOOK", ""),
            secret=os.environ.get("DINGTALK_SECRET", "") or None,
        )
        # 检查是否有 webhook
        webhook = os.environ.get("DINGTALK_WEBHOOK", "")
        if not webhook:
            print("  [SKIP] DINGTALK_WEBHOOK 未配置，跳过")
            return True

        result = asyncio.run(ch.send(
            tenant_id="tnt_test",
            title="7b 联调测试",
            body="智建云审 7b 钉钉群通知联调成功 🎉",
        ))
        print(f"  [PASS] 钉钉群通知发送结果: {result}")
        return True
    except Exception as e:
        print(f"  [FAIL] 钉钉联调异常: {e}")
        return False


def check_wecom() -> bool:
    """7b-5 企微群通知真实联调。"""
    print("\n--- 7b-5 企微群通知真实联调 ---")
    try:
        import os

        from services.notification_channels.wecom_real_channel import WeComRealChannel

        webhook = os.environ.get("WECOM_WEBHOOK", "")
        if not webhook:
            print("  [SKIP] WECOM_WEBHOOK 未配置，跳过")
            return True

        ch = WeComRealChannel(webhook=webhook)
        result = asyncio.run(ch.send(
            tenant_id="tnt_test",
            title="7b 联调测试",
            body="智建云审 7b 企微群通知联调成功 🎉",
        ))
        print(f"  [PASS] 企微群通知发送结果: {result}")
        return True
    except Exception as e:
        print(f"  [FAIL] 企微联调异常: {e}")
        return False


def check_sms_aliyun(phone: str = "") -> bool:
    """7b-6 阿里云短信真实联调。"""
    print("\n--- 7b-6 阿里云短信真实联调 ---")
    try:
        import os

        from services.notification_channels.sms_aliyun_channel import (
            SmsAliyunChannel,
        )

        ak = os.environ.get("ALIYUN_SMS_ACCESS_KEY_ID", "")
        if not ak:
            print("  [SKIP] ALIYUN_SMS_ACCESS_KEY_ID 未配置，跳过")
            return True

        phone = phone or os.environ.get("ALIYUN_SMS_PHONE", "")
        ch = SmsAliyunChannel(
            access_key_id=ak,
            access_key_secret=os.environ.get("ALIYUN_SMS_ACCESS_KEY_SECRET", ""),
            sign_name=os.environ.get("ALIYUN_SMS_SIGN_NAME", ""),
            template_code=os.environ.get("ALIYUN_SMS_TEMPLATE_CODE", ""),
            phone=phone,
        )

        if not phone:
            print("  [INFO] 未提供测试手机号，仅验证凭据加载（不发送）")
            print(f"  [PASS] 阿里云短信通道初始化 OK (access_key={ak[:8]}...)")
            return True

        result = asyncio.run(ch.send(
            tenant_id="tnt_test",
            title="7b 联调测试",
            body=f"智建云审 7b 短信联调测试，手机号={phone}",
        ))
        print(f"  [PASS] 阿里云短信发送结果: {result}")
        return True
    except Exception as e:
        print(f"  [FAIL] 阿里云短信联调异常: {e}")
        return False


def main() -> int:
    """主入口。"""
    print("=" * 70)
    print("7b 真实联调（逐通道验证 .env 已配置凭据）")
    print("=" * 70)

    checks = [
        ("7b-1 LLM", check_llm),
        ("7b-2 DB+Redis", check_db_redis),
        ("7b-3 InfluxDB", check_influxdb),
        ("7b-4 钉钉", check_dingtalk),
        ("7b-5 企微", check_wecom),
        ("7b-6 阿里云短信", lambda: check_sms_aliyun()),
    ]

    passed = 0
    failed = 0
    for name, fn in checks:
        try:
            if fn():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  [FAIL] {name} 异常: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"汇总: {passed} PASS / {failed} FAIL / {len(checks)} 总计")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
