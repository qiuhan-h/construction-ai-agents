# 阶段七 7b：外部接口联调计划

> 项目：智建云审 construction-ai-agents
> 前置：7a 生产硬化已完成（配置收口 + fail-fast + secrets + operations + 安全加固 + 迁移）
> 配套：做什么见 [release_plan_stage7.md](release_plan_stage7.md) · 怎么填见 [deployment_runbook.md](deployment_runbook.md)
> 目标：8 类外部通道全部拿到真实凭据并完成单点冒烟，每个通道至少 1 条真实成功记录

## 当前阶段状态（2026-09-08）

| 验证维度 | 状态 | 说明 |
|---|---|---|
| 本地降级验证 | ✅ 9/9 PASS | 所有通道无凭据下降级到 mock 模式，不崩溃 |
| 真实联调 | ⏳ 待凭据 | .env 中所有外部通道凭据为空，待用户提供 |
| 全量回归 | ✅ 14/14 通过 | verify_all.py + pytest 100% |

**降级验证产出**：`tools/smoke/smoke_7b_degradation.py` — 9 通道降级冒烟脚本
**真实联调模板**：`tools/smoke/smoke_7b_real.py` — 凭据到位后直接运行
**真实联调操作步骤**：见下方各通道章节 + `deployment_runbook.md` §3

---

## 0. 联调顺序与依赖关系

```
第一波（审核周期最长，最先提交申请，与 7a 并行）
  ├─ 7b-6 短信（签名+模板审核 1-3 工作日）
  ├─ 7b-4 钉钉（企业内部应用审核 + 回调域名备案）
  └─ 7b-5 企微（自建应用 + 可信域名校验）

第二波（拿到凭据即可联调，无审核等待）
  ├─ 7b-1 LLM（商用 Key 即时生效）
  ├─ 7b-2 PostgreSQL + Redis（运维部署即可）
  ├─ 7b-3 InfluxDB（初始化即可）
  └─ 7b-8 MQTT/IoT（broker 部署即可）

第三波（依赖 BIM 管理员授权）
  └─ 7b-7 BIM/APS（app 创建 + 项目授权）
```

| 波次 | 通道 | 审核等待 | 联调前提 | 预计联调耗时 |
|---|---|---|---|---|
| 第一波 | 7b-6 短信 | 1-3 工作日 | 签名+模板审核通过 | 0.5 人日 |
| 第一波 | 7b-4 钉钉 | 1-3 工作日 | 应用审核上架 | 1 人日 |
| 第一波 | 7b-5 企微 | 1-3 工作日 | 可信域名校验 | 0.5 人日 |
| 第二波 | 7b-1 LLM | 无 | 商用 Key 获取 | 0.5 人日 |
| 第二波 | 7b-2 DB+Redis | 无 | 实例部署 | 0.5 人日 |
| 第二波 | 7b-3 InfluxDB | 无 | 实例部署+初始化 | 0.5 人日 |
| 第二波 | 7b-8 MQTT | 无 | broker 部署 | 0.5 人日 |
| 第三波 | 7b-7 BIM | 无（需管理员授权） | app 创建+项目授权 | 1 人日 |

**关键路径**：第一波 3 个通道是外部审核等待项，须在 7a 首日并行提交申请。

---

## 1. 7b-1 LLM 商用 Key 联调

**代码位置**：[core/llm/injector.py](file:///d:/Trae%20woek解压盘/workspace-full/zhijian2/智建2/construction-ai-agents/core/llm/injector.py) LLMInjector 单例
**申请步骤**：见 [runbook §3.1](deployment_runbook.md#31-llm-商用-key任选一家)
**.env 变量**：LLM_PROVIDER / LLM_API_KEY / LLM_BASE_URL / LLM_DEFAULT_MODEL

### 联调步骤

1. 在 .env 填写真实 LLM 配置（LLM_PROVIDER=openai，非 mock）
2. 运行验证脚本：

```bash
# 验证 LLM 配置非占位
python tools/verify/verify_prod_config.py

# 冒烟测试：三条链路真实返回
python -c "
from core.llm.injector import get_injector
from config import get_settings
s = get_settings()
print(f'provider={s.llm_provider}, model={s.llm_default_model}')
llm = get_injector().get_llm()
print(f'llm type: {type(llm).__name__}')
# 简单 prompt 测试
resp = llm.invoke('请回复：联调成功')
print(f'response: {str(resp)[:200]}')
"
```

3. 触发完整安全审核链路（安全/合规/监控三条 chain）

### 验收标准

- [ ] `LLM_PROVIDER != mock`（settings 加载验证）
- [ ] `llm.invoke()` 返回非空字符串（真实模型响应）
- [ ] 三条 chain（safety_chain / compliance_chain / monitoring_chain）真实返回
- [ ] UsageRecord 表有 token 用量记录（多租户计费对账依据）
- [ ] 日志无"降级 mock 模式"关键字

### 降级策略

LLM_API_KEY 为空或网络错 → LLMInjector 自动降级 FakeListLLM + warning 日志（不阻塞启动，但生产 readyz 应报降级）

---

## 2. 7b-2 PostgreSQL + Redis 联调

**代码位置**：[core/storage/sqlalchemy_repos.py](file:///d:/Trae%20woek解压盘/workspace-full/zhijian2/智建2/construction-ai-agents/core/storage/sqlalchemy_repos.py) + config/settings.py
**申请步骤**：见 [runbook §1](deployment_runbook.md#1-中间件准备运维)
**.env 变量**：DATABASE_URL / REDIS_URL / CELERY_BROKER_URL / CELERY_RESULT_BACKEND

### 联调步骤

```bash
# 1. 部署中间件
docker compose up -d postgres redis

# 2. 数据库迁移
docker compose exec api alembic upgrade head

# 3. 验证连接
python -c "
from core.storage.sqlalchemy_repos import get_session_scope
from models.database import TenantTable
with get_session_scope() as session:
    count = session.query(TenantTable).count()
    print(f'PostgreSQL 连接 OK，tenants 表记录数: {count}')

import redis
r = redis.from_url('redis://redis:6379/0')
r.set('caai:ping', 'pong')
print(f'Redis 连接 OK: {r.get(\"caai:ping\")}')
"
```

### 验收标准

- [ ] `alembic upgrade head` 一条命令建表成功（含 0001 + 0002 审计日志表）
- [ ] API + worker 连接 PostgreSQL 成功（日志无 connection refused）
- [ ] Redis 连接成功，`celery inspect ping` 返回 pong
- [ ] 配额计数走 Redis（多租户 429 可复现）
- [ ] readyz 返回 200（非 503 降级）

### 降级策略

DATABASE_URL 为占位 → 回退 SQLite + warning；REDIS_URL 为占位 → 内存缓存（生产必须真实实例）

---

## 3. 7b-3 InfluxDB 2.x 联调

**代码位置**：[core/timeseries/client.py](file:///d:/Trae%20woek解压盘/workspace-full/zhijian2/智建2/construction-ai-agents/core/timeseries/client.py) L164 InfluxDBWriter
**申请步骤**：见 [runbook §3.2](deployment_runbook.md#32-influxdb-初始化)
**.env 变量**：TSDB_URL / TSDB_TOKEN / TSDB_ORG / TSDB_BUCKET

### 联调步骤

```bash
# 1. 部署 InfluxDB 并初始化
docker compose up -d influxdb
# UI :8086 → 设置 org=construction, bucket=sensor_data_prod, 生成 token

# 2. 验证写入
python -c "
from core.timeseries.client import InfluxDBWriter
from config import get_settings
s = get_settings()
writer = InfluxDBWriter(
    url=s.tsdb_url, token=s.tsdb_token.get_secret_value(),
    org=s.tsdb_org, bucket=s.tsdb_bucket,
)
writer.write_point(
    measurement='sensor_test',
    tags={'device': 'smoke-test', 'tenant': 'tnt_demo'},
    fields={'temperature': 25.5, 'humidity': 60.0},
)
print('InfluxDB 写入 OK')

# 3. 验证 readyz 时序库健康
import httpx
resp = httpx.get('http://localhost:8000/api/v1/health/readyz')
print(f'readyz: {resp.json()}')
"
```

### 验收标准

- [ ] InfluxDBWriter 写入成功（无异常）
- [ ] `/api/v1/health/readyz` 时序库组件状态为 ready（非降级）
- [ ] 传感器数据可通过 InfluxDB UI 查询到
- [ ] MQTT 消息进入告警链路时，时序数据有对应记录

### 降级策略

TSDB_URL 为占位 → InfluxDBWriter 降级 NoOp（写入静默丢弃 + warning）；传感器功能不阻塞

---

## 4. 7b-4 钉钉联调（群通知 + ISV 应用）

**代码位置**：
- 群通知：[services/notification_channels/dingtalk_real_channel.py](file:///d:/Trae%20woek解压盘/workspace-full/zhijian2/智建2/construction-ai-agents/services/notification_channels/dingtalk_real_channel.py)
- ISV 应用：[services/embedded_apps/dingtalk_app.py](file:///d:/Trae%20woek解压盘/workspace-full/zhijian2/智建2/construction-ai-agents/services/embedded_apps/dingtalk_app.py)
**申请步骤**：见 [runbook §3.3 + §3.5](deployment_runbook.md#33-钉钉机器人群通知)
**.env 变量**：DINGTALK_WEBHOOK / DINGTALK_SECRET（群机器人）+ DINGTALK_CORP_ID / DINGTALK_APP_KEY / DINGTALK_APP_SECRET / DINGTALK_AGENT_ID（ISV 应用）

### 联调步骤（群通知）

```bash
python -c "
from services.notification_channels.dingtalk_real_channel import DingTalkRealChannel
ch = DingTalkRealChannel()
result = ch.send(
    title='7b 联调测试',
    content='钉钉群通知联调成功 🎉',
)
print(f'钉钉群通知: {result}')
"
```

### 联调步骤（ISV 应用免登）

```bash
python -c "
from services.embedded_apps.dingtalk_app import DingTalkApp
from config import get_settings
s = get_settings()
app = DingTalkApp(
    app_key=s.dingtalk_app_key,
    app_secret=s.dingtalk_app_secret.get_secret_value(),
    agent_id=s.dingtalk_agent_id,
    corp_id=s.dingtalk_corp_id,
)
# 生成 OAuth state
state = app.generate_state(session_id='smoke-test')
print(f'state 生成 OK: {state}')

# 模拟 OAuth 回调（需真实 code，从钉钉授权跳转获取）
# result = app.oauth_callback(code='<REAL_CODE>', state=state, timestamp=time.time())
# print(f'userid: {result}')
"
```

### 验收标准

- [ ] 群通知真实送达（钉钉群收到消息）
- [ ] state + timestamp 防重放生效（重复 state → 403）
- [ ] OAuth 免登跳转成功（移动端容器内打开工作台不要求重复登录）
- [ ] 工作通知推送送达（push_notification 返回成功）

### 降级策略

dingtalk-sdk 缺失 → httpx 直连 OAuth API；httpx 缺失 → mock 返回固定 userid。群通知凭据空 → 降级 mock + warning

---

## 5. 7b-5 企业微信联调

**代码位置**：
- 群通知：[services/notification_channels/wecom_real_channel.py](file:///d:/Trae%20woek解压盘/workspace-full/zhijian2/智建2/construction-ai-agents/services/notification_channels/wecom_real_channel.py)
- 自建应用：[services/embedded_apps/wecom_app.py](file:///d:/Trae%20woek解压盘/workspace-full/zhijian2/智建2/construction-ai-agents/services/embedded_apps/wecom_app.py)
**申请步骤**：见 [runbook §3.4 + §3.5](deployment_runbook.md#34-企业微信机器人群通知)
**.env 变量**：WECOM_WEBHOOK（群机器人）+ WECOM_CORP_ID / WECOM_SECRET / WECOM_AGENT_ID（自建应用）

### 联调步骤

```bash
# 群通知
python -c "
from services.notification_channels.wecom_real_channel import WeComRealChannel
ch = WeComRealChannel()
result = ch.send(title='7b 联调', content='企微群通知联调成功')
print(f'企微群通知: {result}')
"

# 自建应用（wechatpy 真实 client）
python -c "
from services.embedded_apps.wecom_app import WeComApp
from config import get_settings
s = get_settings()
app = WeComApp(
    corp_id=s.wecom_corp_id,
    secret=s.wecom_secret.get_secret_value(),
    agent_id=s.wecom_agent_id,
)
print(f'access_token: {app.access_token[:20]}...')
"
```

### 验收标准

- [ ] wechatpy 真实 client 初始化成功（access_token 非空）
- [ ] 群通知真实送达（企微群收到消息）
- [ ] 工作通知送达（应用消息推送到指定用户）
- [ ] 无 wechatpy 时降级仍可（群通知 Webhook 不依赖 wechatpy）

### 降级策略

wechatpy 缺失 → 群通知仍走 Webhook（不依赖 SDK）；自建应用功能降级 mock

---

## 6. 7b-6 短信联调（阿里云 + 腾讯云双通道）

**代码位置**：
- 阿里云：[services/notification_channels/sms_aliyun_channel.py](file:///d:/Trae%20woek解压盘/workspace-full/zhijian2/智建2/construction-ai-agents/services/notification_channels/sms_aliyun_channel.py)
- 腾讯云：[services/notification_channels/sms_tencent_channel.py](file:///d:/Trae%20woek解压盘/workspace-full/zhijian2/智建2/construction-ai-agents/services/notification_channels/sms_tencent_channel.py)
**申请步骤**：见 [runbook §3.6](deployment_runbook.md#36-短信签名与模板审核-1-3-工作日最先提交)
**.env 变量**：ALIYUN_SMS_* / TENCENT_SMS_*（§2.4）

### 联调步骤

```bash
# 阿里云短信
python -c "
from services.notification_channels.sms_aliyun_channel import AliyunSMSChannel
ch = AliyunSMSChannel()
result = ch.send(
    phone='13800138000',  # 真实手机号
    template_code='SMS_123456789',  # 审核通过的模板
    template_params={'content': '告警联调测试'},
)
print(f'阿里云短信: {result}')
"

# 腾讯云短信
python -c "
from services.notification_channels.sms_tencent_channel import TencentSMSChannel
ch = TencentSMSChannel()
result = ch.send(phone='13800138000', template_id='1234567', params=['告警联调测试'])
print(f'腾讯云短信: {result}')
"
```

### 验收标准

- [ ] 阿里云：签名 base64 真实发送成功（无 InvalidSignature）
- [ ] 腾讯云：原始 body 同源签名真实发送成功
- [ ] 手机真实收到短信
- [ ] 双通道任一可用即视为通过（已具备主备）

### 降级策略

access_key 为空 → 降级 mock + warning；网络错 → 降级 mock（不抛 NotifierError）

---

## 7. 7b-7 BIM (Autodesk APS) 联调

> BIM 通道是最复杂的联调项：涉及 Autodesk 开发者后台应用创建、ACC/BIM 360 项目授权、OAuth 2.0 client_credentials、Model Derivative API。
> **关键原则**：APS 授权复杂但不阻塞上线 —— 无授权时 `/bim/*` 自动降级 mock，其他功能正常。

### 7.1 代码架构与调用链

```
API 端点（bim_router.py）
  ├─ GET /api/v1/bim/projects/{project_id}/tree   → _fetch_project_tree()
  ├─ GET /api/v1/bim/elements/{element_id}         → _fetch_element()
  └─ GET /api/v1/bim/progress/{project_id}         → _compute_progress()
                                                            ↓
BIM 连接器工厂（bim_router.py:_get_bim_connector）
  ├─ 优先 BIMRealConnector（APS 真实，凭据从 .env 读取）
  └─ 降级 BIMConnector（4c mock，httpx 缺失走纯 mock）
                                                            ↓
BIMRealConnector（bim_real_connector.py）
  ├─ _ensure_token()       OAuth 2.0 client_credentials → access_token
  ├─ get_project_tree()    GET /data/v1/projects/{pid}/topFolders
  ├─ get_element()         GET /modelderivative/v2/designdata/{urn}/metadata/{guid}
  ├─ list_elements()       GET /data/v1/projects/{pid}/items
  └─ download_ifc()        GET /data/v1/projects/{pid}/items/{item_id}/tip → 二次拉 storage
                                                            ↓
ProgressTracker（progress_tracker.py）
  └─ compute(plan, actual) → 偏差检测 → 告警分级（critical/warning/info）
```

**文件清单**：
- [bim_real_connector.py](file:///d:/Trae%20woek解压盘/workspace-full/zhijian2/智建2/construction-ai-agents/agents/site_monitor_agent/bim_integration/bim_real_connector.py) — APS 真实客户端（OAuth + 4 个业务方法）
- [bim_connector.py](file:///d:/Trae%20woek解压盘/workspace-full/zhijian2/智建2/construction-ai-agents/agents/site_monitor_agent/bim_integration/bim_connector.py) — 4c mock 客户端（兼容保留）
- [progress_tracker.py](file:///d:/Trae%20woek解压盘/workspace-full/zhijian2/智建2/construction-ai-agents/agents/site_monitor_agent/bim_integration/progress_tracker.py) — 进度对比 + 偏差告警
- [ifc_real_parser.py](file:///d:/Trae%20woek解压盘/workspace-full/zhijian2/智建2/construction-ai-agents/agents/site_monitor_agent/bim_integration/ifc_real_parser.py) — ifcopenshell 真实解析器
- [bim_router.py](file:///d:/Trae%20woek解压盘/workspace-full/zhijian2/智建2/construction-ai-agents/api/routers/bim_router.py) — 3 个 API 端点
- [bim_schemas.py](file:///d:/Trae%20woek解压盘/workspace-full/zhijian2/智建2/construction-ai-agents/api/schemas/bim_schemas.py) — 响应 Schema

### 7.2 申请步骤（详细）

**Step 1: 创建 APS 应用**
1. 访问 [aps.autodesk.com](https://aps.autodesk.com) → 注册/登录 Autodesk 账号
2. 进入 My Apps → Create App
3. 应用名称：`construction-ai-agents`（或项目实际名称）
4. 选择 Service API：勾选 **BIM 360 API** + **Data Management API** + **Model Derivative API**
5. 回调 URL：生产环境填 `https://<your-domain>/api/v1/bim/callback`（client_credentials 模式非必需，但建议填）
6. 记录 **Client ID** + **Client Secret** → 填入 `.env` 的 `APS_CLIENT_ID` / `APS_CLIENT_SECRET`

**Step 2: 获取 Hub ID + Project ID**
1. 登录 [BIM 360 / ACC](https://construct.autodesk.com)
2. 进入目标项目 → 账号管理 → 记录 **Hub ID**（URL 中 `construction.autodesk.com/hubs/<hub_id>/...`）
3. 进入具体项目 → 记录 **Project ID**（URL 中 `projects/<project_id>/...`）
4. 填入 `.env` 的 `APS_HUB_ID` / `APS_PROJECT_ID`

**Step 3: 应用授权（关键）**
1. 在 BIM 360 账号中 → Account Admin → Apps → 添加刚创建的 APS 应用
2. 将应用加入目标项目 → 授予项目成员权限（至少 Viewer）
3. 等待权限生效（通常 5-30 分钟）

**参考文档**：
- [APS OAuth 2.0 指南](https://aps.autodesk.com/en/docs/oauth/v2/developers_guide/overview/)
- [Data v2 API](https://aps.autodesk.com/en/docs/data/v2/reference/http/projects-GET/)
- [Model Derivative v2](https://aps.autodesk.com/en/docs/model-derivative/v2)

### 7.3 .env 变量

| 变量 | 必填 | 填写说明 |
|---|---|---|
| `APS_CLIENT_ID` | 用 BIM 必填 | Autodesk 开发者后台创建应用获取 |
| `APS_CLIENT_SECRET` | 用 BIM 必填 | 应用 Secret |
| `APS_HUB_ID` | 用 BIM 必填 | BIM 360 Hub ID（URL 中可查） |
| `APS_PROJECT_ID` | 用 BIM 必填 | BIM 360 Project ID（URL 中可查） |

### 7.4 联调步骤（分阶段验证）

#### 阶段 A: 凭据加载验证

```bash
python -c "
from config import get_settings
s = get_settings()
print(f'aps_client_id: {repr(s.aps_client_id[:8])}...' if s.aps_client_id else 'aps_client_id: EMPTY')
print(f'aps_hub_id: {repr(s.aps_hub_id)}')
print(f'aps_project_id: {repr(s.aps_project_id)}')
print(f'secret set: {bool(s.aps_client_secret.get_secret_value())}')
"
```

**预期**：4 项全部非空、非占位。

#### 阶段 B: OAuth Token 获取验证

```bash
python -c "
import asyncio
from agents.site_monitor_agent.bim_integration.bim_real_connector import BIMRealConnector
from config import get_settings

s = get_settings()
conn = BIMRealConnector(
    client_id=s.aps_client_id,
    client_secret=s.aps_client_secret.get_secret_value(),
    hub_id=s.aps_hub_id,
    project_id=s.aps_project_id,
)
print(f'has_credentials: {conn._has_credentials()}')
print(f'is_mock_mode: {conn.is_mock_mode()}')

# OAuth token 获取
token = asyncio.run(conn._ensure_token())
if token:
    print(f'OAuth token 获取成功: {token[:20]}... (expires_in={conn._token_expires_in}s)')
else:
    print('OAuth token 获取失败 → 检查凭据 / 应用授权')
"
```

**预期**：
- `has_credentials: True`
- `is_mock_mode: False`
- `OAuth token 获取成功`（非空，expires_in ≈ 3600s）

**失败排查**：
- `has_credentials: False` → .env 未填写或仍为占位
- `OAuth token 获取失败` → 检查应用是否已授权到项目（Step 3）
- HTTP 400 `invalid_client` → Client ID/Secret 错误
- HTTP 403 `insufficient_scope` → 应用未勾选 BIM 360 API

#### 阶段 C: 项目树获取验证

```bash
python -c "
import asyncio, json
from agents.site_monitor_agent.bim_integration.bim_real_connector import BIMRealConnector
from config import get_settings

s = get_settings()
conn = BIMRealConnector(
    client_id=s.aps_client_id,
    client_secret=s.aps_client_secret.get_secret_value(),
    hub_id=s.aps_hub_id,
    project_id=s.aps_project_id,
)

# 项目树
tree = asyncio.run(conn.get_project_tree(s.aps_project_id))
print(f'项目树根节点数: {len(tree)}')
print(f'第一个节点: {json.dumps(tree[0], ensure_ascii=False)[:200]}' if tree else '空树')
"
```

**预期**：非空树，节点含 `id` / `type` / `name`（非 `{project_id}-bldg-1` 形式的 mock id）

#### 阶段 D: 构件详情 + 列表验证

```bash
python -c "
import asyncio, json
from agents.site_monitor_agent.bim_integration.bim_real_connector import BIMRealConnector
from config import get_settings

s = get_settings()
conn = BIMRealConnector(
    client_id=s.aps_client_id,
    client_secret=s.aps_client_secret.get_secret_value(),
    hub_id=s.aps_hub_id,
    project_id=s.aps_project_id,
)

# 列出构件
elements = asyncio.run(conn.list_elements(s.aps_project_id, limit=5))
print(f'构件列表: {len(elements)} 条')
if elements:
    first = elements[0]
    print(f'第一个构件: id={first[\"element_id\"]}, name={first[\"name\"]}, type={first[\"type\"]}')

    # 获取单个构件详情（需要 urn:guid 形式）
    elem = asyncio.run(conn.get_element(first['element_id']))
    print(f'构件详情: {json.dumps(elem, ensure_ascii=False)[:300]}')
"
```

#### 阶段 E: API 端点联调

```bash
# 1. 项目树端点
curl -s http://localhost:8000/api/v1/bim/projects/<APS_PROJECT_ID>/tree \
  -H "Authorization: Bearer dev-tnt_test-user1" | python -m json.tool

# 2. 构件详情端点
curl -s http://localhost:8000/api/v1/bim/elements/<element_id> \
  -H "Authorization: Bearer dev-tnt_test-user1" | python -m json.tool

# 3. 进度对比端点
curl -s http://localhost:8000/api/v1/bim/progress/<APS_PROJECT_ID> \
  -H "Authorization: Bearer dev-tnt_test-user1" | python -m json.tool
```

**预期响应**：
```json
{
  "code": "0",
  "message": "project tree (3 roots)",
  "data": [
    {"id": "urn:adsk...real-id", "type": "folder", "name": " architectural", "children": []}
  ]
}
```

#### 阶段 F: IFC 文件下载 + 真实解析验证

```bash
python -c "
import asyncio
from agents.site_monitor_agent.bim_integration.bim_real_connector import BIMRealConnector
from agents.site_monitor_agent.bim_integration.ifc_real_parser import IFCRealParser
from config import get_settings

s = get_settings()
conn = BIMRealConnector(
    client_id=s.aps_client_id,
    client_secret=s.aps_client_secret.get_secret_value(),
    hub_id=s.aps_hub_id,
    project_id=s.aps_project_id,
)

# 下载 IFC（需真实 item_id）
content = asyncio.run(conn.download_ifc(
    project_id=s.aps_project_id,
    item_id='<REAL_ITEM_ID>',
    out_path='/tmp/test.ifc',
))
print(f'IFC 下载: {len(content)} bytes')

if content:
    # 真实解析
    parser = IFCRealParser()
    result = parser.parse('/tmp/test.ifc')
    print(f'IFC 解析: {len(result.get(\"elements\", []))} 个构件')
"
```

#### 阶段 G: 进度对比 + 偏差告警验证

```bash
python -c "
from agents.site_monitor_agent.bim_integration import ProgressTracker

# 真实计划 vs 实际进度
plan = [
    {'element_id': 'urn:beam-1', 'name': '主梁A', 'pct': 80.0},
    {'element_id': 'urn:beam-2', 'name': '次梁B', 'pct': 50.0},
]
actual = [
    {'element_id': 'urn:beam-1', 'name': '主梁A', 'pct': 60.0},   # -20% 滞后
    {'element_id': 'urn:beam-2', 'name': '次梁B', 'pct': 75.0},   # +25% 超前
]

tracker = ProgressTracker(deviation_threshold=10.0)
items = tracker.compute(plan, actual)
for it in items:
    status = '滞后' if it.deviation < -10 else ('超前' if it.deviation > 10 else '正常')
    print(f'  {it.name}: 计划{it.plan_pct}% 实际{it.actual_pct}% 偏差{it.deviation}% [{status}]')

alerts = tracker.deviation_alerts(items, tenant_id='tnt_prod', project_id='proj_prod')
print(f'告警数: {len(alerts)}（应 2 条：1 critical + 1 warning）')
"
```

### 7.5 验收标准（逐项打勾）

| # | 验收项 | 验证方法 | 预期 | 状态 |
|---|---|---|---|---|
| 1 | 凭据加载 | 阶段 A 脚本 | 4 项非空非占位 | ⬜ |
| 2 | OAuth token | 阶段 B 脚本 | token 非空，expires_in≈3600 | ⬜ |
| 3 | 项目树 | 阶段 C 脚本 | 非空，节点 id 非 `{pid}-bldg-N` 形式 | ⬜ |
| 4 | 构件列表 | 阶段 D 脚本 | ≥1 条真实构件 | ⬜ |
| 5 | 构件详情 | 阶段 D 脚本 | element_id 匹配，properties 非空 | ⬜ |
| 6 | API /tree | 阶段 E curl | 200 + tree 非空 + code=0 | ⬜ |
| 7 | API /elements | 阶段 E curl | 200 + element_id 匹配 | ⬜ |
| 8 | API /progress | 阶段 E curl | 200 + delayed/ahead 计数 | ⬜ |
| 9 | IFC 下载 | 阶段 F 脚本 | bytes > 0 | ⬜ |
| 10 | IFC 解析 | 阶段 F 脚本 | elements ≥ 1 | ⬜ |
| 11 | 进度偏差 | 阶段 G 脚本 | 2 条告警（1 critical + 1 warning） | ⬜ |
| 12 | 降级验证 | 清空 .env APS_* 后重启 | source=mock，不崩溃 | ⬜ |

### 7.6 降级策略（已内置）

| 场景 | 降级行为 | 代码位置 |
|---|---|---|
| client_id/secret 缺失或占位 | `_has_credentials()=False` → 所有方法返回 mock 数据 | bim_real_connector.py L140-151 |
| OAuth token 获取失败（网络/凭据错） | `_ensure_token()` 返回 None → 方法降级 mock + warning 日志 | bim_real_connector.py L182-224 |
| 项目树 API 非 2xx | 返回 `_mock_project_tree()` + warning | bim_real_connector.py L252-254 |
| 构件详情 API 非 2xx | 返回 `_mock_element()` + warning | bim_real_connector.py L304-306 |
| IFC 下载失败 | 返回空 bytes（`b""`） | bim_real_connector.py L380-438 |
| ifcopenshell 未安装 | IFCRealParser 降级文本抽取 | ifc_real_parser.py |
| BIMRealConnector 构造失败 | bim_router.py 降级 BIMConnector（4c mock） | bim_router.py L173-191 |

### 7.7 常见问题排查

| 症状 | 原因 | 解决 |
|---|---|---|
| `OAuth token 获取失败` | 应用未授权到项目 | BIM 360 → Account Admin → Apps → 添加应用 |
| HTTP 403 `insufficient_scope` | 应用未勾选 BIM 360 API | APS My Apps → 编辑应用 → 勾选 |
| `has_credentials: False` | .env 未填写或仍为占位 | 检查 APS_* 4 项是否非空非 `xxx` |
| 项目树返回 mock id（`{pid}-bldg-1`） | 降级到 mock | 检查 OAuth token + 项目授权 |
| `download_ifc` 返回空 bytes | item_id 错误或无权限 | 检查构件 item_id + Viewer 权限 |
| IFC 解析 elements 为空 | ifcopenshell 未安装 | `pip install ifcopenshell` |

### 7.8 联调耗时估算

| 阶段 | 耗时 | 备注 |
|---|---|---|
| A 凭据加载 | 5 分钟 | 纯配置验证 |
| B OAuth token | 15 分钟 | 含应用授权等待 |
| C 项目树 | 10 分钟 | 验证 API 权限 |
| D 构件详情+列表 | 15 分钟 | 需要真实 element_id |
| E API 端点 | 20 分钟 | 含 curl 验证 |
| F IFC 下载+解析 | 30 分钟 | 需 ifcopenshell 安装 |
| G 进度对比 | 15 分钟 | 验证告警分级 |
| **合计** | **约 2 小时** | 不含应用授权等待 |

### 7.9 与其他通道的依赖关系

- **7b-7 依赖**：无（BIM 是独立通道）
- **7b-7 被依赖**：
  - `/bim/progress` 端点的偏差告警可触发 **7b-4 钉钉通知** / **7b-5 企微通知** / **7b-6 短信**
  - IFC 解析结果可进入 **7b-1 LLM** 链路（安全审核 chain 消费）
- **降级原则**：BIM 降级 mock 不阻塞其他通道，但 readyz 应报 BIM 降级状态

---

## 8. 7b-8 MQTT/IoT 联调

**代码位置**：[agents/site_monitor_agent/iot_integration/mqtt_connector.py](file:///d:/Trae%20woek解压盘/workspace-full/zhijian2/智建2/construction-ai-agents/agents/site_monitor_agent/iot_integration/mqtt_connector.py)
**申请步骤**：见 [runbook §3.8](deployment_runbook.md#38-mqtt-broker)
**.env 变量**：MQTT_BROKER / MQTT_PORT

### 联调步骤

```bash
# 1. 部署 EMQX 或 Mosquitto
docker compose up -d mqtt-broker  # 或外部 EMQX

# 2. 模拟设备上报
python -c "
import paho.mqtt.client as mqtt
import json, time
c = mqtt.Client()
c.connect('localhost', 1883)
c.publish(
    'construct/tnt_demo/sensors/dev001/telemetry',
    json.dumps({'temperature': 28.5, 'humidity': 65.0}),
)
print('MQTT 消息已发送')
time.sleep(1)
"

# 3. 验证告警链路
python -c "
from agents.site_monitor_agent.iot_integration.mqtt_connector import MQTTConnector
conn = MQTTConnector(broker='localhost', port=1883, tenant_id='tnt_demo')
print(f'mock_mode: {conn._mock_mode}')
"
```

### 验收标准

- [ ] connect_async 真实订阅成功（_mock_mode=False）
- [ ] 设备消息进入告警链路（InfluxDB 有写入 + 围栏越界产生告警）
- [ ] paho-mqtt 缺失时降级 asyncio.Queue（不崩溃）

### 降级策略

paho-mqtt 缺失 → mock 模式（asyncio.Queue 注入）；broker 不可达 → connect_async 非阻塞，不崩溃

---

## 9. 联调总检查清单

### 9.1 每个通道至少 1 条真实成功记录

| # | 通道 | 真实成功记录证据 | 负责人 | 状态 |
|---|---|---|---|---|
| 1 | LLM | llm.invoke() 返回真实模型响应 | 开发 | ⬜ |
| 2 | PostgreSQL + Redis | alembic upgrade + celery ping | 运维 | ⬜ |
| 3 | InfluxDB | writer.write_point() 无异常 | 运维 | ⬜ |
| 4 | 钉钉 | 群通知送达 + OAuth 免登成功 | 开发+企业管理员 | ⬜ |
| 5 | 企微 | 群通知送达 + access_token 获取 | 开发+企业管理员 | ⬜ |
| 6 | 短信 | 手机真实收到（阿里/腾讯任一） | 运维 | ⬜ |
| 7 | BIM | /bim/* 返回 source=aps | BIM 管理员 | ⬜ |
| 8 | MQTT | 设备消息进入告警链路 | 运维+现场 | ⬜ |

### 9.2 readyz 全绿验证

```bash
curl http://localhost:8000/api/v1/health/readyz
# 期望：status=ready，subscribers 全部非降级
```

### 9.3 日志无降级关键字

```bash
# 上线后检查日志不应出现（除 BIM 明确保留的降级）：
grep -E "降级|mock 模式|NoOp|降级 mock" data/logs/*.log
```

---

## 10. 时间排期建议

```
Day 1（与 7a 并行）：
  ├─ 提交短信签名/模板审核（7b-6）
  ├─ 提交钉钉企业内部应用审核（7b-4）
  ├─ 提交企微自建应用+可信域名校验（7b-5）
  ├─ 部署 PostgreSQL + Redis（7b-2）
  ├─ 部署 InfluxDB + 初始化（7b-3）
  └─ 部署 MQTT Broker（7b-8）

Day 2-3（审核等待期）：
  ├─ LLM 商用 Key 联调（7b-1）
  ├─ PostgreSQL + Redis 联调（7b-2）
  ├─ InfluxDB 联调（7b-3）
  └─ MQTT/IoT 联调（7b-8）

Day 4-5（审核通过后）：
  ├─ 短信联调（7b-6）
  ├─ 钉钉联调（7b-4）
  ├─ 企微联调（7b-5）
  └─ BIM/APS 联调（7b-7，需 BIM 管理员授权）

Day 6：总检查清单逐项打勾 → 7b 完成
```

---

## 11. 风险与对策

| 风险 | 对策 |
|---|---|
| 短信/钉钉/企微审核不通过 | 预留二次提审时间；短信备双通道（阿里+腾讯） |
| APS 授权复杂耗时 | 无授权时 BIM 自动降级 mock，不阻塞上线 |
| LLM 商用成本失控 | 配额 429 + UsageRecord 日预算告警 |
| MQTT broker 现场网络不稳定 | connect_async 非阻塞 + 重连退避 |
| 通道间依赖隐藏（如告警依赖通知+时序） | readyz 汇总子组件状态，503 时定位 |

---

*本文档聚焦"联调怎么验、验收什么"；"凭据怎么申请、平台点哪里"见 [deployment_runbook.md](deployment_runbook.md)。*
