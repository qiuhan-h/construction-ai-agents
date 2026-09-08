# 阶段 5e · 质量保障（E2E / 压测 / 灰度 / SLA）

> 版本：2026-09-03
> 周期：1.5 周（7.5 工作日）
> 前置：5d CI/CD + 部署就绪
> 后置：6 试运行

## 1. 目标

在客户进来之前，把「系统能跑」升级为「系统能扛」：
- 端到端业务流程 100% 自动化覆盖；
- 性能基线建立，瓶颈明确；
- 故障可恢复可演练；
- SLA 合同指标可量化可监控。

## 2. 关键交付物

### 2.1 端到端测试

- `tests/e2e/test_business_scenarios.py`（已有雏形）— 扩展 8 个核心场景：
  1. 提交审查 → 编排调度 → 安全审核 → 合规校验 → 报告生成 → 签字
  2. IoT 告警 → 事件总线 → 编排触发安全审查
  3. 法规更新 → 旧审查报告版本快照可查
  4. 多租户数据隔离（租户 A 看不到租户 B 数据）
  5. 智能体故障 → 编排降级到 mock
  6. 通知渠道切换：邮件 → 钉钉 → 企微 → SMS
  7. 报告 PDF 导出与电子签章验证
  8. Streamlit 6 页面 + API 集成（Playwright）
- `tests/e2e/conftest.py` — staging 集群 fixtures + 凭据管理
- `tests/e2e/run_all.sh` — 端到端套件启动器

### 2.2 性能压测

- `tests/load/locustfile.py` — 5 个用户画像：
  - 监理员提交审查（20 RPS）
  - 操作员查询报告（100 RPS）
  - 监控 IoT 数据写入（500 RPS）
  - GIS 围栏越界（10 RPS 重计算）
  - 法规检索（50 RPS）
- 工具：locust 2.x + Prometheus 抓取
- 报告：`docs/performance/baseline_v1.md` — P50 / P95 / P99 / 错误率 / 资源占用
- 优化迭代：识别瓶颈 → 优化 → 重测，循环 2-3 轮

### 2.3 混沌测试

- `tests/chaos/` 剧本（用 `chaos-mesh` 或 `chaosblade`）：
  - **API Pod 随机 kill** — 验证 HPA + readiness probe + 无中断
  - **PostgreSQL 主备切换** — 验证 5b.3 仓储自动重连
  - **Redis 网络分区 30s** — 验证缓存降级到 DB
  - **InfluxDB 不可达** — 验证数据 pipeline 缓冲 + 告警
  - **事件总线堆积 10w 条** — 验证背压 + 丢弃策略
  - **通知渠道超时 5s** — 验证 mock 兜底
- 演练记录表 `docs/chaos/drills.log`

### 2.4 灰度发布

- `deployment/helm/caai/templates/canary.yaml` — 基于 header 的流量切分
- `scripts/canary_promote.sh` — 10% → 30% → 50% → 100% 自动晋升（按错误率与延迟指标）
- `scripts/canary_rollback.sh` — 错误率 > 1% 自动回滚
- Grafana 灰度面板：双版本对比（错误率 / 延迟 / 流量）

### 2.5 SLA 合同与监控

- `docs/sla/sla_v1.md` — 与商务共拟：
  - 可用性 ≥ 99.9%（月）
  - API P95 ≤ 800ms
  - 报告生成 ≤ 90s
  - 通知到达率 ≥ 99.5%
  - 故障响应：P0 ≤ 15min / P1 ≤ 1h / P2 ≤ 4h
  - 故障恢复：P0 ≤ 4h / P1 ≤ 8h
- `core/observability/sli_calculator.py` — 实时计算 SLI（服务等级指标）
- `core/observability/slo_alerting.py` — SLO 告警（错误预算耗尽 50% / 80% / 100%）
- 客户可见的状态页：`https://status.caai.example.com`（基于 `upptime` / `statusfy`）

## 3. 任务拆解（按天）

| 日 | 任务 | 产出 |
| --- | --- | --- |
| D1 | E2E 8 个场景编写 + staging 集群 fixtures | `tests/e2e/` 8 场景 |
| D2 | E2E CI 接入 + 报告徽章 | CI 集成 + README 徽章 |
| D3 | locust 压测脚本 + 5 画像 | `tests/load/locustfile.py` |
| D4 | 压测执行 + 基线报告 | `docs/performance/baseline_v1.md` |
| D5 | 瓶颈优化 1 轮（按基线报告） | 优化 PR + 重测 |
| D6 | 混沌测试 6 个剧本 | `tests/chaos/` + 演练记录 |
| D7 | 灰度发布 + 监控告警 | Helm canary + SLO 告警 |
| D7.5 | SLA 文档 + 状态页 + 文档收口 | `docs/sla/sla_v1.md` + `docs/work_log_stage5e.txt` |

## 4. 验收标准

| 维度 | 标准 | 验证方式 |
| --- | --- | --- |
| E2E | 8 场景全过，CI 必跑 | GitHub Actions |
| 性能 | P95 ≤ 800ms（业务接口） / 1000 RPS 不掉队 | locust 报告 |
| 故障 | 6 混沌剧本全过，无 P0 | `tests/chaos/` 执行记录 |
| 灰度 | 10% 流量下错误率 < 0.5% 自动晋升 | 演练 1 次 |
| SLA | 4 个 SLI 指标可见 + 告警可触发 | Prometheus + AlertManager |
| 状态页 | 5 个核心端点 P95 实时展示 | 状态页截图 |

## 5. 风险与回退

| 风险 | 概率 | 影响 | 缓解 / 回退 |
| --- | --- | --- | --- |
| E2E 套件不稳 | 中 | 中 | 退化为 staging 重试 + 截图存档 |
| 压测把 staging 打挂 | 中 | 中 | 限速 + 独立 namespace + 监控 |
| 混沌测试误伤 | 低 | 高 | 演练窗口凌晨 2-5 点 + 业务可暂停 |
| 灰度切流量有损 | 中 | 高 | 灰度 5min 后必须升 50%，否则回滚 |
| SLA 指标定得过严 | 中 | 中 | 内部试跑 2 周后再签客户合同 |
| 状态页被客户质疑 | 低 | 中 | 公开计算方式 + 历史记录透明 |

## 6. 阶段出口

- E2E 8 场景 100% PASS（CI 必跑）；
- 性能基线报告 + 1 轮优化后达标；
- 6 混沌剧本演练通过；
- 灰度发布 / 回滚全自动；
- SLA 4 指标实时监控 + 状态页对外可见。
