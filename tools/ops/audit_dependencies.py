"""依赖 CVE 扫描（7a-5 安全加固）。

使用 pip-audit 检查项目依赖项是否有已知漏洞。
验收标准：pip-audit 无 HIGH+ 级别漏洞。

用法：
    python tools/audit_dependencies.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    """运行 pip-audit 并检查 HIGH+ 漏洞。返回 exit code。"""
    # 检查 pip-audit 是否安装
    try:
        import importlib

        importlib.import_module("pip_audit")
    except ImportError:
        print("[SKIP] pip-audit 未安装；请先运行: pip install pip-audit")
        print("  安装后重新执行: python tools/audit_dependencies.py")
        return 0

    print("[INFO] 运行 pip-audit 扫描依赖...")

    # 运行 pip-audit（JSON 输出）
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--format", "json"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        print("[FAIL] pip-audit 超时（120s）")
        return 1
    except FileNotFoundError:
        print("[SKIP] pip-audit 命令不可用")
        return 0

    if result.returncode != 0 and not result.stdout:
        print(f"[FAIL] pip-audit 执行失败: {result.stderr}")
        return 1

    # 解析结果
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("[FAIL] pip-audit 输出解析失败")
        print(result.stdout[:500])
        return 1

    vulnerabilities = data.get("dependencies", [])

    if not vulnerabilities:
        print("[OK] 依赖扫描通过：无已知漏洞。")
        return 0

    # 检查 HIGH+ 级别漏洞
    high_vulns = []
    all_vulns = []

    for dep in vulnerabilities:
        name = dep.get("name", "?")
        version = dep.get("version", "?")
        for vuln in dep.get("vulns", []):
            vuln_id = vuln.get("id", "?")
            description = vuln.get("description", "")[:100]
            fix_versions = vuln.get("fix_versions", [])

            all_vulns.append(
                f"  - {name}=={version}: {vuln_id} "
                f"(fix: {','.join(fix_versions) or 'N/A'})"
            )

            # pip-audit 不区分严重级别，所有漏洞都报告
            # 如果有修复版本，视为需要处理

    if all_vulns:
        print(f"[WARN] 发现 {len(all_vulns)} 个依赖漏洞：")
        for v in all_vulns:
            print(v)
        print()
        print("建议：升级到修复版本或使用替代依赖。")
        # 返回 1 以标记有漏洞（但不阻断 CI，除非用户要求严格）
        # 根据 7a-5 验收标准"pip-audit 无 HIGH+"，有漏洞应 exit 1
        return 1

    print("[OK] 依赖扫描通过：无已知漏洞。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
