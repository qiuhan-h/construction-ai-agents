# 运维手册（Operations Manual）

> 项目：智建云审 construction-ai-agents
> 配套文档：[部署操作手册](deployment_runbook.md) · [阶段七规划](release_plan_stage7.md)
> 适用版本：阶段六交付（v0.6.x）→ 阶段七上线

---

## 1. 部署架构总览

### 1.1 服务拓扑

| 服务 | 镜像 | 端口 | 职责 |
|---|---|---|---|
| api | `caai-api` | 8000 | FastAPI 主应用，聚合所有路由 + lifespan |
| worker | `caai-worker` | - | Celery 异步任务（报告生成、通知推送） |
| streamlit | `caai-streamlit` | 8501 | 多页前端控制台 |
| a2a | `caai-a2a` | 8080 | Agent-to-Agent 通信服务 |
| mcp | `caai-mcp` | 8090 | MCP 资源/工具/提示词服务 |
| edge | `caai-edge` | 9000 | 边缘端轻量服务（BIM/GIS 离线） |

### 1.2 依赖中间件

| 组件 | 用途 | 端口 |
|---|---|---|
| PostgreSQL | 业务数据（租户/项目/审查/违规/报告） | 5432 |
| Redis | 缓存 + Celery broker/result | 6379 |
| InfluxDB 2.x | 传感器高频时序数据 | 8086 |
| MQTT Broker | IoT 设备消息接入 | 1883 |

### 1.3 启动顺序

```
postgres → redis → influxdb → api → worker → a2a/mcp → streamlit
```

> docker-compose 已配置 `depends_on` 与 `healthcheck`，按 `docker-compose up -d` 即可按序启动。

---

## 2. Docker 镜像构建与推送

### 2.1 镜像清单

| Dockerfile | 位置 | 多阶段 |
|---|---|---|
| api | `deployment/docker/Dockerfile.api` | 是 |
| worker | `deployment/docker/Dockerfile.worker` | 是 |
| streamlit | `deployment/docker/Dockerfile.streamlit` | 是 |
| a2a | `deployment/docker/Dockerfile.a2a` | 是 |
| mcp | `deployment/docker/Dockerfile.mcp` | 是 |
| edge | `deployment/docker/Dockerfile.edge` | 是 |

### 2.2 构建命令

```bash
# 本地构建全部
docker-compose -f deployment/docker/docker-compose.yml build

# 单独构建
docker build -f deployment/docker/Dockerfile.api -t caai-api:latest .

# 推送到镜像仓库
docker tag caai-api:latest <registry>/caai-api:0.6.0
docker push <registry>/caai-api:0.6.0
```

> 具体镜像仓库地址和认证见 [deployment_runbook.md §4](deployment_runbook.md)。

---

## 3. K8s 部署流程

### 3.1 命名空间与配置

```bash
kubectl apply -f deployment/kubernetes/namespace.yaml
kubectl apply -f deployment/kubernetes/configmap.yaml
kubectl apply -f deployment/kubernetes/secrets.yaml   # CI 渲染后
```

### 3.2 工作负载

```bash
kubectl apply -f deployment/kubernetes/deployments.yaml
kubectl apply -f deployment/kubernetes/services.yaml
kubectl apply -f deployment/kubernetes/ingress.yaml
```

### 3.3 验证

```bash
kubectl -n caai rollout status deploy/api
kubectl -n caai get pods -l app.kubernetes.io/name=construction-ai-agents
```

> K8s 清单详情见 `deployment/kubernetes/` 目录；Sealed Secrets 渲染见 [secrets.yaml](../deployment/kubernetes/secrets.yaml)。

---

## 4. 可观测性

### 4.1 健康检查端点

| 端点 | 用途 |
|---|---|
| `GET /api/v1/health/healthz` | 存活探针（liveness） |
| `GET /api/v1/health/readyz` | 就绪探针（readiness，含子组件状态） |

### 4.2 日志

- 日志级别由 `LOG_LEVEL` 环境变量控制（生产建议 `INFO`）；
- 日志目录：`data/logs/`（容器内 `/app/data/logs`）；
- K8s 下自动采集 stdout/stderr。

### 4.3 Prometheus 指标

- 设置 `ENABLE_METRICS=1` 启用；
- 指标端点：`GET /metrics`（core/observability/exporter.py）；
- Grafana 仪表盘配置见 `deployment/monitoring/`。

### 4.4 OpenTelemetry 链路追踪

- 设置 `ENABLE_OTEL=1` + `OTEL_EXPORTER_OTLP_ENDPOINT`；
- 一次请求可在 trace 中看到 API → chain → LLM 全链路。

---

## 5. 数据库迁移

### 5.1 Alembic 命令

```bash
# 升级到最新版本
PYTHONPATH=. alembic -c alembic.ini upgrade head

# 回退一个版本
PYTHONPATH=. alembic -c alembic.ini downgrade -1

# 查看当前版本
PYTHONPATH=. alembic -c alembic.ini current
```

### 5.2 迁移脚本位置

- `models/database/migrations/versions/0001_initial.py` — 初始 schema（全部表）

### 5.3 全新库初始化

```bash
# 1. 创建数据库
createdb construction_agents

# 2. 一条命令建表
PYTHONPATH=. alembic -c alembic.ini upgrade head
```

> ORM/内存双后端在 CI 均跑通（verify_all.py pytest 144P 验证）。

---

## 6. 故障排查

### 6.1 服务无法启动

| 症状 | 排查 |
|---|---|
| 启动报 JWT 占位 | `APP_ENV=prod` 时占位配置 fail-fast，见 `tools/verify/verify_prod_config.py` |
| 数据库连接失败 | 检查 `DATABASE_URL`；docker-compose 内用 `postgres` 主机名 |
| Redis 连接失败 | 检查 `REDIS_URL`；docker-compose 内用 `redis` 主机名 |
| LLM 调用失败 | 检查 `LLM_API_KEY` / `LLM_BASE_URL`；mock 模式不产生真实调用 |

### 6.2 健康检查失败

```bash
curl http://localhost:8000/api/v1/health/healthz
curl http://localhost:8000/api/v1/health/readyz
```

`readyz` 返回 503 时检查 `subscribers` 字段，定位哪个子组件降级。

### 6.3 worker 不消费

```bash
celery -A core.celery_app inspect ping
celery -A core.celery_app inspect active
```

---

## 7. 备份与恢复

### 7.1 PostgreSQL

```bash
# 备份
pg_dump -h <host> -U <user> construction_agents > backup_$(date +%Y%m%d).sql

# 恢复
psql -h <host> -U <user> -d construction_agents < backup_20260907.sql
```

> 建议设置 cron 定时备份 + 每月恢复演练。

### 7.2 Redis

```bash
redis-cli -h <host> BGSAVE
cp /var/lib/redis/dump.rdb /backups/redis_$(date +%Y%m%d).rdb
```

### 7.3 向量库

- ChromaDB：快照 `data/chroma/` 目录；
- 内存模式：无持久化，重启丢失。

### 7.4 InfluxDB

```bash
influx backup --host http://<host>:8086 /backups/influxdb_$(date +%Y%m%d)
```

---

## 8. 密钥轮换

| 密钥 | 轮换周期 | 操作 |
|---|---|---|
| API_JWT_SECRET | 季度 | 生成新密钥 → 更新 K8s Secret → 滚动重启 |
| LLM_API_KEY | 按供应商策略 | 更新 .env / Secret → 重启 |
| SMS AccessKey | 半年 | 阿里云/腾讯云控制台轮换 |
| APS_CLIENT_SECRET | 半年 | Autodesk 开发者后台轮换 |

---

*交叉引用：[deployment_runbook.md](deployment_runbook.md)（占位怎么填、第三方平台操作）、[release_plan_stage7.md](release_plan_stage7.md)（阶段七规划）。*
