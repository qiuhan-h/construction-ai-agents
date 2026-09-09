<div align="center">

# ArchiMind 建筑全生命周期智能管控平台

**建筑工程多智能体协作平台 — 安全审核 · 合规校验 · 现场监控**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen.svg)](CONTRIBUTING.md)

<br>

[![Architecture](https://img.shields.io/badge/topic-architecture-8A2BE2)](https://github.com/topics/architecture)
[![AI Agents](https://img.shields.io/badge/topic-ai--agents-00BCD4)](https://github.com/topics/ai-agents)
[![LLM](https://img.shields.io/badge/topic-llm-9C27B0)](https://github.com/topics/llm)
[![A2A](https://img.shields.io/badge/topic-a2a--protocol-FF6B35)](https://github.com/topics/a2a)
[![MCP](https://img.shields.io/badge/topic-mcp-007EC6)](https://github.com/topics/mcp)
[![FastAPI](https://img.shields.io/badge/topic-fastapi-009688)](https://github.com/topics/fastapi)
[![Construction](https://img.shields.io/badge/topic-construction-FF9800)](https://github.com/topics/construction)
[![BIM](https://img.shields.io/badge/topic-bim-795548)](https://github.com/topics/bim)
[![IoT](https://img.shields.io/badge/topic-iot-607D8B)](https://github.com/topics/iot)
[![GIS](https://img.shields.io/badge/topic-gis-4CAF50)](https://github.com/topics/gis)
[![Observability](https://img.shields.io/badge/topic-observability-E91E63)](https://github.com/topics/observability)

[English](#features) | [中文](#功能特性)

</div>

---

## 项目简介

Construction AI Agents 是面向建筑行业的多智能体协作平台，基于 LLM（大语言模型）与领域规则引擎，实现**施工安全审核**、**法规合规校验**和**现场实时监控**三大核心场景的自动化。

平台采用 **A2A（Agent-to-Agent）** 协议实现智能体间编排调度，并通过 **MCP（Model Context Protocol）** 层对外暴露标准化工具与资源接口。覆盖从方案审查、法规执行到基于 IoT 的实时工地监控与告警的完整流水线。

## 功能特性

- **3 大专业智能体** — 安全审核智能体（结构分析、荷载计算、风险评估）、合规校验智能体（消防 / 抗震 / 节能 / 绿色建筑专项核查）、现场监控智能体（IoT 传感器接入、GIS 监控、BIM/IFC 解析）
- **A2A 协议** — 基于 HTTP + JSON-RPC 的智能体间通信，支持 Agent Card 发现与多租户隔离
- **MCP 工具层** — 通过 Model Context Protocol 暴露标准化工具（分析、校验）、资源（法规库、案例库）和提示词模板
- **编排引擎** — 基于 DAG 的工作流多智能体协调，支持事件总线与系统动作
- **法规引擎** — 内置 5+ 部国标（GB50009、GB50011、GB50016 等），结论绑定法规版本，支持 RAG 案例检索
- **IoT 与 BIM 集成** — MQTT 传感器接入、InfluxDB 时序存储、IFC/BIM 模型解析、GIS 风险热力图
- **实时告警** — 基于阈值的告警引擎（带去重），支持钉钉 / 企业微信通知渠道，自动生成日报
- **Streamlit 仪表盘** — 交互式 Web UI，包含安全审核、合规审查、现场监控、GIS 查看器、智能体管理等页面，支持移动端
- **可观测性** — OpenTelemetry 链路追踪 + Prometheus 指标监控 + 结构化 JSON 日志，配套 Grafana 仪表盘
- **企业级安全** — JWT 鉴权、RBAC（5 种角色）、令牌桶限流、审计日志、租户隔离
- **云原生部署** — Docker Compose 本地开发，Helm Chart + Terraform 部署到 Kubernetes（阿里云 ACK）

## 系统架构

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Streamlit UI    │    │  WebSocket       │    │  外部客户端       │
│  （仪表盘）        │    │  （实时事件）      │    │                  │
└────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌────────────────────────────────────────────────────────────────────┐
│                     FastAPI 网关（API 层）                           │
│  REST 端点 │ JWT/RBAC 鉴权 │ 令牌桶限流 │ 审计日志                    │
└────────┬───────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────────────┐
│                      编排协调器（Orchestrator）                       │
│  工作流引擎 │ 事件总线 │ 系统动作 │ 协作时间线                         │
└────────┬──────────────┬──────────────┬─────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  安全审核     │ │  合规校验     │ │  现场监控     │
│  智能体       │ │  智能体       │ │  智能体       │
│              │ │              │ │              │
│ · 结构分析   │ │  · 消防      │ │  · IoT/MQTT  │
│ · 荷载计算   │ │  · 抗震      │ │  · BIM/IFC   │
│ · 风险评估   │ │  · 节能      │ │  · GIS 热力图 │
│ · 案例 RAG   │ │  · 绿色建筑   │ │  · 阈值告警   │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │
       ▼                ▼                ▼
┌────────────────────────────────────────────────────────────────────┐
│                        基础设施层                                    │
│  PostgreSQL │ Redis │ InfluxDB │ ChromaDB │ Celery Workers           │
└────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────────────┐
│              A2A 协议（端口 9101）│ MCP 服务（端口 9201）              │
└────────────────────────────────────────────────────────────────────┘
```

## 快速开始

### 前置要求

- Python 3.11+
- pip
- Docker & Docker Compose（用于基础设施服务）

### 安装

```bash
# 克隆仓库
git clone <your-repo-url>.git
cd construction-ai-agents

# 安装核心依赖
pip install -r requirements.txt

# 按需安装可选依赖组
pip install -e ".[dev]"           # 开发工具（pytest、ruff）
pip install -e ".[langchain]"     # LangChain 集成
pip install -e ".[vector]"        # ChromaDB 向量存储
pip install -e ".[frontend]"      # Streamlit 前端
pip install -e ".[geo]"           # GIS（geopandas、shapely）
pip install -e ".[tsdb]"          # InfluxDB 时序数据库
pip install -e ".[observability]" # OpenTelemetry + Prometheus
pip install -e ".[mqtt]"          # MQTT 边缘网关
pip install -e ".[bim]"           # IFC/BIM 解析
pip install -e ".[security]"      # 国密 SM2
```

### 配置

复制示例环境文件并填入实际凭据：

```bash
cp .env.example .env
# 编辑 .env，填入以下配置：
#   LLM_API_KEY, LLM_BASE_URL, LLM_DEFAULT_MODEL
#   DATABASE_URL, REDIS_URL
#   CELERY_BROKER_URL, CELERY_RESULT_BACKEND
#   TSDB_URL, TSDB_TOKEN, TSDB_ORG, TSDB_BUCKET
```

### 启动基础设施

```bash
# 通过 Docker Compose 启动 PostgreSQL、Redis、InfluxDB
docker compose up -d postgres redis influxdb
```

### 启动服务

```bash
# 启动 API 服务
export PYTHONPATH=.
uvicorn api.main:app --host 0.0.0.0 --port 8000

# 启动 Celery Worker（异步任务）
python scripts/start_worker.py --queues default,alerts

# 启动 MCP 服务
python scripts/start_mcp_server.py   # MCP 服务，端口 9201

# 启动 Streamlit 仪表盘
streamlit run streamlit_app/app.py --server.port 8501

# 初始化智能体实例
python scripts/init_agents.py

# 填充测试数据（可选）
python scripts/seed_test_data.py
```

### Docker Compose 一键启动

```bash
# 启动全部服务（API + Worker + Streamlit + A2A + MCP + 基础设施）
docker compose up -d

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f api
```

### API 快速验证

```bash
# 存活探针
curl -s http://127.0.0.1:8000/api/v1/health/healthz | jq

# 就绪探针（DB + Redis + Celery + EventBus）
curl -s http://127.0.0.1:8000/api/v1/health/readyz | jq

# 列出支持的智能体
curl -s -H "Authorization: Bearer dev-tnt_demo-admin" \
     http://127.0.0.1:8000/api/v1/agents/supported | jq

# OpenAPI 文档
# 访问 http://127.0.0.1:8000/docs
```

## 智能体能力

| 智能体 | 功能描述 | 核心规范 / 集成 |
|--------|----------|----------------|
| 安全审核智能体 | 结构分析、荷载计算、风险评估、案例 RAG 检索 | GB50009（荷载规范）、GB50011（抗震规范） |
| 合规校验智能体 | 消防 / 抗震 / 节能 / 绿色建筑法规执行，结论绑定法规版本 | GB50016（防火规范）、GB50011（抗震规范）、节能与绿建标准 |
| 现场监控智能体 | IoT 传感器接入（MQTT）、BIM/IFC 解析、GIS 风险热力图、阈值告警、日报生成 | MQTT、InfluxDB、IFCOpenShell、GeoPandas |

## API 端点

| 端点 | 方法 | 鉴权 | 说明 |
|------|------|------|------|
| `/api/v1/health/healthz` | GET | 否 | 存活探针 |
| `/api/v1/health/readyz` | GET | 否 | 就绪探针（DB / Redis / Celery / EventBus） |
| `/api/v1/agents` | GET | 是 | 列出当前租户可用智能体 |
| `/api/v1/agents/supported` | GET | 是 | 列出支持的智能体白名单 |
| `/api/v1/agents/{name}/card` | GET | 是 | Agent Card（A2A 发现） |
| `/api/v1/agents/{name}/invoke` | POST | 是 | 通过 HTTP 调用智能体 |
| `/api/v1/tasks/{task_id}` | GET/DELETE | 是 | 查询 / 取消异步任务 |
| `/api/v1/reports` | GET | 是 | 报告列表（分页） |
| `/api/v1/reports/{report_id}` | GET | 是 | 报告详情 |
| `/api/v1/reports/{report_id}/download` | GET | 是 | 下载报告（Markdown） |
| `/api/v1/orchestrator/workflows` | GET | 是 | 列出所有工作流 |
| `/api/v1/orchestrator/workflows/{name}/trigger` | POST | 是 | 触发工作流 |
| `/api/v1/orchestrator/runs/{run_id}` | GET | 是 | 工作流执行状态 |
| `/api/v1/orchestrator/timeline` | GET | 是 | 协作时间线 |
| `/api/v1/ws/events` | WS | 否 | 实时事件订阅 |
| `/api/v1/a2a/...` | 多种 | 否 | A2A REST + JSON-RPC |
| `/api/v1/mcp/...` | 多种 | 否 | MCP 资源 / 工具 / 提示词 |

## 项目结构

```
construction-ai-agents/
├── agents/                          # 业务智能体
│   ├── base_agent.py                # 智能体基类（span、生命周期、handle）
│   ├── safety_audit_agent/          # 安全审核智能体
│   │   ├── calculators/             # 结构分析器、荷载计算器
│   │   ├── knowledge_base/          # 案例检索（RAG）
│   │   ├── parsers/                 # 规范 / 图纸解析器
│   │   └── prompts.py              # LLM 提示词模板
│   ├── compliance_agent/            # 合规校验智能体
│   │   ├── regulation_engine/       # 法规索引与查询引擎
│   │   ├── checkers/                # 消防 / 抗震 / 节能 / 绿色核查器
│   │   ├── validators/              # 跨字段校验器
│   │   └── outputs/                 # 违规仓储
│   └── site_monitor_agent/          # 现场监控智能体
│       ├── iot_integration/         # MQTT 传感器管理、时序写入
│       ├── bim_integration/         # IFC/BIM 解析
│       ├── gis_monitoring/          # 风险热力图（GeoPandas）
│       ├── alert_engine/            # 阈值管理、告警仓储
│       └── outputs/                 # 仪表盘数据、趋势分析、报告签章
├── api/                             # FastAPI 应用
│   ├── main.py                      # 应用工厂 + 生命周期
│   ├── routers/                     # HTTP 路由定义
│   ├── schemas/                     # Pydantic 请求 / 响应模型
│   └── dependencies/                # 智能体管理器、依赖注入
├── core/                            # 平台核心
│   ├── a2a/                         # A2A 协议（Agent Card、JSON-RPC）
│   ├── mcp/                         # MCP 服务（工具、资源、提示词）
│   ├── orchestrator/                # 工作流引擎、事件总线、系统动作
│   ├── llm/                         # LLM 适配器（配置、提示词管理、Token 追踪）
│   ├── cache/                       # Redis 缓存层 + 装饰器
│   ├── security/                    # RBAC、JWT 鉴权、限流、审计日志
│   ├── observability/               # OTel 链路追踪、Prometheus 指标、结构化日志
│   ├── events/                      # 事件总线（进程内 / RabbitMQ 适配器）
│   ├── storage/                     # 存储抽象
│   ├── rules/                       # 规则引擎基类
│   ├── langchain/                   # LangChain 集成
│   ├── vector_store/                # ChromaDB 向量存储
│   ├── gis/                         # GIS 工具集
│   └── timeseries/                  # InfluxDB 时序工具
├── models/                          # 数据模型
│   ├── domain/                      # 领域模型（项目、方案、巡检、违规、告警）
│   ├── database/                    # SQLAlchemy ORM + Alembic 迁移
│   └── vector/                      # 向量嵌入模型
├── services/                        # 外部服务集成
│   ├── notification_channels/       # 钉钉、企业微信通知渠道
│   └── reportlab_assets/            # PDF 报告生成资源
├── config/                          # 配置文件
│   ├── agent_configs.yaml           # 智能体业务参数
│   ├── a2a_config.yaml              # A2A 协议配置
│   └── environments/                # 环境覆盖（dev / staging / prod）
├── streamlit_app/                   # Streamlit Web 仪表盘
│   ├── app.py                       # 主入口
│   ├── pages/                       # 多页面：安全审核、合规、监控、GIS、仪表盘
│   ├── components/                  # 可复用 UI 组件（图表、地图、告警展示）
│   └── utils/                       # API 客户端、WebSocket 客户端、状态管理
├── tests/                           # 测试套件
│   ├── unit/                        # 单元测试
│   ├── integration/                 # 集成测试
│   ├── e2e/                         # 端到端测试
│   ├── safety_audit_agent/          # 智能体专项测试
│   ├── compliance_agent/
│   ├── site_monitor_agent/
│   └── orchestrator/
├── scripts/                         # 运维脚本
│   ├── start_worker.py              # Celery Worker 启动器
│   ├── start_mcp_server.py          # MCP 服务启动器
│   ├── init_agents.py               # 智能体初始化
│   ├── seed_test_data.py            # 测试数据填充
│   └── warm_cache.py                # Redis 缓存预热
├── deployment/                      # 部署资源
│   ├── docker/                      # Dockerfile（api、worker、streamlit、a2a、mcp）
│   ├── helm/caai/                   # K8s Helm Chart
│   ├── kubernetes/                  # Kustomize 资源（旧版）
│   └── terraform/                   # Terraform IaC（阿里云 ACK）
├── evaluation/                      # 评估基准
├── tools/                           # 验证与扫描脚本
├── data/                            # 静态数据（法规库、测试夹具）
├── docker-compose.yml               # 本地基础设施 + 服务编排
├── pyproject.toml                   # 项目元数据与依赖声明
├── requirements.txt                 # 锁定依赖
└── alembic.ini                      # 数据库迁移配置
```

## 工作原理

### 1. 智能体调用
用户或外部系统通过 REST API（`/api/v1/agents/{name}/invoke`）触发智能体。请求经 JWT / 开发令牌鉴权、参数校验后，由 `AgentManager` 分发到目标智能体。

### 2. 安全审核
安全审核智能体解析施工方案与规范文本，执行结构分析（依据 GB50009 进行荷载计算），从向量库（ChromaDB RAG）检索相似案例，并调用 LLM 生成风险评估报告。

### 3. 合规校验
合规校验智能体从法规引擎加载规则，执行消防 / 抗震 / 节能 / 绿色建筑专项核查，输出绑定法规版本的违规报告。每条结论均引用所依据的精确法规版本。

### 4. 现场监控
现场监控智能体通过 MQTT 采集 IoT 传感器数据并写入 InfluxDB 时序库，解析 BIM/IFC 模型，生成 GIS 风险热力图，触发基于阈值的告警（带去重）。告警经钉钉 / 企业微信通知渠道分发。

### 5. 多智能体编排
编排协调器通过 DAG 工作流引擎协调跨智能体协作（如"监控告警 → 安全审核"或"合规失败 → 复核审查"），基于事件总线与系统动作实现自动化串联。

### 6. 报告生成
各智能体生成经数字签名的 Markdown 报告（HMAC-SHA256 或国密 SM2），报告可存储、版本化，并通过 API 下载。

## 技术栈

| 层级 | 技术选型 |
|------|----------|
| 编程语言 | Python 3.11+ |
| Web 框架 | FastAPI + Uvicorn |
| 前端 | Streamlit（多页面应用） |
| LLM | OpenAI 兼容接口（httpx 直连）+ LangChain |
| 数据库 | PostgreSQL 16（SQLAlchemy 2.0 + Alembic） |
| 缓存 | Redis 7 |
| 时序数据库 | InfluxDB 2.7 |
| 向量存储 | ChromaDB |
| 任务队列 | Celery 5.4 |
| 智能体协议 | A2A（HTTP + JSON-RPC）+ MCP |
| GIS | GeoPandas + Shapely |
| BIM | IFCOpenShell |
| IoT | Paho MQTT |
| 可观测性 | OpenTelemetry + Prometheus + Grafana |
| 安全 | JWT（python-jose）+ RBAC + 令牌桶限流 + 审计日志 |
| 加密 | GmSSL（SM2）/ HMAC-SHA256 降级 |
| 部署 | Docker Compose / Helm / Terraform（阿里云 ACK） |
| CI/CD | GitHub Actions（lint + test + 安全扫描 + 镜像构建 + cosign 签名） |

## 部署

### Docker Compose（本地 / 开发环境）

```bash
docker compose up -d
# 服务：API(:8000)、Worker、Streamlit(:8501)、A2A(:9101)、MCP(:9201)
# 基础设施：PostgreSQL(:5432)、Redis(:6379)、InfluxDB(:8086)
```

### Kubernetes（生产环境）

```bash
# 构建并推送镜像
make build && make push

# 部署到 staging
make deploy-staging

# 部署到生产
make deploy-prod

# 回滚
make rollback
```

## 测试

```bash
# 运行全部测试
pytest tests/

# 仅运行单元测试
pytest tests/unit/

# 运行集成测试
pytest tests/integration/

# 带覆盖率
pytest tests/ --cov=agents --cov=core --cov=api

# 智能体专项自检脚本
python tests/safety_audit_agent/test_agent.py
python tests/compliance_agent/test_agent.py
python tests/site_monitor_agent/test_agent.py
```

## 贡献指南

欢迎贡献！以下方向尤其需要帮助：

- 扩展法规覆盖面（更多国标及地方修订）
- 提升 BIM/IFC 解析精度
- 增加国际建筑规范支持（IBC、Eurocode）
- Streamlit 仪表盘的 UI/UX 优化
- 大规模 IoT 数据接入的性能优化

## 许可证

本项目为专有软件 — 详见 [LICENSE](LICENSE) 文件。

## 致谢

- API 层基于 [FastAPI](https://fastapi.tiangolo.com/) 构建
- LLM 编排采用 [LangChain](https://python.langchain.com/)
- 交互式仪表盘使用 [Streamlit](https://streamlit.io/)
- CAD/BIM 解析依赖 [ezdxf](https://github.com/mozman/ezdxf) 和 [IFCOpenShell](https://ifcopenshell.org/)
- 灵感来源于中国建筑行业安全与合规流程自动化的迫切需求

## 免责声明

本平台旨在**辅助**专业人员，而非取代。所有自动化结果 — 安全评估、违规判定、监控告警 — 均应由具备资质的工程师和监管人员审核验证后方可用于施工或监管决策。法规规则基于公开发布的中国国家标准（GB），但可能不涵盖所有地方修订或项目特殊要求。
