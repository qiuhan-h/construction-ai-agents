# 阶段七规划：上线前全流程（硬化 → 联调 → 预发 → 上线）

> 项目：智建云审 construction-ai-agents
> 起点：阶段六已全部验收（verify 13/13 exit 0，pytest 144 passed/0 failed）
> 配套文档：
> - 部署操作（占位怎么填、第三方平台点哪里）→ **[deployment_runbook.md](deployment_runbook.md)**
> - 阶段六交付总结 → [交付文件6阶段_stage6.md](交付文件6阶段_stage6.md)
> 原则：每个子阶段开工前报方案 → 批准后执行；不擅自扩大范围

---

## 0. 现状基线与上线差距

| 维度 | 已具备 | 距上线差距 |
|---|---|---|
| 业务功能 | 三智能体 + A2A/MCP + 编排 + 通知 + GIS/BIM + 多租户 + 移动端 | 功能闭环完成 |
| 测试 | 146 收集 / 144 通过 / 3 跳过；163 项阶段六断言 | 缺生产环境 E2E 与压测 |
| 部署骨架 | 6 Dockerfile、docker-compose（8 服务）、K8s 清单、监控配置、Terraform | `operations.md`、`secrets.yaml` 仍是注释占位 |
| 配置 | 占位统一为"需要补充实际链接"，缺凭据自动降级 mock | `.env.example` 有 8 类缺口；生产密钥需 fail-fast |
| 外部集成 | 钉钉/企微/短信/LLM/BIM(APS)/MQTT/InfluxDB 代码通道全部就绪 | 全部未开通真实凭据、未做真实联调 |

---

## 1. 子阶段 7a — 生产硬化（开发主导，约 3-5 人日）

> 目标：代码与配置达到"填入真实凭据即可安全运行"，不依赖任何 mock 兜底生产。

| 编号 | 任务 | 内容要点 | 验收 |
|---|---|---|---|
| 7a-1 | 配置项收口 | 补齐 `.env.example` 8 类缺口：APS_BIM_*（4）、MQTT_*（broker/port）、钉钉 ISV 应用级（APP_KEY/APP_SECRET/AGENT_ID/CORP_ID）、企微（CORP_ID/SECRET/AGENT_ID）、VECTOR_STORE_BACKEND、GEOFENCE_HISTORY_BACKEND、API_BASE_URL/API_AUTH_TOKEN（Streamlit 上游）、ENABLE_METRICS | `.env.example` 全量变量与 `os.environ.get` 调用点一一对应；新增 settings 字段或显式 env 读取 |
| 7a-2 | 生产 fail-fast | `APP_ENV=prod` 时：JWT 密钥仍为占位 → 直接启动失败（当前仅 warning）；DATABASE_URL/REDIS_URL/LLM_API_KEY 为空 → 拒绝启动或明确进入 mock 声明日志 | 新增 `tools/verify/verify_prod_config.py`：prod 模式下占位配置 exit 1 |
| 7a-3 | secrets.yaml 实装 | K8s `secrets.yaml` 从注释模板改为 Sealed Secrets/外部注入说明；明文密钥不落库 | 清单可 `kubectl apply --dry-run`；文档说明 CI 渲染方式 |
| 7a-4 | operations.md 实写 | 把占位注释扩写为真实运维手册（架构/构建/部署/观测/备份/排障） | 与 runbook 交叉引用无死链 |
| 7a-5 | 安全加固 | CORS 白名单可配置；生产关闭 /docs 或加鉴权选项；审计日志（tenant_id + action + actor）落库；依赖 CVE 扫描（pip-audit） | 新增测试：prod 配置下 docs 开关、CORS 拒绝外域；pip-audit 无 HIGH+ |
| 7a-6 | 数据迁移 | Alembic 迁移脚本核对（tenants/billing/alerts 表）；首启 `alembic upgrade head` 自动化 | 全新库一条命令建表成功；ORM/内存双后端在 CI 均跑通 |

## 2. 子阶段 7b — 外部接口开通与联调（开发+运维+第三方审核，约 5-10 工作日，含审核等待）

> 目标：8 类外部通道全部拿到真实凭据并完成单点冒烟。**具体操作步骤全部在 [deployment_runbook.md](deployment_runbook.md)。**

| 编号 | 通道 | 需申请/配置 | 负责方 | 联调验收 |
|---|---|---|---|---|
| 7b-1 | LLM | 商用 Key（通义/DeepSeek/智谱任选或 vLLM 自建）+ 模型名 + base_url | 开发/采购 | chains 三条链路真实返回；`LLM_PROVIDER != mock`；token 用量入 UsageRecord |
| 7b-2 | PostgreSQL + Redis | 生产实例、账号、库名、备份策略 | 运维 | API + worker 连接成功；配额计数走 Redis |
| 7b-3 | InfluxDB 2.x | org/bucket/token（读写权限） | 运维 | 传感器写入 + `/api/v1/health/readyz` 时序库健康 |
| 7b-4 | 钉钉 | 机器人 Webhook（通知）+ 企业内部应用/ISV（corp_id/app_key/app_secret/agent_id）+ 回调域名备案 | 开发+企业管理员 | 群通知真实送达；OAuth 免登跳转成功；state/timestamp 防重放生效 |
| 7b-5 | 企业微信 | 群机器人 Webhook + 自建应用（corpid/secret/agentid）+ 可信域名/回调 | 开发+企业管理员 | wechatpy 真实 client 初始化；工作通知送达；无 wechatpy 时降级仍可 |
| 7b-6 | 短信 | 阿里云或腾讯云：签名审核 + 模板审核 + AccessKey | 运维（审核 1-3 工作日） | 签名 base64（阿里）/原始 body 同源（腾讯）真实发送成功 |
| 7b-7 | BIM (Autodesk APS) | app client_id/secret + hub_id/project_id 授权 | BIM 管理员 | `/bim/*` 三端点 `source=aps`；失败自动降级 mock 仍可 |
| 7b-8 | MQTT/IoT | broker 地址/端口/鉴权（或 EMQX 自建） | 运维+现场 | connect_async 真实订阅；设备消息进入告警链路 |

**依赖关系**：7b-4/7b-5/7b-6 涉及平台审核，**第一天就提交申请**，与 7a 并行。

## 3. 子阶段 7c — 预发环境 Staging（约 3-5 人日）

| 编号 | 任务 | 验收 |
|---|---|---|
| 7c-1 | 全栈起环境 | docker-compose 8 服务全绿 或 K8s staging namespace 部署完成 | `/healthz` 200、`/readyz` 200（非降级 503） |
| 7c-2 | 数据初始化 | `alembic upgrade head` + 首批租户 seed（至少 2 租户验证隔离） | 两租户数据互不可见；配额 429 可复现 |
| 7c-3 | E2E 冒烟 | 三智能体端到端（安全审核→人工复核→PDF；合规校验；现场告警→通知）；A2A/MCP 互通；移动端 3 端点；钉钉/企微内嵌打开 | 新增 `tests/e2e/test_smoke_prod_like.py`（预发配置，不进 CI 阻断） |
| 7c-4 | 压测 | API 并发、worker 队列积压、配额限流、InfluxDB 写入吞吐 | 给出基线数据（QPS/RT/错误率）；无 event loop 阻塞告警 |
| 7c-5 | 安全测试 | 越权（跨租户 404/403）、JWT 伪造、SQL 注入 tenant 中间件、脱敏字段矩阵 | 权限用例全过；无 HIGH 漏洞 |
| 7c-6 | 观测验证 | Prometheus 采集、Grafana 仪表盘出图、OTel trace 串联 | 一次请求可在 trace 中看到 API→chain→LLM 全链路 |

## 4. 子阶段 7d — 生产上线 Go-Live（约 1-2 人日 + 观察期 1 周）

| 编号 | 任务 | 验收 |
|---|---|---|
| 7d-1 | 上线检查单 | Go/No-Go 清单逐项签字（见 runbook 附录）：配置、备份、监控、回滚、值班 | 清单 100% 勾选 |
| 7d-2 | 发布 | 滚动/蓝绿发布 5 个工作负载（api/worker/streamlit/a2a/mcp）；edge 镜像下发边缘设备 | 发布零中断或按窗口执行；版本号可追溯 |
| 7d-3 | 上线验证 | runbook"上线后验证清单"全部通过（真实凭据 ping 每个外部通道） | 每个通道至少 1 条真实成功记录 |
| 7d-4 | 回滚预案 | 镜像 tag 回退 + `alembic downgrade` 边界（只允许兼容迁移） | 演练过一次回滚 |
| 7d-5 | 观察期 | 7 天值班：错误率、LLM 成本/配额、通知送达率、告警误报 | SLA 达标；每日巡检报告 |

## 5. 子阶段 7e — 上线后（持续）

- pg_dump 定时备份 + 每月恢复演练；ChromaDB/向量库快照
- 密钥轮换流程（JWT、SMS AccessKey、APS secret）
- 租户计费对账（UsageRecord ↔ 账单）
- 边缘设备镜像 OTA 更新流程
- 占位项决策回炉：`core/gis/` core 层抽象是否立项（当前 agent 层可用，不阻塞上线）

---

## 6. 里程碑与建议排期

```
7a 生产硬化        ████░░░░░░  开发 3-5 人日
7b 接口开通联调     ██████░░░░  与 7a 并行启动（审核等待 5-10 工作日）
7c 预发环境        ░░░█████░░  依赖 7a+7b，3-5 人日
7d 上线            ░░░░░░░██░  1-2 人日 + 7 天观察
7e 上线后          ░░░░░░░░░█  持续
```

**关键路径**：短信/钉钉/企微审核（7b）是最长外部等待项，须最先发起。

## 7. 风险与对策

| 风险 | 对策 |
|---|---|
| LLM 商用成本失控 | 配额（已有 429）+ UsageRecord 日预算告警先于上线配置 |
| 平台审核不通过 | 预留二次提审时间；短信先备第二家（阿里/腾讯双通道已具备） |
| APS 授权复杂 | 无授权时 BIM 自动降级 mock，不阻塞其他功能上线 |
| 边缘设备环境差异 | edge 镜像提前在目标硬件实测（昨日清单任务 5） |
| mock 降级掩盖生产故障 | 生产 fail-fast（7a-2）+ readyz 区分降级状态 |

---

*本文档只回答"做什么、何时做、谁做、验收什么"；"具体怎么填、去哪申请"见 [deployment_runbook.md](deployment_runbook.md)。*
