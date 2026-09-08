"""7e-2 密钥轮换流程脚本。

用途：定期轮换生产密钥，降低泄露风险。

轮换密钥：
  1. API_JWT_SECRET          JWT 签名密钥（需双密钥并行期）
  2. LLM_API_KEY             LLM 服务 API Key
  3. APS_CLIENT_SECRET       BIM/APS 客户端密钥
  4. TSDB_TOKEN              InfluxDB Token
  5. ALIYUN_SMS_ACCESS_KEY   阿里云短信 AccessKey

流程：
  1. 生成新密钥
  2. 写入 K8s Secret（新 key）
  3. 滚动重启应用（加载新密钥）
  4. 验证新密钥生效
  5. 旧密钥保留 24h（JWT 并行期）后删除

用法：
    python tools/rotate_secrets.py --dry-run  # 仅生成新密钥，不应用
    python tools/rotate_secrets.py --apply    # 生成 + 写入 K8s Secret
    python tools/rotate_secrets.py --verify  # 验证当前密钥
"""

from __future__ import annotations

import argparse
import secrets
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _generate_jwt_secret() -> str:
    """生成 JWT 密钥（32+ 字节随机串）。"""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(48))


def _generate_api_key() -> str:
    """生成 API Key 格式（前缀 + 随机串）。"""
    alphabet = string.ascii_letters + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(32))
    return f"sk-prod-{random_part}"


def _generate_client_secret() -> str:
    """生成客户端密钥。"""
    return secrets.token_urlsafe(32)


def rotate_dry_run() -> int:
    """演练模式：仅生成新密钥，不应用。"""
    print("=" * 72)
    print("7e-2 密钥轮换（DRY-RUN 模式）")
    print("=" * 72)

    new_secrets = {
        "API_JWT_SECRET": _generate_jwt_secret(),
        "LLM_API_KEY": _generate_api_key(),
        "APS_CLIENT_SECRET": _generate_client_secret(),
        "TSDB_TOKEN": _generate_api_key(),
        "ALIYUN_SMS_ACCESS_KEY_SECRET": _generate_client_secret(),
    }

    print("\n生成的新密钥（仅显示前 12 字符）：")
    for key, value in new_secrets.items():
        print(f"  {key}: {value[:12]}...")

    print("\n--- 应用步骤 ---")
    print("1. 更新 K8s Secret:")
    print("   kubectl edit secret caai-secrets -n caai-prod  # 需要补充实际链接：真实命名空间")
    print("   或：")
    print("   kubectl create secret generic caai-secrets \\")
    print("     --from-literal=API_JWT_SECRET='<新值>' \\")
    print("     --dry-run=client -o yaml | kubectl apply -f -")
    print("\n2. 滚动重启应用:")
    print("   kubectl rollout restart deployment/caai-api")
    print("   kubectl rollout restart deployment/caai-worker")
    print("   kubectl rollout status deployment/caai-api --timeout=180s")
    print("\n3. 验证新密钥:")
    print("   python tools/rotate_secrets.py --verify")
    print("\n4. 旧密钥保留 24h 后删除")
    print("\n[OK] DRY-RUN 完成，密钥已生成（未应用）")
    return 0


def rotate_apply() -> int:
    """应用模式：生成 + 写入 .env.example 示例（真实环境用 kubectl）。"""
    print("=" * 72)
    print("7e-2 密钥轮换（APPLY 模式）")
    print("=" * 72)

    new_secrets = {
        "API_JWT_SECRET": _generate_jwt_secret(),
        "LLM_API_KEY": _generate_api_key(),
        "APS_CLIENT_SECRET": _generate_client_secret(),
        "TSDB_TOKEN": _generate_api_key(),
        "ALIYUN_SMS_ACCESS_KEY_SECRET": _generate_client_secret(),
    }

    # 生成 K8s Secret YAML 模板
    print("\n--- 生成 K8s Secret YAML 模板 ---")
    yaml_lines = [
        "apiVersion: v1",
        "kind: Secret",
        "metadata:",
        "  name: caai-secrets-rotated",
        "  namespace: caai-prod  # 需要补充实际链接：真实命名空间",
        "type: Opaque",
        "stringData:",
    ]
    for key, value in new_secrets.items():
        yaml_lines.append(f"  {key}: \"{value}\"  # 需要补充实际链接：轮换后更新")
    yaml_content = "\n".join(yaml_lines)
    print("\n" + yaml_content)

    # 写入文件
    output_file = ROOT / "deployment" / "kubernetes" / "secrets-rotated.yaml"
    output_file.write_text(yaml_content + "\n", encoding="utf-8")
    print(f"\n[OK] YAML 写入: {output_file.name}")
    print("\n--- 后续步骤 ---")
    print("1. 检查 YAML 内容")
    print("2. 应用: kubectl apply -f deployment/kubernetes/secrets-rotated.yaml")
    print("3. 滚动重启: kubectl rollout restart deployment/caai-api")
    print("4. 验证: python tools/rotate_secrets.py --verify")
    print("5. 旧密钥保留 24h 后删除")
    return 0


def verify_secrets() -> int:
    """验证当前密钥状态。"""
    print("=" * 72)
    print("7e-2 密钥轮换（VERIFY 模式）")
    print("=" * 72)

    try:
        from config import get_settings

        s = get_settings()

        checks = [
            ("API_JWT_SECRET", s.api_jwt_secret.get_secret_value()),
            ("LLM_API_KEY", s.llm_api_key.get_secret_value()),
        ]

        # APS 密钥
        aps_secret = getattr(s, "aps_client_secret", None)
        if aps_secret and hasattr(aps_secret, "get_secret_value"):
            checks.append(("APS_CLIENT_SECRET", aps_secret.get_secret_value()))
        else:
            checks.append(("APS_CLIENT_SECRET", str(aps_secret or "")))

        # TSDB Token
        tsdb_token = getattr(s, "tsdb_token", None)
        if tsdb_token and hasattr(tsdb_token, "get_secret_value"):
            checks.append(("TSDB_TOKEN", tsdb_token.get_secret_value()))
        else:
            checks.append(("TSDB_TOKEN", str(tsdb_token or "")))

        print("\n密钥状态：")
        for name, value in checks:
            if not value or value == "需要补充实际链接":
                print(f"  [PLACEHOLDER] {name}: 占位或空")
            elif len(value) < 16:
                print(f"  [WEAK]       {name}: 长度 {len(value)} < 16")
            else:
                print(f"  [OK]         {name}: 长度 {len(value)}")

        # 检查是否需要轮换
        placeholder_count = sum(1 for _, v in checks if not v or v == "需要补充实际链接")
        weak_count = sum(1 for _, v in checks if v and v != "需要补充实际链接" and len(v) < 16)

        if placeholder_count > 0:
            print(f"\n[WARN] {placeholder_count} 个密钥为占位，需填写真实值")
        if weak_count > 0:
            print(f"\n[WARN] {weak_count} 个密钥强度不足，建议轮换")

        if placeholder_count == 0 and weak_count == 0:
            print("\n[OK] 全部密钥状态正常")
            return 0
        return 1

    except Exception as e:
        print(f"[FAIL] 验证失败: {e}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="7e-2 密钥轮换")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True, help="仅生成新密钥（默认）")
    group.add_argument("--apply", action="store_true", help="生成 + 写入 K8s Secret YAML")
    group.add_argument("--verify", action="store_true", help="验证当前密钥状态")
    args = parser.parse_args()

    if args.verify:
        return verify_secrets()
    elif args.apply:
        return rotate_apply()
    else:
        return rotate_dry_run()


if __name__ == "__main__":
    sys.exit(main())
