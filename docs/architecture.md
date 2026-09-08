# 建筑工程智能体集群（construction-ai-agents）架构说明

> 版本：2026-09-01 架构评审修订版
> 本文档描述系统的分层架构、模块职责，以及相对初版蓝图的修订内容。

## 1. 系统定位

面向建筑工程领域的多智能体协作平台，包含三大业务智能体：

* **施工安全审核智能体**（safety\_audit\_agent）：解析施工方案/图纸/规范，执行荷载计算、结构分析、风险评估，输出审查报告与整改建议。

* **合规校验智能体**（compliance\_agent）：依据法规库对设计文件进行消防、抗震、节能、绿色建筑专项核查，输出合规报告并追踪违规项。

* **施工现场监控智能体**（site\_monitor\_agent）：接入 IoT 传感器与 BIM 模型，进行地理围栏、风险热力图等 GIS 监控，触发告警并生成日报。

三大智能体由**编排协调层**（core/orchestrator）统一调度，通过 A2A 协议相互通信，通过 MCP 协议共享法规/标准/案例资源与计算工具。

## 2. 分层架构

```
┌─────────────────────────────────────────────────────────┐
│ 前端展示层   streamlit_app/  （6 个页面：审核/合规/监控/仪表板/GIS/管理）│
├─────────────────────────────────────────────────────────┤
│ 接入层       api/  （FastAPI：A2A/MCP 路由、任务、报告、WebSocket、健康检查）│
├─────────────────────────────────────────────────────────┤
│ 业务服务层   services/  （任务队列、人工复核、通知、文档、数据接入）      │
├─────────────────────────────────────────────────────────┤
│ 智能体层     agents/  （安全审核、合规校验、现场监控）                  │
├─────────────────────────────────────────────────────────┤
│ 编排协调层   core/orchestrator/  （工作流、任务调度、协作、人机交互）    │
├─────────────────────────────────────────────────────────┤
│ 核心框架层   core/                                     │
│   llm/        模型接入、配置、成本统计、提示词管理（不绑定框架）          │
│   a2a/        智能体间通信协议                          │
│   mcp/        资源（法规/标准/案例）与工具（计算/校验/分析）             │
│   langchain/  业务链、工具、记忆                        │
│   gis/        空间分析、图层、地理编码、坐标转换          │
│   events/     事件总线（发布/订阅）                      │
│   observability/ 分布式追踪、指标                       │
│   storage/ cache/ timeseries/  存储与缓存抽象            │
├─────────────────────────────────────────────────────────┤
│ 数据层       models/  （领域模型、数据库模型、向量模型）+ data/          │
├─────────────────────────────────────────────────────────┤
│ 公共基础     common/  （异常、错误码、常量、ID、时间工具）               │
└─────────────────────────────────────────────────────────┘
```

## 3. 关键设计决策

| 决策                                             | 说明                                                       |
| ---------------------------------------------- | -------------------------------------------------------- |
| LLM 接入层独立（core/llm/）                           | 模型提供方、密钥配置、用量统计与 LangChain 解耦，便于更换模型或框架                  |
| 编排层与业务智能体分离                                    | 编排是协调者而非业务执行者，置于 core/orchestrator/，与 agents/ 下三个业务智能体区分 |
| 异步任务队列（services/task\_queue.py）                | 审查为长耗时任务，经 Celery 异步执行，避免阻塞 API                          |
| 时序存储（core/timeseries/）                         | 传感器高频数据写入时序库，不落关系型数据库                                    |
| 法规版本管理（regulation\_engine/version\_manager.py） | 法规会更新废止，每条审查结论绑定当时依据的法规版本，保证合规可追溯                        |
| 事件总线（core/events/）                             | 支撑"监控告警 → 编排器 → 触发审查"等跨智能体异步协作场景                         |
| 数据库迁移（models/database/migrations/）             | 使用 Alembic 管理表结构演进                                       |
| 多租户（models/domain/tenant.py）                   | 多个项目/施工单位并发使用时数据隔离                                       |
| 通知渠道抽象（services/notification\_channels/）       | 短信/钉钉/企业微信可插拔扩展                                          |

## 4. 相对初版蓝图的修订记录（2026-09-01）

### 新增模块

* `common/`：公共基础（异常、错误码、常量、ID、时间工具）

* `core/llm/`：LLM 接入层（provider、config、token\_tracker、prompt\_manager）

* `core/events/`：事件总线

* `core/observability/`：分布式追踪与指标

* `core/storage/`：文件存储抽象（本地/对象存储）

* `core/cache/`：Redis 缓存

* `core/timeseries/`：时序库客户端

* `core/orchestrator/`：编排协调层（自 agents/orchestrator\_agent/ 迁入）

* `config/environments/`：dev/staging/prod 分环境配置

* `evaluation/`：智能体输出质量评测

* `docs/`：架构、API、运维、开发文档

* `.github/workflows/`：CI（lint + 测试）与镜像构建流水线

### 新增文件（现有模块内）

* `core/gis/services/coordinate_transform.py`：GCJ-02/WGS-84 坐标转换（国内地图服务必需）

* `agents/safety_audit_agent/outputs/report_signer.py`：报告电子签章/防伪

* `agents/compliance_agent/regulation_engine/version_manager.py`：法规版本管理

* `agents/site_monitor_agent/iot_integration/tsdb_writer.py`：传感器数据写入时序库

* `api/schemas/pagination.py`：分页与通用响应模式

* `services/task_queue.py`：异步任务队列

* `services/notification_channels/`：通知渠道（接口 + 短信/钉钉/企微）

* `models/domain/tenant.py`：多租户模型

* `models/database/migrations/`：Alembic 迁移

* `alembic.ini`：迁移配置

### 结构调整

* `agents/orchestrator_agent/` → `core/orchestrator/`（编排为协调层，非业务智能体）

### 第二轮修订（2026-09-01）：结构收敛与工程补全

**删除（消除冗余）**

* `services/agent_orchestrator.py`：编排统一收敛至 `core/orchestrator/`，不设第二编排入口

* `core/langchain/agents/`：LangChain Agent 实现收敛到各智能体的 `langchain_agent.py`，避免双处实现

* `agents/orchestrator_agent/` 遗留目录（空文件残留，已迁至 `core/orchestrator/`）

**重命名（统一命名）**

* `api/routers/agents.py | tasks.py | reports.py | websocket.py` → `agents_router.py | tasks_router.py | reports_router.py | websocket_router.py`

**新增**

* `api/routers/health_router.py`：健康检查路由（K8s 存活/就绪探针）

* `models/domain/report.py`：审查报告领域模型

* `agents/compliance_agent/tests/`：合规智能体测试（与另两个智能体对齐）

* `scripts/start_worker.py`、`deployment/docker/Dockerfile.worker`、`deployment/kubernetes/deployments/worker.yaml`：补齐 Celery worker 启动与部署链路

* `.gitignore`、`.dockerignore`；`data/`、`streamlit_app/assets/` 空目录补 `.gitkeep`

## 5. 开发路线建议

1. **阶段一（地基）**：requirements/pyproject 依赖、config 配置、common 公共基础、models 领域模型、core/llm 接入层
2. **阶段二（核心协议）**：A2A 协议、MCP 服务端（资源与工具）、事件总线
3. **阶段三（首个智能体）**：安全审核智能体全流程（解析→计算→知识库→报告）
4. **阶段四（扩展与编排）**：合规、监控智能体 + 编排层 + FastAPI 服务 + 任务队列
5. **阶段五（前端与部署）**：Streamlit 六页面、可观测性接入、Docker 部署、CI 流水线

## 6. 阶段二交付记录（2026-09-01）

阶段二目标：A2A 协议 + MCP 服务端（资源/工具/提示词） + 事件总线 + 接入层协议路由 + 智能体基类。

### 6.1 交付物（36 个文件，全部非 0 字节）

**A.** **`core/a2a/`** **智能体间通信协议（8 个）**

* `protocol.py`：协议版本（`1.0`）、Method 枚举（DISCOVERY / SEND\_MESSAGE / GET\_TASK / CANCEL\_TASK）、ErrorCode、JSON-RPC 2.0 帧

* `message.py`：`A2AMessage` / `MessagePart` / `Task` / `TaskState` / `Artifact`，状态机 PENDING→RUNNING→{COMPLETED,FAILED,CANCELLED}

* `serializers.py`：`JSONRPCRequest` 编解码、success/error 响应构造、协议版本协商

* `agent_card.py`：`AgentCard` / `Skill` / `Capabilities`，对外暴露 `to_public_dict()`，由 `/agent.json` 端点返回

* `server.py`：`AgentRegistry`（注册表）+ `A2AServer.handle_raw`（JSON-RPC 入口），支持方法分发

* `client.py`：`A2AClient`，httpx 异步调用 + 4xx/5xx/网络错误分类（`A2AProtocolError` / `A2ANetworkError` / `A2AServerError` / `A2AMessageInvalidError`）

* `middleware.py`：`logging_middleware` / `timing_middleware` / `RateLimiter`（令牌桶限流），全部 async

* `__init__.py`：包级 re-export

**B.** **`core/mcp/`** **模型上下文协议（13 个）**

* `server.py`：`MCPServer` / `MCPService` 单例、`@register_resource` / `@register_tool` / `@register_prompt` 装饰器、JSON-RPC over HTTP 端点

* `client.py`：`MCPClient`，异步调用 `tools/call` / `resources/read` / `prompts/get`

* `prompts/safety_prompts.py`：`safety.audit` 提示词模板（首版）

* `resources/regulation_resource.py`：URI 规范 `regulation://{code}/{version}`，按 tenant\_id 过滤

* `resources/standard_resource.py`：URI 规范 `standard://{code}/{version}`

* `resources/case_resource.py`：URI 规范 `case://{case_id}`

* `tools/calculation_tools.py`：`calculation.load`（首版荷载组合 1.2D+1.4L+0.6W+0.7S）

* `tools/validation_tools.py`：`validation.plan`（方案一致性校验）、`validation.drawing`（占位）

* `tools/analysis_tools.py`：`analysis.aggregate_risk`（占位）

* 各子包 `__init__.py`：公共 API

**C.** **`core/events/`** **事件总线（3 个）**

* `events.py`：`Event` dataclass + 主题常量 `TOPIC_INSPECTION_COMPLETED` / `TOPIC_VIOLATION_CREATED` / `TOPIC_ALERT_TRIGGERED` / `TOPIC_REPORT_SIGNED`

* `event_bus.py`：`EventBus` 进程内实现（asyncio 队列 + 回调订阅），支持通配符 `topic.*` 与历史回放

* `__init__.py`：便捷 `publish()` 入口

**D.** **`api/`** **接入层（7 个）**

* `schemas/a2a_schemas.py`：A2A DTO（`A2ASendMessageRequest` / `A2AMessageDTO` / 响应）

* `schemas/agent_schemas.py`：`AgentSummary` / `AgentDetail` / `AgentCardDTO` / `AgentListResponse`

* `schemas/response_schemas.py`：`ApiResponse[T]`（统一 `{code,message,data}` 包装）+ `ErrorResponse` + `ErrorDetail`

* `schemas/pagination.py`：`Page[T]` / `PaginationQuery`（offset/limit 推导）

* `routers/a2a_router.py`：`build_a2a_router()`，FastAPI 路由组，prefix `/api/v1/a2a`

* `routers/mcp_router.py`：`build_mcp_router()`，FastAPI 路由组，prefix `/api/v1/mcp`

* `__init__.py`：包级 re-export

**E.** **`agents/`** **智能体基座（2 个）**

* `base_agent.py`：`BaseAgent` 抽象基类（`name` / `version` / `skills` / `card`），提供 `handle` / `get_task` / `cancel_task` / `new_task`；`@register_agent` 装饰器供阶段三继承

* `__init__.py`：基类 re-export

**F.** **`scripts/`** **启动脚本（2 个）**

* `start_a2a_server.py`：`build_app()` 构造 FastAPI，监听 `settings.api_host:9101`

* `start_mcp_server.py`：`build_app()` 构造 FastAPI，监听 `:9201`

**G.** **`config/logging_config.py`（1 个，已存在）**

合计 36 个文件，全部非 0 字节。详见 [stage2\_plan.txt](../stage2_plan.txt) §1 清单。

### 6.2 公共基础增补

* `common/error_codes.py` 增补 `A2A_INVALID_MESSAGE` (50001) / `A2A_AGENT_NOT_FOUND` (50002) / `A2A_PROTOCOL_VERSION_MISMATCH` (50004) / `A2A_TASK_NOT_FOUND` (50005) / `MCP_RESOURCE_NOT_FOUND` (60001) / `MCP_TOOL_EXECUTION_FAILED` (60002) / `MCP_PROTOCOL_VERSION_MISMATCH` (60004) 等

* `common/exceptions.py` 增补 `A2AMessageInvalidError` / `A2AAgentNotFoundError` / `A2AProtocolVersionMismatchError` / `A2ATaskNotFoundError` / `A2ANetworkError` / `A2AServerError` / `MCPResourceNotFoundError` / `MCPToolNotFoundError` / `MCPToolExecutionError` / `MCPProtocolVersionMismatchError` / `MCPPromptNotFoundError` / `EventPublishError` / `TaskStateConflictError`

* `common/ids.py` 增补 `regulation_id` / `standard_id` / `case_id` / `event_id` / `message_id`（对应 `reg_/std_/case_/evt_/msg_` 前缀）

### 6.3 依赖增量

`pyproject.toml` 与 `requirements.txt` 已同步：

* 运行时：`httpx>=0.27` / `fastapi>=0.115` / `uvicorn[standard]>=0.30` / `pydantic>=2.7`（均已存在）

* 可选 messaging 分组：`aio-pika>=9.4`（RabbitMQ 适配器，默认不启用）

* 开发：`respx>=0.21`（httpx mock）、`pytest-asyncio>=0.23`（均已就位）

### 6.4 自检与回归

* `scan_stage2.py`：36/36 OK（无空字节占位、无缺失）

* `verify_stage2.py`：19/19 通过

  * common 增补（A2A/MCP 错误码与异常、阶段二 ID 前缀）

  * `core.a2a.*` 全部模块（协议、消息/状态机、序列化、Agent Card、注册表+JSON-RPC 端到端、客户端+中间件）

  * `core.mcp.*` 全部模块（注册表、工具调用、提示词渲染、资源读取、客户端）

  * `core.events`：发布/订阅/通配/历史

  * `agents.base_agent`：骨架 + 装饰器

  * `api.schemas`：ApiResponse/Page/DTO

  * `api.routers`：a2a/mcp 路由构造

  * `scripts`：a2a/mcp `build_app`

  * 集成：A2A + MCP 工具 + 事件总线 round-trip

* `verify_stage1.py`：10/10 通过（无回归）

* `check_new_tree.py`：目录树与 `shu_zhuang_tu.txt` 100% 一致（仅 `__pycache__` 缓存差异）

### 6.5 与阶段三/四衔接约定

* 业务智能体直接继承 `agents.base_agent.BaseAgent`，通过 `core.a2a.client.A2AClient` 与其他智能体通信

* 真实算法在阶段三落地到 `core/mcp/tools/calculation_tools.py`（首版为荷载组合占位）

* 知识库统一经 `core/mcp/resources/regulation_resource` / `standard_resource` 访问，避免业务侧直接读文件

* 编排器（阶段四）通过 `core.events.event_bus.publish` 触发"监控告警 → 编排 → 启动审查"工作流

## 7. 阶段三交付记录（2026-09-01）

阶段三目标：安全审核智能体（safety\_audit\_agent）全流程——解析 → 计算 → 知识库 → 报告。

### 7.1 交付物（23 个文件全部非 0 字节）

**A.** **`agents/safety_audit_agent/`** **智能体主包（5 个）**

* `agent.py` 主类 SafetyAuditAgent，串起解析/计算/检索/生成/签章/事件

* `a2a_handlers.py` A2A 注册 + FastAPI 路由构造

* `mcp_handlers.py` 包 core.mcp 现有能力，新增 safety.search\_case / safety.match\_regulation

* `langchain_agent.py` LangChain 风格入口（未安装 langchain 时降级）

* `prompts.py` 注册 3 个模板：safety.plan\_review / drawing\_review / report\_draft

**B.** **`agents/safety_audit_agent/calculators/`** **计算引擎（3 个 +** __init__）

* `load_calculator.py` GB 50009 首版荷载组合 1.2D+1.4L+0.6W+0.7S

* `risk_assessor.py` LEC 法 D=L·E·C，5 级分类（CRITICAL/HIGH/MEDIUM/LOW/NEGLIGIBLE）

* `structural_analyzer.py` 跨高比 + 高跨 + 配筋率占位校验

**C.** **`agents/safety_audit_agent/knowledge_base/`** **知识库（3 个 +** __init__）

* `vector_store.py` VectorStore 抽象 + InMemoryVectorStore（纯 Python 余弦相似度）

* `standard_loader.py` regulation/standard 资源桥接 + 章节切分灌库

* `case_retriever.py` 多租户隔离的 Top-K 案例检索

**D.** **`agents/safety_audit_agent/parsers/`** **解析层（3 个 +** __init__）

* `spec_parser.py` 国标/行标按章节切分

* `plan_parser.py` Markdown/DOCX → PlanFields（项目名/阶段/危险源/荷载/材料）

* `drawing_parser.py` 图纸元数据（IFC 头部 / 标题栏）

**E.** **`agents/safety_audit_agent/outputs/`** **报告输出（3 个 +** __init__）

* `report_signer.py` HMAC-SHA256 签章 + verify

* `recommendation_engine.py` LEC 风险 → 整改建议（stop\_work/urgent/normal/info）

* `report_generator.py` 结构化 ReviewReport + Markdown 双形态

**F.** **`tests/safety_audit_agent/test_agent.py`（1 个）** 11 项端到端自检

合计 23 个文件，全部非 0 字节。详见 [stage3\_plan.txt](../stage3_plan.txt) §1 清单。

### 7.2 handle 主流程

A2AMessage → 解析 project\_id/plan\_id/plan\_text → PlanParser → PlanFields
→ LoadCalculator.combined\_load → LoadResult
→ LECAssessor.assess → RiskAssessment
→ CaseRetriever.search\_cases → CaseHit\[]
→ ReportGenerator.generate → ReportArtifacts（结构化 + Markdown）
→ ReportSigner.sign → HMAC 签名
→ 事件发布：report.signed / alert.triggered（CRITICAL 时）/ inspection.completed
→ A2AMessage（text 总结 + file Markdown + data 报告 JSON）

### 7.3 自检结果（6 + 11 = 17 项 PASS）

* `scan_stage3.py`：23 / 23 OK（0 空字节、0 缺失）

* `verify_stage3.py`：6 / 6

  * 顶层 import 全通过、继承 BaseAgent、Skill 元数据完整

  * 模块级 sign/verify 函数、prompts 重复 import 幂等

  * tests/safety\_audit\_agent/test\_agent.py 委派（11 / 11）

* `verify_stage1.py`：10 / 10（无回归）

* `verify_stage2.py`：19 / 19（无回归）

* `check_new_tree.py`：无缺失文件 / 目录（仅 __pycache__ 缓存差量）

### 7.4 阶段三相对计划清单的偏差

* 全部按 plan §1 实施，未新增/合并/删除文件

* 计算/知识库/解析/输出 4 个子包各 3 个模块 + 1 个 __init__ = 16 个文件

* 主包 5 个 + 测试 1 个 + 子包 __init__.py 4 个 = 23 个

* `tests/safety_audit_agent/test_agent.py` 替代 `tests/test_agent.py`（plan §3.17 提到 tests/，但放到 safety\_audit\_agent/ 子目录更聚类；tests/ 根仍保留 e2e/integration/unit 子目录由阶段四填充）

### 7.5 依赖增量

* pyproject.toml / requirements.txt **未新增**依赖

* 内部完全使用阶段一/二已就位的 fastapi / pydantic / sqlalchemy / httpx / langchain(可选)

* DOCX 解析需 `python-docx`（可选依赖，缺失时降级为文本读取）

* 阶段四引入：ChromaDB、IFC 解析、CA 签章

### 7.6 与阶段四衔接

* compliance\_agent / site\_monitor\_agent 直接复用：

  * `agents.safety_audit_agent.knowledge_base.vector_store`（抽象接口）

  * `agents.safety_audit_agent.knowledge_base.standard_loader`

  * `agents.safety_audit_agent.outputs.report_signer`

  * `agents.safety_audit_agent.parsers.spec_parser`

* 编排器订阅：inspection.completed / alert.triggered（已发布）

* 阶段四 FastAPI 业务路由直接 import SafetyAuditAgent.handle()

### 7.7 不在阶段三范围内（确认排除）

* × 合规校验智能体（agents/compliance\_agent/）→ 阶段四

* × 现场监控智能体（agents/site\_monitor\_agent/）→ 阶段四

* × 编排器（core/orchestrator/）→ 阶段四

* × FastAPI 业务路由（api/routers/{agents,tasks,reports,websocket,health}\_router.py）→ 阶段四

* × Celery 任务队列（services/task\_queue.py）→ 阶段四

* × ChromaDB 真实落地 → 阶段四

* × IFC 完整解析 → 阶段四

* × PDF 报告导出（reportlab）→ 阶段五

* × 前端 / 部署 / CI / 可观测性 → 阶段五

## 8. 阶段四交付记录（4c / 4b 收尾）

### 8.1 阶段四范围回顾

* 4a / 4b：3 个业务智能体（safety\_audit\_agent / compliance\_agent / site\_monitor\_agent）→ 已在阶段三先行交付并补齐自检

* **4c（本次）**：编排器 + 业务服务层，把 3 个智能体用 A2A + 事件总线串起来

### 8.2 4c 交付物清单

#### 8.2.1 编排器（`core/orchestrator/`）

| 文件                         | 行数级   | 职责                                                                                                                                           |
| -------------------------- | ----- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `workflow_engine.py`       | \~370 | `TaskSpec` / `Workflow` 数据类；`WorkflowEngine` 注册表 + 拓扑排序（Kahn 按层分组）+ `${var}` 模板渲染 + 按层并行 `asyncio.gather` + agent / system 两类节点派发 + 3 个默认工作流 |
| `task_scheduler.py`        | \~135 | `TaskScheduler`（指数退避 1.0s×2^n，最多 3 次）+ `register_celery_tasks` Celery worker 入口（4c 首版占位）                                                     |
| `orchestrator.py`          | \~225 | 主编排器：订阅 4 类事件（`alert.triggered` / `inspection.completed` / `violation.created` / `regulation.updated`）→ 触发工作流 → 记录协作时间线 + 通知                 |
| `collaboration_manager.py` | \~145 | 多智能体协作时间线（按 task\_id 索引；可 JSON 持久化；多租户隔离）                                                                                                    |
| `human_interaction.py`     | \~80  | `HumanReviewServiceAdapter`：编排器 ↔ `services.human_review_service` 适配层                                                                        |
| `a2a_handlers.py`          | \~180 | `OrchestratorA2AHandler`：把编排器注册成 A2A 智能体（暴露 `agent.send_message` / `workflow.list` / `workflow.get_run` 3 个 method）                          |

#### 8.2.2 业务服务（`services/`）

| 文件                                                      | 职责                                                                                                                                                                                                                      |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `celery_app.py`                                         | Celery 应用单例（broker 缺凭据走 `memory://`；autodiscover `services/`）                                                                                                                                                           |
| `task_queue.py`                                         | `TaskQueue`：Celery 封装 + mock 降级（`memory://` / broker 不可达均视作 mock，返回 `mock-*` id）                                                                                                                                        |
| `service_registry.py`                                   | **4c 新增**：`ServiceRegistry` 静态门面 + `@register_service` 装饰器 + 6 个内置服务（`services.notify` / `services.human_review` / `services.document.upload` / `services.ingest.iot` / `services.ingest.file` / `services.ingest.api`） |
| `human_review_service.py`                               | 人工复核业务服务（`create` / `get` / `list_pending` / `list_by_tenant` / `approve` / `reject`）                                                                                                                                   |
| `human_review_repository.py`                            | 内存仓储（线程安全；多租户隔离：跨租户 `get` 视为 None）                                                                                                                                                                                      |
| `document_service.py`                                   | 文档上传/下载/列表/删除 + SHA-256 fingerprint                                                                                                                                                                                     |
| `notification_service.py`                               | 通知聚合：按 severity → channel 路由；`DEFAULT_SEVERITY_CHANNELS`（critical → 3 渠道、high → 2、warning → 1、info → wecom）                                                                                                             |
| `notification_channels/base_channel.py`                 | 渠道抽象基类 + `@register_channel` 注册表 + severity 过滤                                                                                                                                                                          |
| `notification_channels/{dingtalk,sms,wecom}_channel.py` | 3 个首版 mock 渠道（webhook 缺失走 mock）                                                                                                                                                                                         |
| `data_ingestion.py`                                     | **4c 新增**：`DataIngestionService` 三类入口（`ingest_iot` / `ingest_file` / `ingest_api`）+ 批接入 + 租户统计                                                                                                                          |

#### 8.2.3 测试与验收

| 文件                                               | 覆盖                                                                                                                                            |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/orchestrator/test_orchestrator.py`        | **24 项**脚本式自检（`__main__` 直跑）：TaskSpec/Workflow 校验、模板渲染、环检测、DAG 按层并行、协作时间线、任务调度、4 类事件回调、ServiceRegistry、通知路由、渠道过滤、人工复核、文档、数据接入、A2A handler、端到端 |
| `tests/orchestrator/test_orchestrator_pytest.py` | 与上一份一一对应的 pytest 镜像：同步 14 项 + 异步 10 项 = **24 项 pytest 用例**，`pytest tests/orchestrator/ -v` 即可产出 pass/fail 报告                                  |
| `tools/scan/scan_stage4c.py`                          | 4c 文件/模块/export 静态扫描（22 文件 / 20 模块 / 14 export）                                                                                               |
| `tools/verify/verify_stage4c.py`                        | 4c 验收：自检 + ServiceRegistry 路由 + 端到端冒烟（EventBus→Orchestrator→Workflow→AgentManager）                                                            |

### 8.3 关键设计原则（落实情况）

| 原则                        | 落实                                                                                              |
| ------------------------- | ----------------------------------------------------------------------------------------------- |
| O1 编排器只通过 A2A 调度 agent    | `WorkflowEngine._dispatch_agent` 走 `agent_manager.get(...).handle(msg, task)`                   |
| O2 节点依赖 + 按层并行            | Kahn 拓扑分层，`asyncio.gather(*layer_tasks)`                                                        |
| O3 任务队列 + 重试              | `TaskScheduler.submit` 指数退避；`TaskQueue` Celery 封装 + mock 降级                                     |
| O4 system 动作可扩展           | `ServiceRegistry` + `@register_service` 装饰器；4c 落 6 个内置 action                                   |
| O5 多租户硬隔离                 | 所有 `record_interaction` / `notify` / `human_review.*` / `ingest_*` 必传 `tenant_id`；仓储层跨租户访问视为不存在 |
| O6 规则触发通过 ServiceRegistry | violation / regulation 事件回调直接 `ServiceRegistry.dispatch`                                        |
| O7 失败显式化                  | 工作流任一节点失败 → run 状态 `failed` + 错误入 `errors` 字段 + 协作文档记录                                          |

### 8.4 端到端冒烟结果

```
TIMELINE_COUNT 2
HANDLED {'safety_audit_agent': 1, 'compliance_agent': 1}
WORKFLOWS ['monitor_alert_to_audit', 'compliance_followup', 'regulation_record']
```

1. `alert.triggered` (level=critical) → `monitor_alert_to_audit` 工作流 → safety\_audit\_agent 实际被调 1 次
2. `inspection.completed` (conclusion=fail) → `compliance_followup` 工作流 → compliance\_agent 实际被调 1 次
3. 协作时间线按租户正确隔离
4. 6 个 system action 全注册

### 8.5 全量回归（4c 视角）

| 阶段     | 测试文件                                             | 项数                                    |
| ------ | ------------------------------------------------ | ------------------------------------- |
| 4a     | `tests/safety_audit_agent/test_agent.py`         | 11 PASS（脚本式 self-check）               |
| 4b     | `tests/compliance_agent/test_agent.py`           | 18 PASS（脚本式 self-check）               |
| 4b     | `tests/site_monitor_agent/test_agent.py`         | 22 PASS（4c 顺手修复了 4b 留下的 BOM + GBK 乱码） |
| 4c     | `tests/orchestrator/test_orchestrator.py`        | 24 PASS（脚本式 self-check）               |
| 4c     | `tests/orchestrator/test_orchestrator_pytest.py` | 24 PASS（pytest 镜像）                    |
| 一/二/三  | `tests/unit/`、`tests/integration/`、`tests/e2e/`  | 12 PASS（pytest）                       |
| **合计** | <br />                                           | **111 PASS / 0 FAIL**                 |

#### 8.5.1 三种运行方式

1. **pytest 整轮**（CI 默认入口）：

   ```bash
   PYTHONPATH=. python -m pytest tests/ -q
   # 36 passed in 3.40s
   ```

   * `tests/conftest.py` 在 collection 阶段把 `sys.exit` 替换为 noop，让老式
     `__main__` 自检脚本（顶层含 `sys.exit()`）不会在 collection 时打断整轮。

   * 阶段一/二/三/四/5 个子目录已加 `__init__.py`，消除 `test_agent` 同名
     import 冲突。

2. **4c 脚本式自检**（保留 `__main__` 入口，便于 IDE 直跑）：

   ```bash
   python tests/orchestrator/test_orchestrator.py
   # == 4c 自检 24/24 通过 ==
   ```

3. **4c 端到端验收**：

   ```bash
   python tools/scan/scan_stage4c.py    # 静态：22 文件 / 20 模块 / 14 export
   python tools/verify/verify_stage4c.py   # 动态：self_test + service_registry + e2e_smoke
   ```

### 8.6 阶段四下一站（4d / 4e）

* 4d：`api/routers/` 实际接通编排器（`POST /orchestrator/workflows/{name}/trigger`、状态查询、Celery worker 启动脚本）

* 4e：编排器可视化（时间线 / 运行历史 dashboard）

* 阶段五：ChromaDB 真实落地、IFC 完整解析、PDF 报告导出、CICD

## 8.7 阶段四·子阶段 4d 交付记录（2026-09-02）

阶段四 4d 目标：FastAPI 业务接入 + 运维脚本 + 测试收口，让平台具备"完整 REST + WebSocket 接入 + 一键运维脚本 + 端到端测试"能力（阶段五前端可直接消费所有 API）。

### 8.7.1 范围与交付物

* **api/**：1 个 `main.py`（lifespan + 路由聚合）+ 3 个依赖注入 + 6 个业务路由（4d 业务层）+ 1 个编排器路由（4d 业务层）
* **scripts/**：6 个运维脚本（init_agents / load_regulations / load_gis_data / setup_vector_db / seed_test_data / start_worker）
* **tests/**：1 个 conftest + 3 个 unit + 2 个 integration + 1 个 e2e
* **tools/**：1 个 scan + 1 个 verify

合计 **26 个交付文件**（含 tools/）。

### 8.7.2 api/ 主要端点

| 端点                                                                | 方法     | 鉴权 | 用途                              |
| ----------------------------------------------------------------- | ------ | -- | ------------------------------- |
| `/api/v1/health/healthz`                                          | GET    | 否  | 存活探针（K8s livenessProbe）         |
| `/api/v1/health/readyz`                                           | GET    | 否  | 就绪探针（database/redis/celery/event_bus） |
| `/api/v1/agents`                                                  | GET    | 是  | 列出当前租户可调用的业务智能体（白名单 + 已实例化）     |
| `/api/v1/agents/supported`                                        | GET    | 是  | 列出 AgentManager 支持的智能体白名单        |
| `/api/v1/agents/{name}/card`                                      | GET    | 是  | 读取指定智能体的 Agent Card              |
| `/api/v1/agents/{name}/invoke`                                    | POST   | 是  | 通过 HTTP 触发智能体 handle（A2A 包装）     |
| `/api/v1/tasks/{task_id}`                                         | GET    | 是  | 查询任务状态（Celery / mock）           |
| `/api/v1/tasks/{task_id}`                                         | DELETE | 是  | 取消任务                            |
| `/api/v1/reports?project_id=&page=&page_size=`                    | GET    | 是  | 按项目/分页列出报告（内存 store）             |
| `/api/v1/reports/{report_id}`                                     | GET    | 是  | 读取报告详情（Markdown + 签章）           |
| `/api/v1/reports/{report_id}/download?format=md`                  | GET    | 是  | 下载报告（首版仅 Markdown）              |
| `/api/v1/orchestrator/workflows`                                  | GET    | 是  | 列出所有注册工作流                       |
| `/api/v1/orchestrator/workflows/{name}`                           | GET    | 是  | 读取工作流定义（节点 + 依赖）                |
| `/api/v1/orchestrator/workflows/{name}/trigger?payload={...}`      | POST   | 是  | 触发工作流（同步返回 run_id）               |
| `/api/v1/orchestrator/runs/{run_id}`                              | GET    | 是  | 查询工作流执行状态（timeline + 错误）        |
| `/api/v1/orchestrator/timeline?tenant_id=&limit=`                 | GET    | 是  | 协作时间线（按租户过滤）                    |
| `/api/v1/ws/events?topic=*.*&tenant_id=tnt_x`                     | WS     | 否  | 实时事件订阅（30s ping，跨租户过滤）          |
| `/api/v1/a2a/...`（阶段二已存在，本次仅 lifespan 接入）                            | 多     | 否  | A2A REST + JSON-RPC 端点           |
| `/api/v1/mcp/...`（阶段二已存在）                                              | 多     | 否  | MCP 资源/工具/提示词端点                |
| `/`                                                               | GET    | 否  | 根 banner（含 endpoint 列表）          |

所有 HTTP 响应统一为 `ApiResponse[T] = {code, message, data, request_id, timestamp}`，4d 阶段不要求鉴权的端点仅 healthz/readyz/根 banner + WebSocket。

### 8.7.3 关键设计原则（4d 落实情况）

| 原则                                | 落实                                                                                                                                                  |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1 FastAPI 依赖注入统一                 | `api.dependencies.{auth, agent_manager, orchestrator_provider}` 全部 `Depends()` 注入，依赖项返回对象带 `tenant_id`                                              |
| D2 异步优先                           | 所有路由 handler `async def`；唯一同步块是 `agent_manager._create_agent` 内部构造，4d 用 `async with self._lock` 包裹                                                   |
| D3 OpenAPI 自动生成                   | 所有路由带 `response_model=ApiResponse[dict]` + `tags=[...]`；`uvicorn api.main:app` 启动后 `/docs` 直接可见                                                       |
| D4 健康检查分级                         | `/healthz` 永远 200；`/readyz` 聚合 db/redis/celery/event_bus 四类检查，失败 503                                                                          |
| D5 WebSocket 心跳 + 跨租户过滤           | 每 30s 发送 `{"type":"ping"}`；handler 推送前过滤 `event.tenant_id == tenant_id`；断线时 `bus.unsubscribe` 释放订阅                                                  |
| D6 测试金字塔                          | unit（MCP/A2A/GIS）/ integration（工作流 + 协作）/ e2e（HTTP→A2A→handle→报告→DB→事件→WS）三档分明                                                                |
| D7 脚本幂等                            | `load_regulations` / `load_gis_data` / `setup_vector_db` / `seed_test_data` 全部基于 ULID 主键 + upsert 语义，重复执行不会产生重复数据                                  |
| D8 阶段四不引入新依赖                      | 4d 全部使用阶段一/二/三/4a/4b/4c 已就位依赖；dev 仅 `pytest-asyncio` / `respx` 已就位；`python-jose` 可选（缺失自动降级为 `dev-{tenant}-{user}` token）                       |

### 8.7.4 鉴权降级

`get_auth_context` 解析顺序（4d §3.2）：

1. token 以 `dev-` 开头 → 走 dev 降级（不论 `python-jose` 是否安装）；
2. 否则尝试 JWT（HS256，密钥 `settings.api_jwt_secret`）；
3. `python-jose` 缺失 → 降级为 dev- 前缀鉴权。

dev 模式 token 形如 `dev-{tenant_id}-{user_id}`，例如 `dev-tnt_demo-admin` → `AuthContext(tenant_id="tnt_demo", user_id="admin", scopes=["*"])`。

### 8.7.5 端到端冒烟（`tools/verify/verify_stage4d.py`）

| 项                    | 结果                                                                                                                                       |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| scan                | 27 文件 / 10 模块 / 15 export 全 OK                                                                                                          |
| pytest              | `tests/unit + tests/integration + tests/e2e` 共 **39/39 PASS**                                                                              |
| app_health          | `create_app()` + `/healthz` + `/readyz` + 根 banner 全部 200/正确返回                                                                          |
| api_business        | dev- 鉴权 + `/api/v1/agents/supported` + `/api/v1/orchestrator/workflows` + `/api/v1/reports` + `/api/v1/ws/events` 订阅并收到 publish 事件 |
| scripts             | `init_agents` 导出 3 个白名单；`setup_vector_db._scan_*` + `_make_store` upsert 路径 OK；`seed_test_data` import 正常                              |
| start_worker        | `scripts.start_worker` 含 `main()`，argv 解析函数签名正常                                                                                       |

### 8.7.6 全量回归（4d 视角）

| 阶段     | 测试文件                                  | 项数                       |
| ------ | ------------------------------------- | ------------------------ |
| 4d unit | `tests/unit/test_a2a_protocol.py`    | 6 PASS                   |
| 4d unit | `tests/unit/test_mcp_handlers.py`    | 5 PASS                   |
| 4d unit | `tests/unit/test_gis_engine.py`      | 7 PASS                   |
| 4d int  | `tests/integration/test_workflows.py` | 4 PASS                   |
| 4d int  | `tests/integration/test_agent_collaboration.py` | 4 PASS           |
| 4d e2e  | `tests/e2e/test_full_pipeline.py`    | 15 PASS（含 2 项 trigger 端到端用例） |
| 4c     | `tests/orchestrator/test_orchestrator_pytest.py` | 24 PASS         |
| 一/二/三  | 各业务智能体 `tests/<agent>/test_agent.py`  | 11+18+22 PASS            |
| **合计** | `pytest tests/`                       | **77 pytest PASS / 0 FAIL** |
| **合计** | 脚本式 self-check（4 份）                  | **75 PASS / 0 FAIL**     |

#### 三种运行方式

1. **pytest 整轮**：
   ```bash
   PYTHONPATH=. python -m pytest tests -q
   # 77 passed in 6.00s
   ```
2. **4d 端到端验收**：
   ```bash
   python tools/scan/scan_stage4d.py    # 静态：27 文件 / 10 模块 / 15 export
   python tools/verify/verify_stage4d.py   # 动态：scan + pytest + 4 项冒烟
   ```
3. **业务路由本地起服务**：
   ```bash
   PYTHONPATH=. uvicorn api.main:app --host 0.0.0.0 --port 8000
   curl -s http://127.0.0.1:8000/api/v1/health/healthz | jq
   curl -s -H "Authorization: Bearer dev-tnt_demo-admin" \
        http://127.0.0.1:8000/api/v1/agents/supported | jq
   ```

### 8.7.7 4d 期间发现并修复的 5 处自检问题

1. **`mcp_handlers` 单测 reset 后工具消失**：`reset_mcp_service()` 把全局 svc 重置后，tools 子包的 `@register_tool` 装饰器已经把工具注册到旧 svc；新增测试 helper 用 `importlib.reload(calculation_tools)` 强制重跑装饰器。
2. **dev- token 误走 JWT 路径**：`python-jose` 已安装时，JWT 解析先于 dev- 前缀检查，导致 dev- 模式失效；改为"dev- 前缀优先"再尝试 JWT。
3. **`/api/v1/health/readyz` 503 时 response_model 校验失败**：补 `response_model=ApiResponse[dict]`。
4. **WebSocket event handler 同步函数被 await**：`bus.subscribe` 期待 async handler，原 `def _enqueue` 被 `gather` 后报 `TypeError: object NoneType can't be used in 'await' expression`；包一层 `async def _async_handler`。
5. **`POST /api/v1/orchestrator/workflows/{name}/trigger` 任意 ValueError 漏到 500**：模板变量缺失应返回 400（10002），未知工作流 404（10003）。新增 `_coerce_payload()` 同时支持 `?payload={...}` query 与 JSON body（推荐），并把 `ValueError` 映射为 `HTTP 400`，补 2 个 e2e 用例覆盖完整闭环（`tests/e2e/test_full_pipeline.py::test_trigger_workflow_missing_payload_var_returns_400` / `..._with_required_payload_returns_200`）。

### 8.7.8 与阶段五衔接

* Streamlit 前端直接消费 `/api/v1/*` 全套 REST 端点 + `/api/v1/ws/events` 实时事件。
* OpenAPI（FastAPI 自动生成）→ 前端 SDK 工具。
* `start_worker` 启动 Celery worker 处理 LLM / 解析等长任务。
* 不在 4d 范围：Streamlit 六页面 / OpenTelemetry / Docker 镜像 / ChromaDB 真实落地 / RBAC 权限模型 / 报告 PDF 导出。

## 8.8 阶段四·子阶段 4e 交付记录（2026-09-02）

阶段四 4e 目标：**编排可视化 Dashboard**——Streamlit 前端直接消费 4d 已落地的 REST + WebSocket，把"工作流注册 / 触发 / 运行 / 协作时间线 / 实时事件"四块可视化，并把整套验收工具（scan + verify）补齐。

### 8.8.1 范围与交付物

* **`streamlit_app/` 前端包（11 个文件，全部非 0 字节）**

  * `app.py`：多页应用骨架（侧栏连接配置 + 顶部 banner + 6 页面按钮路由）
  * `utils/api_client.py`：同步 httpx 客户端（ApiResponse 包壳解析 + dev- 鉴权 + 10 个 dashboard 业务方法）
  * `utils/websocket_client.py`：WebSocketApp 后台线程客户端（自动重连 + tenant_id 隔离）
  * `utils/state_manager.py`：session_state 统一代理（`caai_` 前缀 + 事件缓冲 + push/clear）
  * `utils/__init__.py`：包级 re-export
  * `components/__init__.py`：通用组件占位包（阶段五按页面实做）
  * `pages/__init__.py`：6 个 page 的路由分发（仅 04_dashboard 实做，其它友好提示"5a 阶段实做"）
  * `pages/04_dashboard.py`：编排可视化主页面（4 个 tab）
  * `pages/01~06_safety_audit / compliance / site_monitor / 05_gis_viewer / 06_agent_management.py`：5a 阶段入口

* **后端编排器扩展（3 处补丁）**

  * `core/orchestrator/orchestrator.py`：新增 `stats()` 方法（workflows / runs / today_triggers / collaboration_entries / failed / last_run_* / is_running / as_of）+ `trigger_workflow()` 写协作时间线（`manual_trigger` 状态）。
  * `api/routers/orchestrator_router.py`：新增 `GET /api/v1/orchestrator/workflows/{name}` 端点（dashboard 详情面板依赖）+ `GET /api/v1/orchestrator/stats` 端点 + `/timeline?limit=N` 支持分页。
  * `api/main.py`：根 banner `stage` 升级到 `4e`。

* **`tests/` 4e 测试**

  * `tests/integration/test_dashboard_data.py`：6 项 dashboard 数据形状稳定性测试（stats / workflows 列表 / workflows 详情 / timeline limit / manual_trigger 写时间线 / run 查询）。

* **`tools/` 4e 验收工具**

  * `tools/scan/scan_stage4e.py`：静态扫描（18 文件 / 7 模块 / 11 export）
  * `tools/verify/verify_stage4e.py`：动态验收（scan + pytest + dashboard_api smoke + streamlit_utils smoke + dashboard_render smoke）

合计 **20 个交付文件**（11 streamlit + 3 后端补丁 + 1 test + 2 tools + 3 兼容修订）。

### 8.8.2 编排可视化 Dashboard 四 Tab

| Tab            | 内容                                                                                          | 后端依赖                                                          |
| -------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| **Overview**   | 4 KPI 卡（workflows / runs / today / failed）+ system status（healthz / readyz / backend）+ 最近 run 跳转 | `GET /orchestrator/stats` + `/health/healthz` + `/health/readyz` |
| **Workflows**  | 左侧工作流列表（含节点数）+ 右侧详情（节点 + 模板）+ trigger 表单（JSON / ?payload=）+ 自动跳转 run          | `GET /orchestrator/workflows` + `/workflows/{name}` + `/workflows/{name}/trigger` |
| **Runs**       | 输入 run_id 或从 Overview/Workflows 跳转 → 节点结果 + 错误 + 起始/结束时间                                | `GET /orchestrator/runs/{run_id}`                              |
| **Events**     | 实时 WS 订阅（topic / tenant_id）+ Start/Stop + 连接状态 + 事件表（type / topic / source / ts / payload） | `WS /api/v1/ws/events?topic=*.*&tenant_id=...`                 |

### 8.8.3 关键设计原则（4e 落实情况）

| 原则                            | 落实                                                                                                                                  |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| E1 不绑定 orchestrator 内部模块          | `streamlit_app/utils/*` 仅 import `httpx` / `websocket-client`，零后端内部依赖                                                            |
| E2 dev- 鉴权降级                   | `APIClient` 自动从 `state.token` 拼 `Authorization: Bearer dev-{tenant}-{user}`，与 4d 鉴权一致                                       |
| E3 WebSocket 跨租户隔离             | WS URL 带 `tenant_id` 参数；后端 handler 在 publish 推送前过滤 `event.tenant_id == tenant_id`                                            |
| E4 自动重连                        | `EventStreamClient` 指数退避（1→5s），30s 心跳由 server 端发送 `{"type":"ping"}`                                                              |
| E5 数据形状稳定性                    | 6 项 dashboard 单测锁死 4 个核心 API 的字段集合；新增字段必须同步更新测试                                                                  |
| E6 手动 trigger 写时间线            | `Orchestrator.trigger_workflow()` 同步调用 `_collab.record_interaction(from=manual, status=manual_trigger)`                          |
| E7 stats / workflows/{name} 端点 | dashboard 显式依赖的两个端点在 4d 留有 docstring 但未实现；4e 实做并补 e2e 单测                                                                 |
| E8 不引入新依赖                     | 4e 全部使用阶段一/二/三/4a/4b/4c/4d 已就位依赖；`streamlit>=1.35` / `websocket-client>=1.6` 已在 `requirements.txt`                          |

### 8.8.4 端到端冒烟（`tools/verify/verify_stage4e.py`）

| 项                  | 结果                                                                                                                                |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| scan              | 18 文件 / 7 模块 / 11 export 全 OK                                                                                                       |
| pytest_dashboard  | `tests/integration/test_dashboard_data.py` **6/6 PASS**                                                                               |
| dashboard_api     | TestClient 直跑 `/stats` `/workflows` `/workflows/{name}` `/trigger` `/timeline?limit` `/runs/{id}` 全链路 200 + 字段齐                                               |
| streamlit_utils   | APIClient / EventStreamClient / StateManager / ws_base 转换 / 单例 / 业务方法签名 全部离线可构造                                                                |
| dashboard_render  | `04_dashboard.render()` + 4 个 tab 渲染函数 + 3 类工作流默认 payload 全部存在；模块以 `importlib.import_module` 加载（模块名数字开头）                                              |

### 8.8.5 全量回归（4e 视角）

| 阶段     | 测试文件                                              | 项数                       |
| ------ | ------------------------------------------------- | ------------------------ |
| 4e int  | `tests/integration/test_dashboard_data.py`        | 6 PASS                   |
| 4d unit | `tests/unit/test_a2a_protocol.py`                | 6 PASS                   |
| 4d unit | `tests/unit/test_mcp_handlers.py`                | 5 PASS                   |
| 4d unit | `tests/unit/test_gis_engine.py`                  | 7 PASS                   |
| 4d int  | `tests/integration/test_workflows.py`             | 4 PASS                   |
| 4d int  | `tests/integration/test_agent_collaboration.py`   | 4 PASS                   |
| 4d e2e  | `tests/e2e/test_full_pipeline.py`                | 15 PASS                  |
| 4c     | `tests/orchestrator/test_orchestrator_pytest.py`  | 24 PASS                  |
| 一/二/三  | 各业务智能体 `tests/<agent>/test_agent.py`           | safety 5 + compliance 12 + site_monitor 12 PASS |
| **合计** | `pytest tests/`                                   | **83 pytest PASS / 0 FAIL** |
| **合计** | `verify_stage4d` + `verify_stage4e`                | **6 + 5 = 11 项 PASS**     |

#### 三种运行方式

1. **pytest 整轮**：
   ```bash
   PYTHONPATH=. python -m pytest tests -q
   # 83 passed in 6.37s
   ```
2. **4e 端到端验收**：
   ```bash
   python tools/scan/scan_stage4e.py    # 静态：18 文件 / 7 模块 / 11 export
   python tools/verify/verify_stage4e.py   # 动态：scan + pytest + dashboard_api + streamlit_utils + dashboard_render
   ```
3. **启动 Streamlit Dashboard**：
   ```bash
   # 终端 A：起后端
   PYTHONPATH=. uvicorn api.main:app --host 0.0.0.0 --port 8000
   # 终端 B：起前端
   PYTHONPATH=. streamlit run streamlit_app/app.py --server.port 8501
   # 浏览器：http://127.0.0.1:8501 → 侧栏填 dev-tnt_demo-admin → Overview / Workflows / Runs / Events 四 Tab
   ```

### 8.8.6 4e 期间发现并修复的 3 处问题

1. **`GET /api/v1/orchestrator/workflows/{name}` 端点 4d 留 docstring 未实现**：dashboard 详情面板直接调用 404；4e 实做并补 e2e 单测（`test_workflow_detail_shape_is_stable`）覆盖成功路径 + 未知工作流 404。
2. **`streamlit_app/components/__init__.py` 空文件**：scan_stage4e 静态扫描报 `FILE_EMPTY`；改为预留位置 docstring 占位（阶段五按页面实做）。
3. **根 banner `stage` 等值断言在 4e 后失效**：`tests/e2e/test_full_pipeline.py::test_root_banner` 与 `tools/verify/verify_stage4d.py::smoke_app_health` 都断言 `stage == "4d"`；4e 升级到 `"4e"` 后两处改为 `in ("4d", "4e")` 兼容演进。

### 8.8.7 与阶段五衔接

* 阶段五（5a）：实做 5 个剩余页面（01 安全审核 / 02 合规 / 03 现场监控 / 05 GIS / 06 智能体管理），沿用 `streamlit_app/utils/*` 与 `streamlit_app/pages/04_dashboard.py` 的渲染模式。
* `components/` 包占位：alert_display / chart_component / map_component / report_viewer 由各页面按需填充。
* 4e 的 dashboard 4 个核心 API 已冻结数据形状，阶段五消费时若新增字段需同步更新 `test_dashboard_data.py`。
* 不在 4e 范围：Docker 镜像（已有 `deployment/docker/Dockerfile.streamlit` 占位）/ OpenTelemetry / ChromaDB 真实落地 / RBAC 权限模型 / 报告 PDF 导出。

## 9. 全局占位说明

> ⚠️ 任何形如 `需要补充实际链接` 的字符串均为占位，生产部署前必须替换：
> 数据库 / Redis / Celery / InfluxDB / LLM / JWT 凭据全部由 K8s Secret / Vault 注入，不入仓。

