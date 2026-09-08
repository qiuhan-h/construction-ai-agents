# 阶段 5c · 可观测性 / 缓存 / 安全

> 版本：2026-09-03
> 周期：2 周（10 工作日）
> 前置：5b 完成
> 后置：5d CI/CD 与部署

## 1. 目标

把已经能跑的 5 个服务（API / A2A / MCP / Streamlit / Worker）从「能跑」升级到「可观测、可防护、可调优」：
- 每个请求都有 trace / metric / log 三件套；
- 热点数据进入 Redis，二级缓存降低 DB 压力；
- 接入 RBAC + 限流 + 审计，满足合规可追溯要求。

## 2. 关键交付物

### 2.1 可观测性（OpenTelemetry + Prometheus + Loki）

- `core/observability/tracing.py`：OTel TracerProvider 初始化（资源属性含 `service.name` / `service.version` / `deployment.environment`）
- `core/observability/metrics.py`：Prometheus 导出器 + 业务指标（`agent_invocations_total` / `agent_invocation_duration_seconds` / `orchestrator_workflow_runs_total` / `notification_send_total{channel,result}`）
- `core/observability/logging.py`：结构化 JSON 日志（`json-log-formatter`）+ trace_id / span_id 自动注入
- `core/observability/middleware.py`：FastAPI 中间件（`http_request_duration_seconds` / `http_requests_total` / `http_requests_in_progress`）
- 智能体基类 `BaseAgent.handle()` 自动创建 span（attributes: `agent.name` / `task.id` / `tenant.id`）
- A2A / MCP 客户端 span 透传（`traceparent` header）
- 部署文件：`deployment/observability/` 含 Prometheus / Grafana / Tempo / Loki 4 个组件的 Helm values 片段
- Grafana dashboard JSON：4 个（API 总览、智能体性能、通知渠道、数据库）

### 2.2 缓存（Redis）

- `core/cache/redis_cache.py`（已存在）升级：序列化统一 `pickle` + `gzip`，TTL 默认 300s，命名空间 `caai:{tenant_id}:{key}`
- `core/cache/decorators.py`：`@cached(prefix, ttl, key_fn)` 装饰器；空值缓存（防穿透）+ 失败回退（防雪崩）
- 业务接入点：
  - 法规库 / 标准库查询（`regulation_index.query`）— TTL 1800s
  - 案例检索 RAG（`case_retriever.search`）— TTL 600s
  - 编排器工作流定义（`workflows.load`）— TTL 3600s
  - 编排器统计（`orchestrator.stats`）— TTL 30s
- `core/cache/keys.py`：统一 key 生成器（tenant 隔离 + 防前缀冲突）
- 缓存预热脚本 `scripts/warm_cache.py`：冷启动 / 法规更新后触发

### 2.3 安全（RBAC + 限流 + 审计）

- `core/security/rbac.py`：角色定义（`admin` / `operator` / `auditor` / `viewer` / `service`）+ `Permission` 枚举 + `RoleBinding`
- `core/security/policies.py`：策略文件 `config/rbac_policies.yaml`，按租户加载
- `core/security/middleware.py`：
  - `AuthMiddleware`：解析 `Authorization: Bearer <jwt>`，注入 `request.state.user`
  - `RBACMiddleware`：按路由 + 角色判定（FastAPI dependency）
  - `RateLimitMiddleware`：令牌桶（按 `tenant_id` + `endpoint` 维度，可配置 QPS）
- `core/security/audit.py`：`AuditLogger`，记录所有写操作（POST / PUT / DELETE / 触发工作流 / 签字），落 `audit_logs` 表（含 trace_id + user_id + tenant_id + action + target + result + timestamp + ip）
- `models/database/audit_models.py`：`AuditLogTable`（5b.3 仓储模式）
- `api/routers/auth_router.py`：`/api/v1/auth/login` / `/api/v1/auth/me` / `/api/v1/auth/refresh`（JWT 签发与刷新）
- `scripts/gen_test_users.py`：测试用户生成（5 个角色 × 2 租户）

## 3. 任务拆解（按周）

### 第 1 周 · 可观测 + 缓存

| 日 | 任务 | 产出 |
| --- | --- | --- |
| D1 | OTel SDK 接入 + FastAPI 中间件 | `core/observability/` 4 个文件 + 单元测试 |
| D2 | 业务埋点：智能体 / 编排 / 通知 / DB | 4 个核心模块埋点完成 |
| D3 | Prometheus 抓取配置 + Grafana dashboard JSON | 4 个 dashboard + `deployment/observability/prometheus-values.yaml` |
| D4 | Redis 客户端升级 + `@cached` 装饰器 | `core/cache/` 2 个新文件 + 4 业务接入点 |
| D5 | 缓存预热脚本 + 失效策略测试 | `scripts/warm_cache.py` + 雪崩 / 穿透 / 一致性测试 |

### 第 2 周 · 安全 + 收口

| 日 | 任务 | 产出 |
| --- | --- | --- |
| D6 | RBAC 角色 + 策略文件 + 中间件 | `core/security/rbac.py` / `policies.py` / `middleware.py` + 策略 YAML |
| D7 | JWT 鉴权 + `/auth/*` 路由 + 现有 8 个路由接入 | `auth_router.py` + 路由适配 |
| D8 | 限流中间件 + 令牌桶 | `RateLimitMiddleware` + 维度配置（租户 / IP / endpoint） |
| D9 | 审计日志 + `audit_logs` 表 + 5b.3 仓储扩展 | `AuditLogger` + `AuditLogTable` + 4 个写操作埋点 |
| D10 | 集成验证 + 文档 + Stage 5c 验收 | `tools/scan_stage5c.py` / `tools/verify_stage5c.py` / `docs/work_log_stage5c.txt` |

## 4. 验收标准

| 维度 | 标准 | 验证方式 |
| --- | --- | --- |
| 追踪 | 每个 HTTP 请求都能在 Tempo 中找到对应 trace，含 ≥ 3 个 span | `verify_stage5c` 自动化 |
| 指标 | Prometheus 暴露 `/metrics`，含 ≥ 10 个业务指标 | `curl /metrics` + 指标清单 |
| 日志 | 所有 INFO 以上日志均为 JSON，含 `trace_id` | `jq` 抽样验证 |
| 缓存 | 法规查询热路径 P95 ≤ 50ms（DB 600ms+） | 压测前后对比 |
| 限流 | 同一租户 1000 QPS 触发 429 | `locust` 脚本 |
| RBAC | 5 个角色 × 10 个核心接口授权矩阵全通过 | `tests/integration/test_rbac_matrix.py` |
| 审计 | 5 个写操作落 `audit_logs` 表可查询 | `tests/integration/test_audit.py` |

## 5. 风险与回退

| 风险 | 概率 | 影响 | 缓解 / 回退 |
| --- | --- | --- | --- |
| OTel SDK 拖慢请求 | 中 | 中 | 异步导出 + 采样率 10%；性能下降 > 5% 立即降级 |
| Redis 故障 | 中 | 高 | `redis_cache` 已有 "Redis 不可用 → 直接走 DB" 兜底（5b 风格），监控告警 |
| RBAC 策略过严 | 中 | 中 | 先观察 / 列表，1 周后收紧；提供 `super_admin` 紧急通道 |
| 审计日志写入慢 | 低 | 中 | 异步批量写 + 本地缓冲；高峰 ≥ 1000 条/s 时降采样 |
| JWT 密钥泄露 | 低 | 高 | 短期 15min + 刷新 7d，泄漏可主动失效；密钥在 K8s Secret |

## 6. 阶段出口

- 5 个服务全部接入 OTel + Prometheus + Loki + Redis；
- 5 个角色 × 10 个接口授权矩阵全 PASS；
- 5 个写操作审计可查；
- `tools/verify_stage5c.py` 全 PASS；
- `docs/architecture.md` §阶段五·子阶段 5c 记录已写。
