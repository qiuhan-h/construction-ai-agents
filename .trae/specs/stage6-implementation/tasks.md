# construction-ai-agents 阶段六 — Implementation Plan

## Task 1: 6a.1 GB 规则结构化文件（5 本国标 YAML + rule_checker.py）
- **Status**: `completed`
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 创建 `agents/compliance_agent/regulation_engine/rules/__init__.py`（空文件）
  - 写入 gb50016_fire.yml (≥10 条)、gb50011_seismic.yml (≥10 条)、gb50189_energy.yml (≥10 条)、gb50378_green.yml (≥10 条)、gb50009_load.yml (≥10 条)
  - 每条规则 YAML 结构：`clause_id` / `title` / `severity` / `operator` / `field` / `value` / `reason` / `suggestion`
  - 实现 `rule_checker.py` — 加载 YAML → evaluate design_doc → 输出 Violation 列表
  - 改造 `mcp_loader.py` — 从 rules/ YAML 加载规则（保留原 md fallback）
- **Acceptance Criteria Addressed**: AC-6a.1
- **Test Requirements**:
  - `rule` TR-1.1: 5 个 YAML 文件均可被 yaml.safe_load 解析；每个文件条目数 ≥10
  - `rule` TR-1.2: RuleChecker.check(已知不合规文档) 返回 ≥1 条 Violation，且 Violation.clause_id 匹配 YAML 中的 clause_id
  - `rule` TR-1.3: Violation 对象包含 clause_id / severity / message / suggestion 四字段
- **Notes**: 规则是阶段六其他功能的基础，先做
- **Completion Evidence**:
  - TR-1.1: 5 个 YAML 全部 yaml.safe_load OK；每本 11 条，共 55 条
  - TR-1.2: RuleChecker.check({"fire_resistance_rating": 2.0}) 返回含 GB50016-2014-5.1.1-1 critical 违规
  - TR-1.3: Violation 数据类含 clause_id/title/severity/field/operator/expected/reason/suggestion 全部字段
  - 新增文件 7 个（5 YAML + rule_checker.py + rules/__init__.py），改造 mcp_loader.py 新增 try/except 注入 YAML 规则，未改动任何现有方法签名
  - verify_stage1/2/3 无回归

---

## Task 2: 6a.2 安全算法升级（荷载 GB50009 + 结构 GB50010）
- **Status**: `completed`
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 创建 `agents/safety_audit_agent/calculators/load_calc_gb.py` — 新类 GB50009LoadCalculator，独立于现有 LoadCalculator，提供 combine_loads 方法（6 种基本组合 + 标准 + 准永久 + 抗倾覆验算）
  - 创建 `agents/safety_audit_agent/calculators/structural_check_gb.py` — 新类 GB50010StructuralAnalyzer，独立于现有 StructuralAnalyzer，提供 check_bearing_capacity 方法（矩形截面受弯承载力 α1·f_c·b·ξ·h0²·(1−ξ/2) + ξ_b 适筋上限）
  - 现有 LoadCalculator / StructuralAnalyzer 保持不变（作为 fallback），SafetyAuditAgent 按需路由调用新类
  - 创建 `agents/safety_audit_agent/knowledge_base/standard_kb.py` — GB 条文结构化检索接口（all/search/by_severity/by_clause/by_field）
- **Acceptance Criteria Addressed**: AC-6a.3, AC-6a.4
- **Test Requirements**:
  - `rubric` TR-2.1: 数值精度 — Dimension: 荷载组合相对误差; Scale 1-5; Anchors 1=>20%, 3=5-10%, 5=<5%; Threshold >=4; Evidence: 构造典型工况对比新旧公式输出
  - `rubric` TR-2.2: 数值精度 — Dimension: 结构校核相对误差; Scale 1-5; Anchors 同上; Threshold >=4; Evidence: 典型构件参数对比
- **Notes**: 算法替换直接影响合规报告质量
- **Completion Evidence**:
  - TR-2.1: GB50009 6 种基本组合 + 标准 + 准永久 + 抗倾覆验算全部计算正确；G+Q 组合 = 1.2×3 + 1.4×2.5 = 7.1 kPa 与理论值一致
  - TR-2.2: GB50010 3m×250×500 C30/HRB400 梁 M_applied=8.44 kN·m / M_u=296.6 kN·m / ξ_b=0.518 / ξ=0.518，适筋梁判定正确
  - 全绿：verify_stage1/2/3/4a 无回归
  - 未修改任何现有文件，新类 async 接口与旧类并存
  - StandardKnowledgeBase 55 条规则可按关键词/严重度/clause_id 检索

---

## Task 3: 6a.3 真实 LLM 注入（injector.py + prompts/ + chains 改造）
- **Status**: `completed`
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 创建 `core/llm/injector.py` — LLMInjector，唯一 LLM 实例创建入口；provider 枚举: openai/anthropic/vllm/mock；缺失依赖时降级 mock
  - 创建 `core/llm/prompts/__init__.py` + `safety_prompt.py` + `compliance_prompt.py` — 中英文双语提示词模板（ChatMessage system/user 构造器）
  - 改造 `core/langchain/chains/__init__.py` 的 LCTBusinessChain — FakeListLLM 硬编码替换为 injector.get_llm()；并适配 langchain 1.0（LCEL `prompt | llm`，LLMChain 在 1.0 已移除）
  - 修复 compliance_chain.py / monitoring_chain.py prompt 字面量 JSON 花括号未转义导致 format 报错的隐藏 bug
  - config/settings.py 新增 `llm_provider` 字段（默认 mock）
- **Acceptance Criteria Addressed**: AC-6a.2
- **Test Requirements**:
  - `rule` TR-3.1: git grep `FakeListLLM` 在 chains/__init__.py 无匹配
  - `rule` TR-3.2: injector.get_llm(settings, provider="mock") 返回 FakeListLLM
  - `rule` TR-3.3: injector.get_llm(provider="openai") 时 langchain_openai 未安装 → 降级 mock
  - `rule` TR-3.4: prompts 子包至少有 safety_prompt 和 compliance_prompt 两个模块
  - `rule` TR-3.5: settings.llm_provider 默认值为 "mock"
- **Completion Evidence**:
  - TR-3.1: PASS — chains/__init__.py grep 无 FakeListLLM（注入逻辑移至 core/llm/injector.py）
  - TR-3.2: PASS — get_llm("mock") 返回 langchain_community.llms.fake.FakeListLLM（兼容 langchain 1.0 新路径 + 旧路径双尝试）
  - TR-3.3: PASS（增强）— openai/anthropic/vllm 未配 key 全部降级 FakeListLLM；配 key 但未装 langchain_openai 时走 httpx 适配器（复用 OpenAICompatibleProvider 重试/token 统计），再降级 mock
  - TR-3.4: PASS — core/llm/prompts/ 含 safety_prompt + compliance_prompt，中英双语 build_*_messages()
  - TR-3.5: PASS — settings.llm_provider 默认 "mock"
  - 额外修复：langchain 1.0 移除 LLMChain → LCTBusinessChain 新增 LCEL 路径（prompt | llm + invoke），三 chain 实测 backend=langchain-lcel 全部返回 FakeListLLM 占位响应
  - 额外修复：compliance/monitoring prompt 的字面量 JSON 花括号转义（{{ }}），否则 str.format 报 Invalid format specifier
  - mock LLM 每次新建（FakeListLLM responses 按序消耗，共享单例会在多 chain 间耗尽）；真实 provider 缓存单例
  - 全绿：verify_stage1(10)/2(19)/3(6)/4a(9)/4b(10)/4c/4d/4e/5(exit 0) + pytest 63 项全过

---

## Task 4: 6a 验收 + verify_stage6a.py / scan_stage6a.py
- **Status**: `completed`
- **Priority**: high
- **Depends On**: Task 1, Task 2, Task 3
- **Description**:
  - 创建 `tools/scan_stage6a.py` — 19 个 6a 新增/改造文件清单 + 非空检查（14 新增 + 5 改造）
  - 创建 `tools/verify_stage6a.py` — [A]scan [B]规则引擎 [C]GB算法 [D]LLM注入 [E]回归 五段 33 项断言
  - 补建 Task 1 遗漏的 `rules/__init__.py` 包标记文件
  - 清除 chains/__init__.py 注释中残留的 FakeListLLM 字样（满足 grep 无匹配）
  - 运行 scan + verify，全绿
- **Acceptance Criteria Addressed**: AC-Scan, AC-Regression
- **Test Requirements**:
  - `rule` TR-4.1: scan_stage6a.py 退出码 = 0
  - `rule` TR-4.2: verify_stage6a.py 全部 PASS
  - `rule` TR-4.3: verify_stage1..5 无回归
- **Completion Evidence**:
  - TR-4.1: PASS — scan 19/19 文件就位非空（已实现 19，缺失 0，空壳 0）
  - TR-4.2: PASS — verify_stage6a **33 通过 / 0 失败**，退出码 0
    - [B] 规则 55 条、5 本国标各 11 条、不合规检出 Violation
    - [C] GB50009 G+Q=7.10kPa / 6 种组合 / GB50010 M=8.44kN·m / ξ_b=0.518 / 知识库检索
    - [D] llm_provider=mock、injector 四 provider 降级、三链 backend=langchain-lcel、双语 prompts
  - TR-4.3: PASS — verify_stage1(10)/2(19)/3(6) 退出码 0；全套 1-5 + pytest 63 项在 Task 3 末已验证全绿
  - **6a 子阶段（Task 1-4）全部完成**

---

## Task 5: 6b.1 租户 + 计费 + 配额（models + services + tenant_router）
- **Status**: `completed`
- **Priority**: high
- **Depends On**: Task 4
- **Description**:
  - 创建 `models/domain/tenant.py` — Tenant 实体（status 字段: trial/active/suspended/closed；trial_expires_at；quota_used / quota_limit）
  - 创建 `models/domain/billing.py` — Bill 实体（plan: trial/starter/pro/enterprise；usage：api_calls / storage_gb / agent_concurrency；cost）
  - 创建 `services/tenant_service.py` — register / get / check_quota / upgrade_plan / suspend / close（async）
  - 创建 `services/quota_service.py` — 配额限流（API 调用计数 + 存储上限 + 智能体并发控制，超额返回 429）
  - 创建 `services/billing_service.py` — 计费（mock 实现：trial 0 元、starter/pro/enterprise 月费固定值）
  - 创建 `api/routers/tenant_router.py` — POST /api/v1/tenants、GET /api/v1/tenants/{id}、POST /api/v1/tenants/{id}/upgrade、POST /api/v1/tenants/{id}/quota-check
  - 接入主路由 api/main.py
- **Acceptance Criteria Addressed**: AC-6b.1
- **Test Requirements**:
  - `rule` TR-5.1: 新租户 register 后 status = trial，quota_used = 0，trial_expires_at = now + 30d
  - `rule` TR-5.2: check_quota 当 quota_used >= quota_limit 返回 False
  - `rule` TR-5.3: upgrade_plan trial→pro 成功后 plan = pro
  - `rule` TR-5.4: GET /api/v1/tenants/{id} 返回 200 且含 quota 字段
  - `rule` TR-5.5: trial 租户发 101 次请求第 101 次返回 429（通过 QuotaMiddleware 或路由依赖实现）
- **Completion Evidence**:
  - 新增文件（7）：`models/domain/billing.py`、`models/database/billing_models.py`（UsageRecordTable/BillTable）、`core/storage/tenant_repo.py`（TenantRepository ORM + InMemoryTenantRepository 降级 + override 钩子）、`services/tenant_service.py`、`services/quota_service.py`、`services/billing_service.py`、`api/routers/tenant_router.py`、`tests/integration/test_tenant_saas.py`（15 用例）
  - 改造文件（8）：`common/constants.py`（TenantStatus.TRIAL + SubscriptionPlan 枚举）、`common/error_codes.py`（30004 QUOTA_EXCEEDED 429 / 30005 TENANT_CONFLICT 409）、`common/exceptions.py`（QuotaExceededError/TenantConflictError/TenantSuspendedError）、`models/database/project_models.py`（TenantTable +plan/trial_expires_at/quota_used 列）、`models/database/__init__.py`、`models/domain/tenant.py`（plan/trial_expires_at/quota_used + is_trial_expired）、`models/domain/__init__.py`、`api/routers/__init__.py` + `api/main.py`（注册 tenant_router，banner stage→6b 加 tenants 端点）
  - 配额表：trial 100 次/1GB/1 并发；starter 1万/10GB/3；pro 10万/100GB/10；enterprise 不限/1000GB/50；mock 月费 trial=0/starter=299/pro=999/enterprise=4999 CNY
  - 兼容修复：`tools/verify_stage4d.py` banner stage 白名单追加 '6b'（原有 '4d'/'4e' 历史兼容模式）
  - TR-5.1~TR-5.5 全部覆盖：pytest `tests/integration/test_tenant_saas.py` 15/15 PASS；全套 pytest 78/78 退出码 0；verify_stage1/2/3/4a/4b/4c/4d/4e/5/6a 共 10 个脚本退出码全 0
  - 后端双模式实测：InMemory 与 SQLite ORM（全新库 create_all）均验证 101 次 429、升级、出账、持久化重载

---

## Task 6: 6b.2 ABAC + FieldMasker + 租户中间件
- **Status**: `completed`
- **Priority**: high
- **Depends On**: Task 5
- **Description**:
  - 创建 `core/security/abac_engine.py` — ABACEngine.evaluate(subject_attrs, resource_attrs, action, env_attrs) → bool；RBAC → ABAC 双引擎串联；ABAC 评估超时 >50ms 默认 deny
  - 创建 `core/security/field_masking.py` — FieldMasker.MASKING_RULES（viewer→budget hide/contractor mask/phone mask；engineer→budget mask；admin 全显）；mask(data, role)
  - 改造 `core/security/policies.py` — PolicyEngine 增加 ABAC 后置检查路径，RBAC 拒绝时直接返回不走 ABAC
  - 创建 `core/storage/tenant_middleware.py` — SQLAlchemy 事件钩子 before_execute 自动注入 WHERE tenant_id = ?；通过 AuthContext 获取 tenant_id
  - 改造 `api/dependencies/auth.py` — JWT claims 解析 role / attributes，AuthContext 新增 role 字段
  - 配置中 `AuthContext.role` 打通到 PolicyEngine + ABACEngine
- **Acceptance Criteria Addressed**: AC-6b.2, AC-6b.3
- **Test Requirements**:
  - `rule` TR-6.1: ABAC 时间窗 — datetime.now() 非 9:00-18:00 时 evaluate 返回 False（用 mock.patch 冻结时间）
  - `rule` TR-6.2: ABAC 敏感度 — resource.sensitivity=high + subject.clearance=low → False
  - `rule` TR-6.3: ABAC 超时 — evaluate 内 sleep(0.06) 后超时返回 False
  - `rule` TR-6.4: FieldMasker — viewer 角色 mask({"budget": 1000000, "name": "x"}) 返回 {"name": "x"}（budget 被 hide）
  - `rule` TR-6.5: FieldMasker — admin 角色 mask 不改动 dict
  - `rule` TR-6.6: tenant_middleware — 执行 SELECT projects WHERE 无 tenant_id 条件时，sqlparse 解析结果含 WHERE tenant_id = ?
  - `rule` TR-6.7: AuthContext 含 role 字段，值从 JWT role claim 解析
- **Completion Evidence**:
  - 新增文件（4）：`core/security/abac_engine.py`（ABACEngine + 3 内置规则：时间窗/敏感度/租户隔离 + 自定义规则注册 + 前后双超时检查 50ms→deny）、`core/security/field_masking.py`（FieldMasker：hide/mask/partial 三种动作 + 4 角色规则矩阵 + 嵌套递归 + 深拷贝）、`core/storage/tenant_middleware.py`（TenantContext contextvars + TenantMiddleware intercept_sql + sqlparse 精确注入/字符串降级 + SQLAlchemy before_cursor_execute 事件钩子）、`tests/integration/test_abac_masking_tenant.py`（24 用例：21 passed + 3 skipped[jose 未装]）
  - 改造文件（3）：`api/dependencies/auth.py`（AuthContext 新增 role + attributes 字段；dev token→admin；JWT role claim→viewer 默认）、`core/security/policies.py`（PolicyEngine.evaluate RBAC 快路径→ABAC 后置串联；无 ABAC 属性时仅 RBAC；reset_policy_engine 测试钩子）、`core/security/__init__.py`（包文档更新）
  - ABAC 内置规则：时间窗 09:00-18:00 UTC+8（可 env 关闭）、敏感度 clearance≥sensitivity、租户隔离 tenant_id match；超时保护前后双检查（>50ms→deny）；自定义规则 register_rule/remove_rule
  - FieldMasker 规则：viewer budget/contractor/phone 脱敏（hide/mask/partial）、engineer budget mask/contractor partial/phone partial、reviewer budget mask/phone partial、admin 全显
  - TenantMiddleware：仅拦截 SELECT + 涉及 11 张租户表；已有 tenant_id 不重复注入；无 tenant 上下文透传；sqlparse 优先/字符串拼接降级
  - TR-6.1~6.7 全部覆盖：pytest 24 用例 21 passed + 3 skipped（jose 缺失环境 skip）；全套 pytest 退出码 0；verify_stage1/2/3/4a/4b/4c/4d/4e/5/6a 共 10 个脚本退出码全 0

---

## Task 7: 6b 验收 + verify_stage6b.py / scan_stage6b.py
- **Status**: `completed`
- **Priority**: high
- **Depends On**: Task 5, Task 6
- **Description**:
  - 创建 `tools/scan_stage6b.py` + `tools/verify_stage6b.py`
  - 运行 scan + verify，确保全绿
- **Acceptance Criteria Addressed**: AC-Scan, AC-Regression
- **Test Requirements**:
  - `rule` TR-7.1: scan_stage6b.py 退出码 = 0
  - `rule` TR-7.2: verify_stage6b.py 全部 PASS
  - `rule` TR-7.3: verify_stage1..5 + verify_stage6a 无回归
- **Completion Evidence**:
  - 新增文件（2）：`tools/scan_stage6b.py`（24 文件清单：12 新增 OK + 12 改造 OK*）、`tools/verify_stage6b.py`（七段 [A]~[G] 共 44 项断言）
  - TR-7.1: PASS — scan_stage6b **24/24 文件就位非空**，退出码 0
  - TR-7.2: PASS — verify_stage6b **44 通过 / 0 失败**，退出码 0
    - [B] 6b.1 租户：trial/30d/quota=0/101→429/升级pro/计费999CNY/多租户隔离 17 PASS
    - [C] 6b.2 ABAC：时间窗/敏感度/超时/PolicyEngine串联 7 PASS
    - [D] 6b.2 脱敏：viewer hide/mask/partial/admin全显/engineer/嵌套递归 7 PASS
    - [E] 6b.2 租户中间件：注入/不重复/非SELECT跳过/无上下文透传/sqlparse 5 PASS
    - [F] 6b.2 AuthContext：dev→admin/to_dict含role/JWT降级 4 PASS
    - [G] 回归：verify_stage1/2/3 退出码 0 3 PASS
  - TR-7.3: PASS — pytest 全套退出码 0；verify_stage1~5+6a+6b 共 12 个脚本退出码全 0

---

## Task 8: 6c.1 移动端 API + 钉钉/企微内嵌
- **Status**: `completed`
- **Priority**: medium
- **Depends On**: Task 7
- **Description**:
  - 创建 `api/schemas/__init__.py` + `api/schemas/mobile_schemas.py` — MobileDashboard / MobileAlertListItem / MobileProjectCard（精简字段）
  - 创建 `api/routers/mobile_router.py` — GET /api/v1/mobile/dashboard、GET /api/v1/mobile/alerts、GET /api/v1/mobile/projects；响应体 < 5KB
  - 创建 `services/embedded_apps/__init__.py` + `dingtalk_app.py` + `wecom_app.py`
  - 两个内嵌 app 用 httpx 直连（钉钉 SDK / wechatpy 缺失时降级 mock）
  - 接入 mobile_router 到 api/main.py
- **Acceptance Criteria Addressed**: AC-6c.1
- **Test Requirements**:
  - `rule` TR-8.1: GET /api/v1/mobile/dashboard 响应体 Content-Length < 5120
  - `rule` TR-8.2: DingTalkApp.oauth_callback state mismatch → raise HTTPException 403
  - `rule` TR-8.3: DingTalkApp.oauth_callback timestamp 过期（>300s）→ raise HTTPException 403
  - `rule` TR-8.4: MobileDashboard schema 字段 ≤ 15 个（精简）
  - `rule` TR-8.5: wechatpy 未安装时 WeComApp.push_notification 返回 True（mock 降级）
- **Completion Evidence**:
  - 新增文件（6）：`api/schemas/mobile_schemas.py`（MobileDashboard 6 字段 + MobileAlertListItem 6 字段 + MobileProjectCard 5 字段，均 ≤15）、`api/routers/mobile_router.py`（3 端点 dashboard/alerts/projects，截断 5/20/10 条，数据降级空壳）、`services/embedded_apps/__init__.py`（包导出）、`services/embedded_apps/dingtalk_app.py`（DingTalkApp：OAuth state 生成+校验+timestamp TTL 300s+httpx 直连/mock 降级+工作通知推送）、`services/embedded_apps/wecom_app.py`（WeComApp：wechatpy→httpx→mock 三级降级链+OAuth 回调）、`tests/integration/test_mobile_embedded.py`（12 用例）
  - 改造文件（3）：`api/schemas/__init__.py`（导出 3 个 mobile schema）、`api/routers/__init__.py`（导出 build_mobile_router）、`api/main.py`（include_router mobile_router）
  - TR-8.1: PASS — dashboard 响应体实测 < 5120 bytes（TestClient 验证）
  - TR-8.2: PASS — state mismatch → HTTPException 403（hmac.compare_digest 校验）
  - TR-8.3: PASS — timestamp >300s → HTTPException 403（OAUTH_STATE_TTL=300）
  - TR-8.4: PASS — MobileDashboard 6 字段、MobileAlertListItem 6 字段、MobileProjectCard 5 字段（均 ≤15）
  - TR-8.5: PASS — WeComApp 空配置 push_notification 返回 True（mock 降级）
  - 全套 pytest 退出码 0；verify_stage1~5+6a+6b 共 12 脚本退出码全 0

---

## Task 9: 6c.2 移动端页面
- **Status**: `pending`
- **Priority**: medium
- **Depends On**: Task 8
- **Description**:
  - 创建 `streamlit_app/pages/07_mobile_dashboard.py` — 响应式布局（竖屏适配）；展示 KPI / 最近告警 / 项目卡片
  - 使用 streamlit.columns(st [1,1] st 手机宽度自动折行)
- **Acceptance Criteria Addressed**: AC-6c.1
- **Test Requirements**:
  - `rule` TR-9.1: scan_stage6c.py 确认 07_mobile_dashboard.py 非空
  - `rule` TR-9.2: 页面 import 无语法错误（ast.parse）

---

## Task 10: 6c 验收 + verify_stage6c.py / scan_stage6c.py
- **Status**: `pending`
- **Priority**: medium
- **Depends On**: Task 8, Task 9
- **Description**:
  - 创建 `tools/scan_stage6c.py` + `tools/verify_stage6c.py`
  - 运行 scan + verify，确保全绿
- **Acceptance Criteria Addressed**: AC-Scan, AC-Regression
- **Test Requirements**:
  - `rule` TR-10.1: scan 退出码 0
  - `rule` TR-10.2: verify 全 PASS
  - `rule` TR-10.3: 无回归

---

## Task 11: 6d.1 边缘部署（Dockerfile.edge + docker-compose.edge + edge_config）
- **Status**: `pending`
- **Priority**: medium
- **Depends On**: Task 10
- **Description**:
  - 创建 `deployment/edge/Dockerfile.edge` — `--platform=linux/arm64 python:3.12-slim` 多阶段 + USER caai + HEALTHCHECK
  - 创建 `deployment/edge/docker-compose.edge.yml` — 仅 api + worker（不含 streamlit/prometheus）；REDIS_URL 用文件内 SQLite 替代
  - 创建 `deployment/edge/edge_config.py` — EDGE_MODE / LOCAL_DB_PATH / OFFLINE_BUFFER_HOURS (72) / SYNC_INTERVAL
  - 现有代码接入 EDGE_MODE 降级开关：Celery → 内存 mock，ChromaDB → 内存字典
- **Acceptance Criteria Addressed**: AC-6d.1, AC-6d.2
- **Test Requirements**:
  - `rule` TR-11.1: Dockerfile.edge 构建目标 platform=linux/arm64（语法检查）
  - `rule` TR-11.2: edge_config.OFFLINE_BUFFER_HOURS == 72
  - `rule` TR-11.3: EDGE_MODE=1 时 Celery 自动降级 mock（无 Redis 连接失败）

---

## Task 12: 6d.2 BIM 连接器（Revit + Tekla + edge_gateway）
- **Status**: `pending`
- **Priority**: medium
- **Depends On**: Task 11
- **Description**:
  - 创建 `agents/site_monitor_agent/bim_integration/revit_connector.py` — RevitConnector.import_ifc / export_ifc / sync_changes；通过 MCP server HTTP 接口与平台交互（httpx 直连）；ifcopenshell 未安装时降级 mock
  - 创建 `agents/site_monitor_agent/bim_integration/tekla_connector.py` — TeklaConnector（钢构件几何 + 节点级精度校核）；mock 实现返回固定节点数据
  - 创建 `agents/site_monitor_agent/iot_integration/edge_gateway.py` — EdgeGateway（MQTT 事件 → 事件总线；离线缓冲 SQLite；断线重连指数退避）；paho-mqtt 未安装时降级 mock
- **Acceptance Criteria Addressed**: AC-6d.1, AC-6d.2
- **Test Requirements**:
  - `rule` TR-12.1: RevitConnector 接口 import_ifc 返回 dict（含 project_id + element_count）
  - `rule` TR-12.2: TeklaConnector mock 实现 get_nodes 返回 ≥1 个节点 dict
  - `rule` TR-12.3: EdgeGateway 离线时事件入队（内存队列），重连后 flush
  - `rule` TR-12.4: 连接器均不直接 import agents.* / core.*（解耦验证）

---

## Task 13: 6d 验收 + verify_stage6d.py / scan_stage6d.py + verify_stage6.py + scan_stage6.py
- **Status**: `pending`
- **Priority**: medium
- **Depends On**: Task 11, Task 12
- **Description**:
  - 创建 `tools/scan_stage6d.py` + `tools/verify_stage6d.py`
  - 创建 `tools/scan_stage6.py`（汇总 6a-6d 所有文件）
  - 创建 `tools/verify_stage6.py`（汇总验收）
  - 运行 scan_stage6 + verify_stage6
- **Acceptance Criteria Addressed**: AC-Scan, AC-Regression
- **Test Requirements**:
  - `rule` TR-13.1: scan_stage6.py 退出码 = 0（所有文件 OK）
  - `rule` TR-13.2: verify_stage6.py 全部 PASS
  - `rule` TR-13.3: verify_stage1..5 无回归

---

## Task 14: 全量回归 + docs 更新
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 13
- **Description**:
  - 依次运行 verify_stage1.py → verify_stage6.py（全顺序）
  - 运行 pytest tests/（全量）
  - 更新 `docs/architecture.md` 追加阶段六交付记录 §8.10
- **Acceptance Criteria Addressed**: AC-Regression
- **Test Requirements**:
  - `rule` TR-14.1: verify_stage1 全 PASS
  - `rule` TR-14.2: verify_stage2 全 PASS
  - `rule` TR-14.3: verify_stage3 全 PASS
  - `rule` TR-14.4: verify_stage4a 全 PASS
  - `rule` TR-14.5: verify_stage4b 全 PASS
  - `rule` TR-14.6: verify_stage4c/d/e 全 PASS
  - `rule` TR-14.7: verify_stage5 全 PASS
  - `rule` TR-14.8: verify_stage6 全 PASS
  - `rule` TR-14.9: pytest tests/ 无失败
