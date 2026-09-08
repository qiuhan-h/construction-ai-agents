# construction-ai-agents 阶段六 — Product Requirements Document

## Overview
- **Summary**: 将平台从"可部署的单租户系统"升级为"可运营的 SaaS 平台 + 多端覆盖 + 边缘可用 + BIM 深度集成"
- **Purpose**: 5b 遗留 FakeListLLM 占位需替换；RBAC 需升级 RBAC+ABAC；多租户 SaaS 化；钉钉/企微内嵌；边缘端离线自治；Revit/Tekla BIM 接入
- **Target Users**: 建筑工程监理/施工方/设计方/安全监管部门的多租户 SaaS 管理者和使用者

## Goals
- GB 规则结构化引擎（5 本国标，每本 ≥10 条结构化规则，机器可判定）
- 真实 LLM 注入（移除 FakeListLLM，支持 OpenAI/Anthropic/vLLM 三选一可切换）
- 多租户 SaaS 化（自助注册 / trial→active 状态机 / 配额限流 429 / 套餐升级）
- ABAC 属性级扩展（RBAC 快路径保留，ABAC 超时 50ms 默认 deny）
- 字段级脱敏（viewer 角色看不到 budget）
- ORM 层 tenant_middleware 纵深防御
- 移动端适配 API + 钉钉/企微内嵌
- 边缘端 ARM64 镜像 + 离线自治 72h
- Revit/Tekla BIM 连接器（MCP 接口，独立进程不侵入核心）

## Non-Goals
- AI 智能体自主决策（→ 阶段七，法规要求人工签字）
- 区块链存证（→ 阶段七，政策依赖）
- 跨项目知识联邦学习（→ 阶段七）
- 全屋智能 / IoT 直连（→ 阶段七）
- 多模态审核（无人机/视频）（→ 阶段七）

## Background & Context
- 阶段 1-5 全部验收通过（pytest 41+ 通过，verify_stage5 5/5 OK）
- 5b.6 LangChain 链 LLM 仍为 FakeListLLM 硬编码（[chains/__init__.py:L202](file:///d:/Trae%20woek%E8%A7%A3%E5%8E%8B%E7%9B%98/workspace-full/zhijian2/%E6%99%BA%E5%BB%BA2/construction-ai-agents/core/langchain/chains/__init__.py)）
- 核心链路已就绪但断开：`core/llm/provider.py` 有完整 OpenAI 兼容调用链路（ProviderRouter → OpenAICompatibleProvider），但 `chains/` 完全没接它
- RBAC 纯静态：`permissions.py` 硬编码 ROLES × RESOURCES 矩阵，`auth.py` 的 JWT claims 只注 tenant_id，**完全没处理 role**
- 规划文档：[stage6_plan.txt](file:///d:/Trae%20woek%E8%A7%A3%E5%8E%8B%E7%9B%98/workspace-full/zhijian2/%E6%99%BA%E5%BB%BA2/stage6/stage6_plan.txt)

## Functional Requirements

### 6a 业务算法升级 + LLM 注入
- **FR-6a.1**: `agents/compliance_agent/regulation_engine/rules/` 下 5 本国标 YAML（GB50016/50011/50189/50378/50009），每本 ≥10 条结构化规则
- **FR-6a.2**: `rule_checker.py` 规则引擎输出必须含条文编号 + 判定结果 + 不合规原因 + 修改建议
- **FR-6a.3**: 荷载组合 GB 50009 公式替换 LoadCalculator 简化公式（误差 < 5%）
- **FR-6a.4**: 结构校核 GB 50010 承载力公式替换简化公式（误差 < 5%）
- **FR-6a.5**: `core/llm/injector.py` — LLM 实例唯一创建入口，OpenAI/Anthropic/vLLM 三选一可切换
- **FR-6a.6**: 提示词模板独立到 `core/llm/prompts/` 子包（safety_prompt.py + compliance_prompt.py），禁止在 chains 中拼接 prompt 字符串
- **FR-6a.7**: `chains/__init__.py` 移除 FakeListLLM，改用 `injector.get_llm()` 注入真实 LLM

### 6b 多租户 SaaS + ABAC
- **FR-6b.1**: `POST /api/v1/tenants` 自助注册 → trial 套餐 30d + 100 次调用额度
- **FR-6b.2**: trial 100 次用完后第 101 次 API 调用 → HTTP 429
- **FR-6b.3**: tenant 状态机 trial → active → suspended → closed
- **FR-6b.4**: ABAC 引擎：RBAC 通过后追加检查（敏感度/时间窗/设备/部门隔离）
- **FR-6b.5**: ABAC 评估超时 >50ms 默认 deny（fail-secure）
- **FR-6b.6**: `FieldMasker.mask(data, role)` — viewer 对 budget 字段 hide
- **FR-6b.7**: `tenant_middleware.py` — SQLAlchemy 事件钩子自动注入 tenant_id WHERE，业务代码遗漏时 SQL 层也不跨租户泄漏
- **FR-6b.8**: JWT claims 注入 role + attributes，AuthContext 新增 role 字段

### 6c 移动端 + 内嵌应用
- **FR-6c.1**: `GET /api/v1/mobile/dashboard` 响应体 < 5KB
- **FR-6c.2**: 钉钉 OAuth 免登 → AuthContext 注入 → 消息推送
- **FR-6c.3**: 企微 OAuth 网页授权 → AuthContext 注入 → 消息推送
- **FR-6c.4**: 钉钉/企微 OAuth 回调校验 state + timestamp（防 CSRF）
- **FR-6c.5**: 移动端仪表盘（Streamlit 响应式，竖屏适配）

### 6d 边缘部署 + BIM 集成
- **FR-6d.1**: ARM64 边缘镜像构建成功 + 健康检查通过
- **FR-6d.2**: 边缘端断网本地 SQLite 缓冲事件 ≥ 72h，重新联网增量同步
- **FR-6d.3**: Revit 连接器：IFC 导入/导出 + 变更同步（MCP 接口，独立进程）
- **FR-6d.4**: Tekla 连接器：钢构件几何 + 节点级精度校核
- **FR-6d.5**: 边缘网关 MQTT → 事件总线，支持离线缓冲 + 断线重连

## Non-Functional Requirements
- **NFR-1**: 降级优先：所有新增外部依赖（钉钉 SDK / 企微 SDK / stripe / asyncio-mqtt / freezegun）try/except 守卫，dev 环境零依赖即可运行
- **NFR-2**: pytest 全部新增测试通过，verify_stage6 验收 10+ 项冒烟全 PASS
- **NFR-3**: 全量回归：verify_stage1..5 全部 OK，pytest 无新失败
- **NFR-4**: 不修改现有通过测试的测试文件行为
- **NFR-5**: 代码风格与现有项目一致（类型注解、中文 docstring、`__init__.py` 导出）

## Constraints
- **Technical**: 用户暂不填 .env 真实值，所有外部依赖必须可降级运行
- **Technical**: 无 Stripe/支付宝支付资质，billing_service 初版用 mock 接口（verify 阶段保留真实 SDK 导入和降级守卫）
- **Technical**: 无 Revit/Tekla 许可证，连接器初版接口定义 + mock 实现，verify 验证接口正确性
- **Technical**: freezegun 不在 requirements.txt 中，ABAC 时间窗测试用 `unittest.mock.patch` 实现

## Assumptions
- 用户批准 spec 和 tasks 后，6a 立即开始实施
- 规划文档 `stage6_plan.txt` §1-§8 为既定范围，用户已确认
- `.trae/specs/stage6-implementation/` 下的 spec/tasks/review 为本阶段唯一工件

## Acceptance Criteria

### AC-6a.1: GB 规则结构化
- **Type**: `rule`
- **Given**: 5 本国标 YAML 文件就位
- **When**: RuleChecker.check(design_doc) 执行
- **Then**: 每条未通过规则返回含 clause_id + severity + message + suggestion 的 Violation 对象
- **Pass Condition**: verify_stage6a.py 规则引擎专项检查通过；gb50016/50011/50189/50378/50009 每本 ≥10 条规则被加载
- **Evidence**: 扫描 YAML 文件条数 + pytest 测试 Violation 对象结构

### AC-6a.2: LLM 注入链通
- **Type**: `rule`
- **Given**: FakeListLLM 占位已移除
- **When**: LCTBusinessChain.run() 执行
- **Then**: injector.get_llm() 返回非 FakeListLLM 的真实 LLM 实例（或无 API Key 时明确 fail fast）
- **Pass Condition**: core/langchain/chains/__init__.py 中不再出现 FakeListLLM
- **Evidence**: git grep FakeListLLM（chains/__init__.py 无结果）+ 单元测试验证返回实例类型

### AC-6a.3: GB 算法替换
- **Type**: `rubric`
- **Dimension**: 数值精度
- **Scale**: 1-5
- **Anchors**: 1=误差>20% 不可用; 3=误差5-10% 基本可用; 5=误差<5% 替代成功
- **Pass Threshold**: >= 4
- **Evidence**: 构造已知载荷/跨度/材料输入对比新旧公式输出

### AC-6b.1: 租户注册与配额
- **Type**: `rule`
- **Given**: 新租户 POST /api/v1/tenants
- **When**: 试用租户发起第 101 次 API 调用
- **Then**: HTTP 429 返回
- **Pass Condition**: verify_stage6b.py 配额专项检查通过
- **Evidence**: 连续 101 次调用，第 101 次状态码 = 429

### AC-6b.2: ABAC RBAC 双引擎
- **Type**: `rule`
- **Given**: 非工作时间（非 9:00-18:00）+ 非受管设备 IP + viewer 角色
- **When**: 访问敏感度 = high 的报告
- **Then**: HTTP 403（ABAC deny 覆盖 RBAC allow）
- **Pass Condition**: verify_stage6b.py ABAC 专项检查通过
- **Evidence**: 时间冻结到 02:00 后请求被 403 拦截

### AC-6b.3: ORM 租户隔离纵深
- **Type**: `rule`
- **Given**: 业务代码手动遗漏 tenant_id 过滤
- **When**: 执行 SELECT 查询跨租户数据
- **Then**: SQLAlchemy 自动注入 WHERE tenant_id = ?，仍返回 0 行
- **Pass Condition**: verify_stage6b.py middleware 专项检查通过
- **Evidence**: sqlparse 解析 SQL 确认 WHERE 子句存在

### AC-6c.1: 移动端 + 内嵌应用
- **Type**: `rule`
- **Given**: GET /api/v1/mobile/dashboard
- **When**: 移动端客户端请求
- **Then**: 响应体 Content-Length < 5120 字节
- **Pass Condition**: verify_stage6c.py 响应体大小检查通过
- **Evidence**: 抓包 Content-Length 头部

### AC-6d.1: 边缘端 + BIM 集成
- **Type**: `rule`
- **Given**: edge_gateway 断网
- **When**: 72h 内事件产生
- **Then**: 事件写入本地 SQLite；重连后增量同步
- **Pass Condition**: verify_stage6d.py 离线/同步专项检查通过
- **Evidence**: 模拟断网→联网生命周期，事件计数一致

### AC-Regression: 全量回归不破坏
- **Type**: `rule`
- **Given**: 阶段 1-5 验收已全绿
- **When**: 阶段六全部实施完毕
- **Then**: verify_stage1..5 全 PASS，pytest tests/ 无新失败
- **Pass Condition**: 每个 verify_stage1..5 输出均为 `N 通过, 0 失败`
- **Evidence**: 依次运行 verify_stage1.py 至 verify_stage5.py + pytest tests/

### AC-Scan: scan_stage6 全通过
- **Type**: `rule`
- **Given**: 阶段六全部文件就位
- **When**: scan_stage6.py 运行
- **Then**: 所有 EXPECTED_FILES 条目 status = OK
- **Pass Condition**: scan_stage6.py 退出码 = 0
- **Evidence**: scan 输出表格无 MISSING / 0 字节占位行
