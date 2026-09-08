# 部署上线操作手册（Runbook）

> 项目：智建云审 construction-ai-agents
> 用途：部署上线时**手动替换占位、开通与配置外部接口**的操作指引
> 配套：做什么/何时做见 [release_plan_stage7.md](release_plan_stage7.md)
> 约定：所有占位在代码中统一为字符串 `需要补充实际链接`；`.env` 不入库（.gitignore 已忽略）

---

## 0. 操作顺序总览

```
① 准备服务器与中间件 → ② 申请全部外部接口（审核最慢，最先做）
→ ③ 复制 .env.example 为 .env 逐项填写 → ④ 构建/启动
→ ⑤ 健康检查 → ⑥ 逐通道真实联调 → ⑦ 上线后验证清单
```

---

## 1. 中间件准备（运维）

| 组件 | 版本要求 | 部署要点 |
|---|---|---|
| PostgreSQL | 14+ | 建库 `construction_agents`、建账号；docker-compose 内服务名 `postgres` |
| Redis | 6+ | 建议 3 个 db：0 缓存 / 1 celery broker / 2 result |
| InfluxDB | 2.x | 初始化 org、bucket（如 `sensor_data_prod`）、生成读写 token |
| MQTT Broker | EMQX 5 / Mosquitto | 生产建议开账号密码或 TLS；记录 host/port（默认 1883） |
| （可选）ChromaDB | 最新 stable | 语义检索向量库；不接则走内存/降级 |

启动命令（compose 路线）：

```bash
cp .env.example .env     # 然后按下文逐项填写
docker compose up -d postgres redis influxdb
# 数据库表结构：
docker compose exec api alembic upgrade head
```

---

## 2. 占位替换总表（.env 逐项填写）

> 填写位置：项目根目录 `.env`（复制自 `.env.example`）。
> 标注 **[必填]** 的生产必须填写；**[可选]** 不填则自动降级 mock/NoOp。

### 2.1 应用与认证

| 变量 | 必填 | 填写说明 |
|---|---|---|
| `APP_ENV` | 必填 | `dev` / `staging` / `prod`；生产填 `prod`（触发 fail-fast 校验） |
| `API_HOST` | 必填 | 容器内填 `0.0.0.0` |
| `API_PORT` | 选填 | 默认 8000 |
| `LOG_LEVEL` | 选填 | 生产建议 `INFO` |
| `API_JWT_SECRET` | **必填** | 32 字节以上随机串。生成：`python -c "import secrets;print(secrets.token_urlsafe(48))"`。**禁止使用默认占位值，否则 prod 启动失败（7a-2）** |

### 2.2 数据存储

| 变量 | 必填 | 填写说明 |
|---|---|---|
| `DATABASE_URL` | **必填** | `postgresql+psycopg://<用户>:<密码>@<host>:5432/construction_agents`；compose 内 host 填 `postgres`。密码含 `@:/` 需 URL 编码（`@→%40` `:→%3A` `/→%2F`） |
| `REDIS_URL` | **必填** | `redis://[:<密码>@]<host>:6379/0`；compose 内 host 填 `redis` |
| `CELERY_BROKER_URL` | **必填** | 同上用 db `/1` |
| `CELERY_RESULT_BACKEND` | **必填** | 同上用 db `/2` |
| `TSDB_URL` | 有 IoT 必填 | `http://<host>:8086`（compose 内 `http://influxdb:8086`） |
| `TSDB_TOKEN` | 有 IoT 必填 | InfluxDB API Token（需读写目标 bucket 权限）；与初始化 admin token 一致 |
| `TSDB_ORG` | 有 IoT 必填 | 组织名，如 `construction` |
| `TSDB_BUCKET` | 有 IoT 必填 | 桶名，生产建议 `sensor_data_prod` |

### 2.3 LLM 大模型

| 变量 | 必填 | 填写说明 |
|---|---|---|
| `LLM_PROVIDER` | **必填** | `openai`（OpenAI 兼容协议，含通义/DeepSeek/智谱/vLLM/Ollama）；默认 `mock` 为假数据，**生产必须改** |
| `LLM_API_KEY` | **必填** | 各平台 Key（见 §3.1） |
| `LLM_BASE_URL` | **必填** | OpenAI 兼容基址（不含 `/chat/completions`），各平台地址见 §3.1 |
| `LLM_DEFAULT_MODEL` | **必填** | 模型名，如 `qwen-plus` / `deepseek-chat` / `glm-4-flash` |
| `LLM_TIMEOUT/MAX_RETRIES/TEMPERATURE/MAX_TOKENS` | 选填 | 默认 120s / 3 次 / 0.2 / 4096 |

### 2.4 通知渠道

| 变量 | 必填 | 填写说明 |
|---|---|---|
| `DINGTALK_WEBHOOK` | 用钉钉群通知必填 | 群机器人 Webhook（§3.3） |
| `DINGTALK_SECRET` | 选填 | 机器人加签密钥（SEC 开头），启用加签时填 |
| `WECOM_WEBHOOK` | 用企微群通知必填 | 企微群机器人 Webhook（§3.4） |
| `ALIYUN_SMS_ACCESS_KEY_ID/SECRET` | 用阿里短信必填 | RAM AccessKey（LTAI 开头 / 30 位） |
| `ALIYUN_SMS_SIGN_NAME` | 同上必填 | 控制台审核通过的签名 |
| `ALIYUN_SMS_TEMPLATE_CODE` | 同上必填 | 模板 ID（SMS_ 开头） |
| `ALIYUN_SMS_PHONE` | 同上必填 | 接收手机号（11 位） |
| `TENCENT_SMS_SECRET_ID/KEY` | 用腾讯短信必填 | AKID 开头 / 32 位 |
| `TENCENT_SMS_APP_ID/SIGN_NAME/TEMPLATE_ID/PHONE` | 同上必填 | 1400 开头 AppId / 签名 / 纯数字模板 / 手机号 |

### 2.5 内嵌应用（钉钉 ISV / 企微应用，移动端免登+工作通知）

> 以下变量为 7a-1 约定接入名（当前代码经 settings 属性读取，缺省降级 mock）。

| 变量 | 必填 | 填写说明 |
|---|---|---|
| `DINGTALK_CORP_ID` | 用钉钉免登必填 | 企业 CorpId（钉钉管理后台 → 企业信息） |
| `DINGTALK_APP_KEY` | 同上必填 | 应用 AppKey（钉钉开发者后台创建应用） |
| `DINGTALK_APP_SECRET` | 同上必填 | 应用 AppSecret |
| `DINGTALK_AGENT_ID` | 同上必填 | 应用 AgentId |
| `WECOM_CORP_ID` | 用企微免登必填 | 企业 CorpID（企微管理后台 → 我的企业） |
| `WECOM_SECRET` | 同上必填 | 自建应用 Secret |
| `WECOM_AGENT_ID` | 同上必填 | 自建应用 AgentId（数字） |

### 2.6 BIM / IoT / 其他

> 以下变量为 7a-1 约定接入名。

| 变量 | 必填 | 填写说明 |
|---|---|---|
| `APS_CLIENT_ID` | 用 BIM 必填 | Autodesk APS 应用 Client ID（§3.6） |
| `APS_CLIENT_SECRET` | 用 BIM 必填 | APS Client Secret |
| `APS_HUB_ID` | 用 BIM 必填 | APS Hub ID |
| `APS_PROJECT_ID` | 用 BIM 必填 | APS Project ID |
| `MQTT_BROKER` | 接 IoT 必填 | broker 主机/IP；当前默认 `localhost` |
| `MQTT_PORT` | 接 IoT 必填 | 默认 1883 |
| `VECTOR_STORE_BACKEND` | 选填 | `chroma` / `memory`；不填走内存降级 |
| `GEOFENCE_HISTORY_BACKEND` | 选填 | `sql` / `memory`；生产建议 `sql` |
| `API_BASE_URL` | Streamlit 必填 | Streamlit 访问 API 的地址，如 `http://api:8000` |
| `API_AUTH_TOKEN` | Streamlit 必填 | Streamlit 调 API 的服务 token |
| `ENABLE_OTEL` / `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_SERVICE_NAME` | 选填 | 链路追踪，不填降级 NoOp |
| `ENABLE_METRICS` | 选填 | `1` 开启 Prometheus 指标 |
| `SM2_PRIVATE_KEY_PATH` / `SM2_PUBLIC_KEY_PATH` / `SM2_KEY_PASSPHRASE` | 选填 | 国密签章证书路径；不填降级 HMAC-SHA256 |

---

## 3. 外部接口开通操作指引（第三方平台）

### 3.1 LLM 商用 Key（任选一家）

| 平台 | 开通路径 | base_url | 模型名示例 |
|---|---|---|---|
| 通义千问（阿里云百炼） | 阿里云控制台 → 百炼 → API-KEY 管理 → 创建 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| DeepSeek | platform.deepseek.com → API Keys → 创建 | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 智谱 AI | open.bigmodel.cn → 控制台 → API Keys | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| OpenAI | platform.openai.com → API keys | `https://api.openai.com/v1` | `gpt-4o-mini` |
| 自建 vLLM/Ollama | 部署后无需申请，内网地址 | `http://<内网IP>:8000/v1` | 部署的模型名 |

### 3.2 InfluxDB 初始化

1. 打开 InfluxDB UI（`:8086`）→ 首次访问设置用户名/密码/组织名（记为 org，如 `construction`
2. **Load Data → Buckets → Create Bucket**：建 `sensor_data_prod`
3. **Load Data → API Tokens → Generate Token → Read/Write**：勾选目标 bucket，复制 token 填入 `TSDB_TOKEN`

### 3.3 钉钉机器人（群通知）

1. 目标钉钉群 → 群设置 → 智能群助手 → 添加机器人 → **自定义（Webhook）**
2. 安全设置勾选"加签"→ 复制 SEC 开头密钥 → `DINGTALK_SECRET`
3. 创建完成复制 Webhook（含 access_token）→ `DINGTALK_WEBHOOK`

### 3.4 企业微信机器人（群通知）

1. 目标企微群 → 群设置 → 添加群机器人 → 新建
2. 复制 Webhook（含 key）→ `WECOM_WEBHOOK`

### 3.5 钉钉/企微内嵌应用（移动端免登 + 工作通知）

**钉钉企业内部应用：**
1. 钉钉开发者后台（open-dev.dingtalk.com）→ 应用开发 → 创建企业内部应用
2. 记录 **AppKey / AppSecret / AgentId / 企业 CorpId** → 填入 §2.5
3. 应用能力 → 登录与分享：配置回调域名（须 https、已备案）为部署后的访问域名
4. 发布应用 → 企业内管理员审批上架

**企业微信自建应用：**
1. 企微管理后台（work.weixin.qq.com）→ 应用管理 → 自建 → 创建应用
2. 记录 **CorpID（我的企业页）/ AgentId / Secret** → 填入 §2.5
3. 应用 → 网页授权及 JS-SDK：配置**可信域名**（https 域名，需上传校验文件）
4. 企业可信 IP：填写服务器出口 IP

> OAuth 防重放（state + timestamp）代码已内置，无需额外配置。

### 3.6 短信签名与模板（审核 1-3 工作日，**最先提交**）

**阿里云：** 控制台 → 短信服务 → 国内消息 → 签名管理（添加签名，填资质）→ 模板管理（添加模板，如"告警通知：${content}"）→ 审核通过后填 §2.4；AccessKey 在 RAM 控制台创建（建议子账号仅授短信权限）。

**腾讯云：** 控制台 → 短信 → 签名管理 → 正文模板管理 → 审核；密钥在访问管理（CAM）→ API 密钥。

### 3.7 Autodesk APS（BIM 数据）

1. aps.autodesk.com → 注册应用（Create App）→ 选 BIM 360 / ACC 相关 API
2. 获取 **Client ID / Client Secret**
3. 在 ACC/BIM 360 账号中把该应用加入项目，记录 **Hub ID / Project ID**（账号管理页 URL 中可查）
4. 填入 §2.6；未授权时 `/bim/*` 自动降级 mock，不阻塞其他功能

### 3.8 MQTT Broker

- 自建 EMQX：dashboard 建账号、记录 1883（TCP）/8883（TLS）端口 → `MQTT_BROKER/PORT`
- 现场设备按 `tenant/{租户}/device/{设备}/telemetry` 主题上报（主题规范按现场约定文档）

---

## 4. 部署启动

### 4.1 Docker Compose（单机/小规模）

```bash
docker compose build
docker compose up -d
docker compose ps          # 8 个服务应全部 Up
```

### 4.2 Kubernetes（生产推荐）

```bash
kubectl apply -f deployment/kubernetes/namespace.yaml
# 由 CI/Vault 渲染 secrets.yaml（严禁明文）后：
kubectl apply -f deployment/kubernetes/secrets.yaml
kubectl apply -f deployment/kubernetes/configmap.yaml
kubectl apply -f deployment/kubernetes/deployments/
kubectl apply -f deployment/kubernetes/services/
```

### 4.3 边缘端（工地现场）

```bash
docker build -f deployment/docker/Dockerfile.edge -t zhijian-edge .
# 运行时注入 EDGE_MODE=1 + .env（边缘配置：本地 Influx/MQTT 地址）
```

---

## 5. 上线后验证清单（逐项打勾）

| # | 验证项 | 命令/操作 | 预期 |
|---|---|---|---|
| 1 | 存活探针 | `GET /api/v1/health/healthz` | 200 |
| 2 | 就绪探针 | `GET /api/v1/health/readyz` | 200（若 503 说明有依赖在降级，按返回 dependencies 排查） |
| 3 | 版本横幅 | `GET /` | stage=6d，endpoints 列表含 bim/mobile/tenants |
| 4 | 数据库 | 跑一条租户查询 `/api/v1/tenants` | 真实 PostgreSQL 返回（非内存） |
| 5 | LLM | 触发一次安全审核链 | 真实模型返回；`LLM_PROVIDER != mock`；UsageRecord 有用量 |
| 6 | 钉钉通知 | 触发一条告警 | 钉钉群真实收到消息 |
| 7 | 企微通知 | 同上 | 企微群真实收到 |
| 8 | 短信 | 触发短信渠道 | 手机收到；签名验证通过（无 InvalidSignature） |
| 9 | 钉钉/企微免登 | 移动端容器内打开工作台 | OAuth 跳转成功、不要求重复登录 |
| 10 | BIM | `GET /api/v1/bim/progress/{id}` | `source=aps`（未授权时 source=mock 也算可接受降级） |
| 11 | IoT | 设备发一条 MQTT 消息 | InfluxDB 可查到写入；越界产生围栏告警 |
| 12 | 多租户隔离 | 用 A 租户 token 查 B 租户任务 | 404/403 |
| 13 | 配额 | 超额调用 | 429 + 结构化错误体 |
| 14 | 移动端 | 手机访问 `/mobile/dashboard` | 响应 < 5KB、布局正常 |
| 15 | 观测 | Grafana 看仪表盘 | QPS/RT/错误率有数据；trace 可串联 |

---

## 6. 回滚

```bash
# compose：回退到上一镜像 tag
docker compose down && IMAGE_TAG=<上一版本> docker compose up -d
# K8s：
kubectl rollout undo deployment/api -n caai
# 数据库迁移只允许向后兼容；如需回退先备份再 alembic downgrade -1
```

## 7. 注意事项

- `.env`、`secrets.yaml` 明文密钥**严禁提交 git**（.env 已忽略；secrets 走 Sealed Secrets/Vault）
- 生产 `APP_ENV=prod` 下 JWT 密钥为占位会**拒绝启动**（fail-fast）
- 任何通道未配置都会自动降级 mock/NoOp 并打 warning 日志——上线后**检查日志中不应再出现"降级/mock 模式"关键字**（除明确保留的 BIM 降级）
- 短信签名/模板、钉钉/企微应用审核有等待期，**部署前至少提前 3 个工作日提交申请**
