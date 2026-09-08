# 建筑工程智能体集群 API 文档

> 版本：4d（2026-09-02）
> 本文档描述 `api.main:app` 暴露的全部 HTTP + WebSocket 端点。所有响应统一为
> `ApiResponse[T] = {code, message, data, request_id, timestamp}`，错误码
> 与 `common/error_codes.py` 对齐（业务 1xxxx / A2A 5xxxx / MCP 6xxxx 等）。

## 0. 启动与访问

```bash
# 1) 安装依赖（一次性）
pip install -r requirements.txt

# 2) 配置环境（dev 默认值可用）
export PYTHONPATH=.
export ENV=dev   # 可选；默认 dev

# 3) 启动
uvicorn api.main:app --host 0.0.0.0 --port 8000

# 4) 访问
curl -s http://127.0.0.1:8000/api/v1/health/healthz | jq
curl -s -H "Authorization: Bearer dev-tnt_demo-admin" \
     http://127.0.0.1:8000/api/v1/agents/supported | jq
# OpenAPI 文档：
open http://127.0.0.1:8000/docs
```

启动后 lifespan 会自动：

1. 调用 `init_agent_manager()` 初始化进程级单例；
2. 调用 `init_orchestrator()` 订阅 4 类事件 + 注册 6 个 system action；
3. 关闭时按 `bus.reset() → orchestrator.stop() → agent_manager.shutdown()` 顺序清理。

## 1. 鉴权

`get_auth_context` 解析顺序：

1. **dev- 前缀**（不论 `python-jose` 是否安装）：`Authorization: Bearer dev-{tenant_id}-{user_id}`
   * 例：`dev-tnt_demo-admin` → `AuthContext(tenant_id="tnt_demo", user_id="admin", scopes=["*"])`
2. **JWT**（HS256，密钥 `settings.api_jwt_secret`）：`Authorization: Bearer <jwt>`
   * 必须包含 `tenant_id` claim；`user_id` / `scopes` 可选；
   * 解析失败 → 401（错误码 30001）。
3. **未配置 Authorization** → 401（错误码 30001）。

4d 不要求鉴权的端点仅：`/api/v1/health/healthz`、`/api/v1/health/readyz`、`/`、WebSocket。

## 2. 响应结构

成功：

```json
{
  "code": "0",
  "message": "ok",
  "data": { ... },
  "request_id": null,
  "timestamp": "2026-09-02T07:42:27+00:00"
}
```

失败（业务错误）：

```json
{
  "code": "10003",
  "message": "报告不存在: rpt_xxx",
  "data": { "details": {} },
  "request_id": null,
  "timestamp": "2026-09-02T07:42:27+00:00"
}
```

Pydantic 校验失败（422）：`{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`，不通过 ApiResponse 包装。

## 3. 端点清单

| # | 端点                                                | 方法     | 鉴权 | 描述                              |
| - | ------------------------------------------------- | ------ | -- | ------------------------------- |
| 1 | `/`                                              | GET    | 否  | 根 banner（endpoint 列表）              |
| 2 | `/api/v1/health/healthz`                          | GET    | 否  | 存活探针                            |
| 3 | `/api/v1/health/readyz`                           | GET    | 否  | 就绪探针                            |
| 4 | `/api/v1/agents`                                 | GET    | 是  | 列出当前租户可调用的业务智能体（白名单 + 已实例化）         |
| 5 | `/api/v1/agents/supported`                       | GET    | 是  | 列出 AgentManager 支持的智能体白名单        |
| 6 | `/api/v1/agents/{name}/card`                     | GET    | 是  | 读取指定智能体的 Agent Card              |
| 7 | `/api/v1/agents/{name}/invoke`                   | POST   | 是  | 通过 HTTP 触发智能体 handle              |
| 8 | `/api/v1/tasks/{task_id}`                        | GET    | 是  | 查询任务状态                          |
| 9 | `/api/v1/tasks/{task_id}`                        | DELETE | 是  | 取消任务                            |
| 10 | `/api/v1/reports`                               | GET    | 是  | 列出报告（按 project_id + 分页）            |
| 11 | `/api/v1/reports/{report_id}`                    | GET    | 是  | 读取报告详情                          |
| 12 | `/api/v1/reports/{report_id}/download`           | GET    | 是  | 下载报告（md）                       |
| 13 | `/api/v1/orchestrator/workflows`                 | GET    | 是  | 列出所有工作流                         |
| 14 | `/api/v1/orchestrator/workflows/{name}`          | GET    | 是  | 读取工作流定义                         |
| 15 | `/api/v1/orchestrator/workflows/{name}/trigger`  | POST   | 是  | 触发工作流                           |
| 16 | `/api/v1/orchestrator/runs/{run_id}`             | GET    | 是  | 查询工作流执行状态                       |
| 17 | `/api/v1/orchestrator/timeline`                  | GET    | 是  | 协作时间线（按租户）                      |
| 18 | `/api/v1/ws/events`                             | WS     | 否  | 实时事件订阅                          |
| 19 | `/api/v1/a2a/...`                               | 多     | 否  | A2A REST + JSON-RPC 入口（阶段二已存在）   |
| 20 | `/api/v1/mcp/...`                               | 多     | 否  | MCP 资源/工具/提示词（阶段二已存在）          |

## 4. 端点详述

### 4.1 `GET /api/v1/health/healthz`

存活探针（K8s livenessProbe 推荐）。**总是 200**。

```json
{
  "code": "0", "message": "ok",
  "data": { "status": "ok", "checked_at": "2026-09-02T07:42:27+00:00" }
}
```

### 4.2 `GET /api/v1/health/readyz`

就绪探针（K8s readinessProbe 推荐）。聚合 4 类检查，**任一失败 → 503**：

* `database`：连接测试（4d 占位：未配置时返回 `configured: false`，视为 OK）
* `redis`：连接测试（同上）
* `celery`：Celery app 可加载（broker=`memory://` 视为 mock OK）
* `event_bus`：EventBus 单例可获取

```json
{
  "code": "0", "message": "ok",
  "data": {
    "status": "ok",
    "checked_at": "2026-09-02T07:42:27+00:00",
    "checks": {
      "database":  { "ok": true, "configured": false, "mode": "placeholder" },
      "redis":     { "ok": true, "configured": false, "mode": "placeholder" },
      "celery":    { "ok": true, "app": "construction_ai_agents", "broker": "memory://", "is_mock": true },
      "event_bus": { "ok": true, "published_count": 0, "delivered_count": 0, "subscribers": 0 }
    }
  }
}
```

### 4.3 `GET /api/v1/agents`

列出当前租户可调用的业务智能体（白名单 + 已实例化）：

```json
{
  "code": "0", "message": "ok",
  "data": {
    "tenant_id": "tnt_demo",
    "agents": [
      {
        "name": "safety_audit_agent",
        "version": "1.0.0",
        "description": "...",
        "skills": ["safety.plan_review", "safety.drawing_review", "safety.report_draft"],
        "instantiated": true
      },
      ...
    ],
    "total": 3
  }
}
```

### 4.4 `GET /api/v1/agents/supported`

```json
{
  "code": "0", "message": "ok",
  "data": { "supported": ["safety_audit_agent", "compliance_agent", "site_monitor_agent"] }
}
```

### 4.5 `GET /api/v1/agents/{name}/card`

```json
{
  "code": "0", "message": "ok",
  "data": {
    "name": "safety_audit_agent",
    "version": "1.0.0",
    "description": "...",
    "protocol_version": "1.0",
    "skills": [
      { "skill_id": "safety.plan_review", "name": "...", "description": "..." }
    ]
  }
}
```

`name` 不在白名单 → 50001。

### 4.6 `POST /api/v1/agents/{name}/invoke`

通过 HTTP 触发智能体（4d 把入参包成 A2AMessage → 调 `BaseAgent.handle()`）。

请求体：

```json
{
  "method": "agent.send_message",       // 可选，默认 agent.send_message
  "params": {
    "project_id": "prj_xxx",            // 透传进 metadata
    "plan_id": "plan_xxx",
    "message": { "text": "请审查..." }     // 可选纯文本；也可直接 "text": "..."
  }
}
```

响应：

```json
{
  "code": "0", "message": "ok",
  "data": {
    "task_id": "task_01HXXX",
    "agent": "safety_audit_agent",
    "method": "agent.send_message",
    "tenant_id": "tnt_demo",
    "state": "COMPLETED",
    "reply": {
      "message_id": "msg_01HXXX",
      "parts": [
        { "type": "text", "text": "..." },
        { "type": "data", "data": { ... } }
      ],
      "metadata": { ... }
    }
  }
}
```

错误：

* `name` 不在白名单 → 50001（500 Internal Server Error）
* 智能体 handle 抛 `AppException` → 自动映射到对应 HTTP 状态码
* 其他异常 → 10001（500 Internal Server Error）

### 4.7 `GET /api/v1/tasks/{task_id}`

查询任务状态（Celery 或 mock）：

```json
{
  "code": "0", "message": "ok",
  "data": {
    "task_id": "task_01HXXX",
    "tenant_id": "tnt_demo",
    "state": "PENDING",
    "result": null,
    "is_mock": true
  }
}
```

`state` 取值：`PENDING` / `RUNNING` / `SUCCESS` / `FAILURE` / `REVOKED`。

### 4.8 `DELETE /api/v1/tasks/{task_id}`

取消任务。已完成的任务返回 `cancelled=false`：

```json
{
  "code": "0", "message": "ok",
  "data": { "task_id": "task_01HXXX", "tenant_id": "tnt_demo", "cancelled": true }
}
```

### 4.9 `GET /api/v1/reports`

按 `project_id` 过滤 + 分页（首版走内存 store；阶段五接 DB ORM）：

```
GET /api/v1/reports?project_id=prj_xxx&page=1&page_size=20
```

```json
{
  "code": "0", "message": "ok",
  "data": {
    "items": [
      {
        "report_id": "rpt_xxx",
        "tenant_id": "tnt_demo",
        "project_id": "prj_xxx",
        "title": "...",
        "conclusion": "pass",
        "status": "signed",
        "created_at": "2026-09-01T00:00:00Z"
      }
    ],
    "total": 5, "page": 1, "page_size": 20
  }
}
```

### 4.10 `GET /api/v1/reports/{report_id}`

读取报告详情（Markdown + 签章 + 完整字段）。`report_id` 必须以 `rpt_` 开头，否则 400。

### 4.11 `GET /api/v1/reports/{report_id}/download`

下载报告（首版仅 `format=md`）：

```
GET /api/v1/reports/rpt_xxx/download?format=md
```

```json
{
  "code": "0", "message": "ok",
  "data": {
    "report_id": "rpt_xxx",
    "format": "md",
    "size": 1234,
    "content": "# 审查报告\n\n...",
    "signature": "hmac-sha256:..."
  }
}
```

阶段五接 `format=pdf`。

### 4.12 `GET /api/v1/orchestrator/workflows`

列出所有已注册工作流（来自 `core.orchestrator.workflow_engine.WorkflowEngine`）：

```json
{
  "code": "0", "message": "ok",
  "data": {
    "workflows": [
      { "name": "monitor_alert_to_audit", "description": "监控告警 → 安全审查", "node_count": 2 },
      { "name": "compliance_followup",     "description": "审查失败 → 合规复核", "node_count": 2 },
      { "name": "regulation_record",       "description": "法规更新 → 记录",   "node_count": 1 }
    ]
  }
}
```

### 4.13 `GET /api/v1/orchestrator/workflows/{name}`

读取工作流定义（节点 + 依赖）：

```json
{
  "code": "0", "message": "ok",
  "data": {
    "name": "monitor_alert_to_audit",
    "description": "...",
    "nodes": [
      { "node_id": "notify",     "kind": "system", "system_action": "services.notify", "params": {...} },
      { "node_id": "start_audit","kind": "agent",  "agent": "safety_audit_agent",   "params": {...}, "depends_on": ["notify"] }
    ]
  }
}
```

### 4.14 `POST /api/v1/orchestrator/workflows/{name}/trigger`

触发工作流。`payload` 通过 query 传 JSON 字符串：

```
POST /api/v1/orchestrator/workflows/monitor_alert_to_audit/trigger?payload={"alert_id":"a1"}
```

```json
{
  "code": "0", "message": "ok",
  "data": { "run_id": "run_01HXXX", "state": "RUNNING" }
}
```

工作流不存在 → 404（错误码 10003）。

### 4.15 `GET /api/v1/orchestrator/runs/{run_id}`

查询工作流执行状态（节点完成情况 + 错误）。

### 4.16 `GET /api/v1/orchestrator/timeline`

协作时间线（按 `tenant_id` 过滤，可选 `limit`）：

```
GET /api/v1/orchestrator/timeline?tenant_id=tnt_demo&limit=50
```

### 4.17 `WS /api/v1/ws/events`

WebSocket 实时事件订阅：

```
ws://host/api/v1/ws/events?topic=alert.*&tenant_id=tnt_demo
```

* `topic` 支持通配符（`*` 表示所有 `*.*`）。
* `tenant_id` 必填；缺失 → close 1008。
* 服务端每 30s 发送 `{"type":"ping"}`，客户端应回 `pong`（4d 暂不强制）。
* 推送的事件结构：
  ```json
  {
    "type": "event",
    "topic": "alert.triggered",
    "tenant_id": "tnt_demo",
    "source": "site_monitor_agent",
    "event_id": "evt_01HXXX",
    "payload": { ... },
    "occurred_at": "2026-09-02T07:42:27+00:00"
  }
  ```
* 跨租户事件自动过滤。

## 5. 错误码

| 范围     | 含义              | 例子                                            |
| ------ | --------------- | --------------------------------------------- |
| 0      | 成功              | -                                             |
| 1xxxx  | 业务错误            | 10001 内部错误 / 10002 参数非法 / 10003 资源不存在      |
| 3xxxx  | 鉴权错误            | 30001 未授权 / token 失效                            |
| 5xxxx  | A2A 协议错误        | 50001 智能体不存在 / 50002 消息非法 / 50005 任务不存在        |
| 6xxxx  | MCP 协议错误        | 60001 资源不存在 / 60002 工具不存在                       |
| HTTP   | 状态码             | 401 / 403 / 404 / 422 / 500 / 503 / 504         |

详细映射见 `common/error_codes.py` 与 `common/exceptions.py`。

## 6. 端到端示例

```bash
TOKEN="Bearer dev-tnt_demo-admin"
HOST="http://127.0.0.1:8000"

# 1) 健康检查
curl -s $HOST/api/v1/health/readyz | jq .data.status

# 2) 列出白名单
curl -s -H "Authorization: $TOKEN" $HOST/api/v1/agents/supported | jq

# 3) 触发 safety_audit_agent
curl -s -X POST -H "Authorization: $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "method": "agent.send_message",
    "params": {
      "project_id": "prj_demo",
      "plan_id": "plan_demo",
      "message": { "text": "请审查该方案" }
    }
  }' \
  $HOST/api/v1/agents/safety_audit_agent/invoke | jq

# 4) 列出工作流 + 触发
curl -s -H "Authorization: $TOKEN" $HOST/api/v1/orchestrator/workflows | jq
curl -s -X POST -H "Authorization: $TOKEN" \
  "$HOST/api/v1/orchestrator/workflows/monitor_alert_to_audit/trigger?payload=%7B%22alert_id%22%3A%22a1%22%7D" | jq

# 5) WebSocket（wscat 示例）
wscat -c "ws://127.0.0.1:8000/api/v1/ws/events?topic=*.*&tenant_id=tnt_demo"
```

## 7. 阶段五衔接

* Streamlit 前端直接消费 `/api/v1/*` 全套端点 + `/api/v1/ws/events` 实时事件；
* OpenAPI 文档（`/docs`）→ 客户端 SDK 自动生成；
* Celery worker 由 `python scripts/start_worker.py --queues default,alerts` 启动，处理 LLM / 解析等长任务；
* RBAC 权限模型在阶段五落地（4d 仅做租户提取 + 身份记录）。
