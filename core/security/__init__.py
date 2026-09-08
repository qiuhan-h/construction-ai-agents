"""安全包：RBAC 权限矩阵 + ABAC 引擎 + 字段脱敏 + 国密 SM2 签章。

6b.2 新增：
- ABACEngine（属性级访问控制，RBAC 通过后追加）
- FieldMasker（字段级脱敏，role-based 规则矩阵）
- TenantMiddleware（ORM 层自动注入 tenant_id WHERE）
"""

from __future__ import annotations
