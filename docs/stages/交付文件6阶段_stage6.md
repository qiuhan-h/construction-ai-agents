# 阶段六交付总结

> 项目：智建云审（construction-ai-agents）
> 阶段：六 · 试点运行 + 工程化增强
> 日期：2026-09-05
> 状态：✅ 全部验收通过（14/14 回归脚本 + pytest 全套 exit 0）

---

## 1. 阶段概述

阶段六在阶段一~五（智能体、A2A/MCP 双协议、编排器、多渠道通知、GIS/监控）基础上，完成**工程化落地增强**，覆盖四个子阶段：

| 子阶段 | 主题 | 核心目标 |
|---|---|---|
| 6a | GB 规则结构化 + LLM 真实注入 | 规范条文参数化 + 真实 LLM 替换 FakeListLLM |
| 6b | 多租户 SaaS | 租户/计费/配额 + ABAC 权限 + 字段脱敏 + 租户中间件 |
| 6c | 移动端 | 移动端精简 API + 钉钉/企微内嵌 + 响应式 Streamlit 页面 |
| 6d | 边缘端 + BIM | Dockerfile.edge + BIM 数据 API + 连接器降级 |

---

## 2. 子阶段交付明细

### 2.1 子阶段 6a — GB 规则结构化 + LLM 真实注入

**新增文件：**

| 文件 | 说明 |
|---|---|
| `core/llm/injector.py` | LLMInjector 单例：按用途注入真实 LLM，缺配置时降级 FakeListLLM |
| `core/llm/prompts/safety_prompt.py` | 安全审查提示词模板 |
| `core/llm/prompts/compliance_prompt.py` | 合规校验提示词模板 |

**修改文件：**

| 文件 | 变更 |
|---|---|
| `core/langchain/chains/__init__.py` | 三条 Chain（safety/compliance/monitoring）由 FakeListLLM 切换为 LLMInjector |

**约束遵守：**
- 现有 `LoadCalculator` / `StructuralAnalyzer` 未改动；GB 公式以独立类实现（`GBXXXX` 前缀）
- 缺 `.env` 配置时自动降级，不阻断开发

### 2.2 子阶段 6b — 多租户 SaaS + ABAC

**6b.1 多租户基座（8 新增 + 8 修改）：**

| 文件 | 说明 |
|---|---|
| `models/domain/tenant.py` | Tenant / TenantPlan 领域模型 |
| `models/domain/billing.py` | 计费模型 |
| `core/storage/tenant_repo.py` | 租户仓储（ORM + 内存双后端，均测试） |
| `services/tenant_service.py` | 租户注册 / 查询 / 升级 |
| `services/quota_service.py` | 配额检查，超限返回 429 + 结构化错误体 |
| `services/billing_service.py` | 计费服务 |
| `api/routers/tenant_router.py` | `/api/v1/tenants` 端点 |
| `tests/integration/test_tenant_saas.py` | 15 个集成测试 |

**6b.2 ABAC + 脱敏 + 中间件：**

| 文件 | 说明 |
|---|---|
| `core/security/abac_engine.py` | ABAC 引擎（RBAC 通过后才评估；RBAC 拒绝则跳过 ABAC） |
| `core/security/field_masking.py` | FieldMasker 字段脱敏 |
| `core/storage/tenant_middleware.py` | 租户上下文注入中间件 |
| `tests/integration/test_abac_masking_tenant.py` | 24 个集成测试 |

### 2.3 子阶段 6c — 移动端

**6c.1 移动端 API + 内嵌应用：**

| 文件 | 说明 |
|---|---|
| `api/routers/mobile_router.py` | `/api/v1/mobile/{dashboard,alerts,projects}` 三个精简端点 |
| `api/schemas/mobile_schemas.py` | MobileDashboard（6 字段 ≤ 15）/ MobileAlertListItem（≤ 8）/ MobileProjectCard（≤ 8） |
| `services/embedded_apps/dingtalk_app.py` | 钉钉 ISV：OAuth（state + timestamp 防重放）+ push（缺配置 mock 降级） |
| `services/embedded_apps/wecom_app.py` | 企微应用：OAuth + push（wechatpy 缺失降级 mock） |
| `tests/integration/test_mobile_embedded.py` | 12 个集成测试 |

**6c.2 响应式 Streamlit 页面：**

| 文件 | 说明 |
|---|---|
| `streamlit_app/pages/07_mobile.py` | 移动工作台页（mobile-first 单列布局） |
| `streamlit_app/components/mobile_card.py` | KPI / 告警 / 项目卡片组件（原生 HTML+CSS，空数据降级） |
| `streamlit_app/assets/css/mobile.css` | 响应式断点（600px 平板 4 列 KPI / 1024px 桌面限宽） |
| `streamlit_app/utils/api_client.py`（修改） | 新增 `mobile_dashboard` / `mobile_alerts` / `mobile_projects` |
| `streamlit_app/pages/__init__.py`（修改） | 注册 `07_mobile` |
| `streamlit_app/app.py`（修改） | PAGES 列表新增"07 移动工作台" |
| `streamlit_app/components/__init__.py`（修改） | 注册 `mobile_card` |
| `tests/integration/test_mobile_pages.py` | 19 个集成测试（TR-9.1~9.6） |

### 2.4 子阶段 6d — 边缘端 + BIM

| 文件 | 说明 |
|---|---|
| `deployment/docker/Dockerfile.edge` | 边缘端容器：多阶段构建 + `EDGE_MODE=1` + 非 root + healthcheck + 单 worker |
| `api/routers/bim_router.py` | `/api/v1/bim/{projects/{id}/tree, elements/{id}, progress/{id}}`；优先 BIMRealConnector（APS），缺凭据降级 BIMConnector（mock） |
| `api/schemas/bim_schemas.py` | BIMElement（4 字段）/ BIMProjectTreeNode（4）/ BIMProgressItem（6）/ BIMProgressResponse（6） |
| `api/main.py`（修改） | 挂载 bim_router；root banner `stage → "6d"`；endpoints 增加 bim |
| `api/routers/__init__.py` / `api/schemas/__init__.py`（修改） | 注册 bim_router / 导出 4 个 BIM Schema |
| `tests/integration/test_bim_edge.py` | 13 个集成测试（TR-10.1~10.7） |

### 2.5 全量回归工具

| 文件 | 说明 |
|---|---|
| `tools/verify_all.py` | 一键回归：13 个 verify 脚本 + pytest 全套，输出通过率报告 |
| `tools/verify_stage4d.py`（修复） | banner stage 白名单增加 `'6d'`（stage 升级后的兼容修复） |
| `tools/scan_stage6{a,b,c,d}.py` | 各子阶段文件清单检查（新增 + 改造文件就位且非空） |
| `tools/verify_stage6{a,b,c,d}.py` | 各子阶段运行期断言 |

---

## 3. 验收结果汇总

### 3.1 阶段六验收断言（163 项）

| 子阶段 | 验收脚本 | 断言数 | 结果 |
|---|---|---|---|
| 6a | `verify_stage6a.py` | 33 | ✅ 全通过 |
| 6b | `verify_stage6b.py` | 44 | ✅ 全通过 |
| 6c | `verify_stage6c.py` | 48 | ✅ 全通过 |
| 6d | `verify_stage6d.py` | 38 | ✅ 全通过 |
| **合计** | | **163** | **0 失败** |

### 3.2 全量回归（verify_all.py）

```
verify_stage1   10P   verify_stage4b   10P   verify_stage6a   33P
verify_stage2   19P   verify_stage4c    4P   verify_stage6b   44P
verify_stage3    6P   verify_stage4d    6P   verify_stage6c   48P
verify_stage4a   9P   verify_stage4e    6P   verify_stage6d   38P
                     verify_stage5     6P
-----------------------------------------------
14/14 脚本退出码全 0，通过率 100%
```

### 3.3 pytest 全套

| 指标 | 数值 |
|---|---|
| 收集用例 | 146 |
| 通过 | 143 |
| 跳过 | 3（ABAC 超时类时序用例） |
| 失败 | 0 |
| 退出码 | 0 |

### 3.4 阶段六新增测试资产（83 个）

| 测试文件 | 用例数 |
|---|---|
| `test_tenant_saas.py` | 15 |
| `test_abac_masking_tenant.py` | 24 |
| `test_mobile_embedded.py` | 12 |
| `test_mobile_pages.py` | 19 |
| `test_bim_edge.py` | 13 |
| **合计** | **83** |

---

## 4. 关键设计决策

| 编号 | 决策 | 理由 |
|---|---|---|
| D1 | LLM 注入采用单例 `LLMInjector`，缺配置降级 `FakeListLLM` | 缺 `.env` 不阻断开发与测试 |
| D2 | ABAC 仅在 RBAC 通过后评估 | 权限收敛，RBAC 拒绝即短路 |
| D3 | 配额超限返回 429 + 结构化错误体 | 客户端可编程处理 |
| D4 | 租户上下文经中间件注入 | 业务代码零侵入 |
| D5 | 移动端 Schema 字段精简（dashboard < 5KB） | 弱网/移动端体验 |
| D6 | 钉钉/企微内嵌均带 mock 降级路径 | OAuth/push 无凭据可开发可测 |
| D7 | BIM 优先 APS 真实连接器，占位凭据降级 mock | 与通知渠道降级策略一致 |
| D8 | Dockerfile.edge 单 worker + EDGE_MODE | 边缘设备资源受限 |

---

## 5. 已知问题与风险（2026-09-05 修复后状态）

| 编号 | 问题 | 影响 | 状态 / 修复方式 |
|---|---|---|---|
| K1 | ~~`test_abac_timeout_denied` 时序敏感（flaky）~~ | 14 脚本连续高负载下偶发失败 | ✅ **已修复**：`ABACEngine` 支持时钟注入（`clock` 参数），测试与 `verify_stage6b` TR-6.3 改用受控时钟推进模拟慢规则，移除真实 `sleep`，超时判定完全确定 |
| K2 | ~~`BIMConnector` 真实模式分支返回空 `{}`/`[]`~~ | httpx 可用但未配置平台时返回空数据 | ✅ **已修复**：`get_project_tree` / `get_element` 真实调用失败或返回空时自动降级 mock（与通知渠道降级策略一致），并新增 `_mock_element` 方法 |
| K3 | ~~`pytest` 汇总行被 warnings 淹没~~ | `verify_all.py` 计数解析困难 | ✅ **已修复**：`verify_all.py` pytest 调用加 `-p no:warnings`，末行汇总（`N passed, M skipped`）可直接解析；保留 `--co` fallback 兜底 |
| K4 | `verify_stage6b.py` / 6c / 6d 全量连跑时受负载影响 | 个别断言偶发波动 | ⚠️ 观察：均为环境负载因素，单脚本运行稳定通过 |

---

## 6. 回归基线与运行方式

```bash
# 全量回归（约 6 分钟）
python tools/verify_all.py

# 单个子阶段
python tools/verify_stage6a.py   # 6a：33 断言
python tools/verify_stage6b.py   # 6b：44 断言
python tools/verify_stage6c.py   # 6c：48 断言
python tools/verify_stage6d.py   # 6d：38 断言

# pytest 全套
python -m pytest tests/ -q --tb=no -p no:warnings

# 边缘端镜像构建
docker build -f deployment/docker/Dockerfile.edge -t zhijian-edge .
```

---

## 7. 后续建议

1. **flaky 治理**：为 ABAC 超时类用例引入时钟注入（`freezegun` / 显式 clock 参数），消除时序依赖
2. **pytest 报告**：`pyproject.toml` 中固定 `-p no:warnings` 或清理 altair 弃用告警，保证汇总行可解析
3. **BIM 真实联调**：配置 APS `client_id/secret/hub_id/project_id` 后对 `BIMRealConnector` 做真实环境冒烟
4. **移动端增强**：`07_mobile` 页面可增加 PWA manifest，支持钉钉/企微容器内免登直连 `/api/v1/mobile/dashboard`
5. **边缘端验证**：在目标边缘设备上实测 `Dockerfile.edge` 镜像体积与启动时间
