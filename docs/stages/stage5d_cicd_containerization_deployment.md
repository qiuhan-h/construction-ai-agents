# 阶段 5d · CI/CD + 容器化 + 部署

> 版本：2026-09-03
> 周期：1.5 周（7.5 工作日）
> 前置：5c 完成
> 后置：5e 质量保障

## 1. 目标

让"提交代码到代码可对外提供服务"全自动：本地 `git push` → CI 全跑 → 5 个服务镜像构建 → 部署到 staging / production Kubernetes 集群。`make deploy-staging` 一键可达。

## 2. 关键交付物

### 2.1 CI（GitHub Actions）

- `.github/workflows/ci.yml`（已存在）扩展：
  - lint（ruff / mypy / black）
  - 单元 + 集成测试（pytest，分片并行）
  - 安全扫描（`bandit` + `safety` + `trivy`）
  - 镜像构建（5 个服务，独立 tag，缓存层）
  - SBOM（`syft`）生成
- `.github/workflows/release.yml`：
  - 触发：`v*` tag 或 `main` 分支
  - 动作：构建 + 推送 + 数字签名（cosign）+ 部署到 staging
- `.github/workflows/rollback.yml`：
  - 手动触发，按镜像 tag 回滚
- `.github/dependabot.yml`：依赖自动更新

### 2.2 容器化（5 个服务镜像）

- `deployment/docker/Dockerfile.api`（已存在）— 多阶段构建，slim 基础镜像，非 root 运行，healthcheck 内置
- `deployment/docker/Dockerfile.a2a` / `Dockerfile.mcp` / `Dockerfile.streamlit` / `Dockerfile.worker` — 同样多阶段 + 最小层
- `deployment/docker/.dockerignore`（已存在）— 排除 `.git` / `__pycache__` / `.pytest_cache` / `data/` / `tests/`
- `deployment/docker/entrypoint.sh` — 启动前 5s 等待依赖 + Alembic 升级 + signal 转发
- 镜像命名：`ghcr.io/<org>/caai-{api|a2a|mcp|streamlit|worker}:<sha>-<short>`

### 2.3 K8s 部署（Helm Chart 收口）

- `deployment/helm/caai/`：
  - `Chart.yaml` / `values.yaml` / `values-staging.yaml` / `values-prod.yaml`
  - `templates/`：5 个 Deployment + 3 个 Service（API/A2A/MCP clusterIP，Streamlit LoadBalancer）+ 5 个 HPA + 5 个 PDB
  - `templates/ingress.yaml` — 域名 + TLS（cert-manager）
  - `templates/networkpolicy.yaml` — 命名空间隔离 + 出口白名单
  - `templates/serviceaccount.yaml` / `templates/secret.yaml` / `templates/configmap.yaml`
  - `templates/job-migrate.yaml` — Alembic 升级 Job
- `deployment/kubernetes/`（已存在）— 旧 Kustomize 资源并入 Helm 单一来源

### 2.4 基础设施即代码（Terraform）

- `deployment/terraform/main.tf`（已存在）扩展：
  - 阿里云 ACK 集群（生产）
  - RDS PostgreSQL（生产 HA）
  - Redis（生产 HA）
  - InfluxDB Cloud（云版）
  - OSS（报告 / IFC / BIM 存储）
  - SLB（负载均衡 + 证书）
  - 监控（ARMS Prometheus + SLS）
- `deployment/terraform/environments/staging.tfvars` / `prod.tfvars`
- 状态后端：Terraform Cloud 或 OSS Remote State

### 2.5 部署脚本与 Makefile

- `Makefile`（新增）：
  - `make build` / `make push` / `make deploy-staging` / `make deploy-prod` / `make rollback` / `make status` / `make logs` / `make shell`
- `scripts/deploy_helm.sh` — Helm 部署封装（带 dry-run 校验）
- `scripts/wait_rollout.sh` — 等待 Deployment ready，最长 5 分钟
- `scripts/healthcheck.sh` — 5 个服务全健康检查

## 3. 任务拆解（按天）

| 日 | 任务 | 产出 |
| --- | --- | --- |
| D1 | 5 个 Dockerfile 多阶段优化 + 镜像层缓存策略 | 镜像大小 < 500MB / 服务 |
| D2 | CI pipeline 全流水线（lint / test / security / build / sign） | `.github/workflows/ci.yml` |
| D3 | Release + Rollback workflow + 镜像签名 | `.github/workflows/release.yml` + `rollback.yml` |
| D4 | Helm Chart 5 服务 + Ingress + NetworkPolicy + HPA + PDB | `deployment/helm/caai/` 完整 |
| D5 | Terraform staging / prod 两套环境 | `deployment/terraform/` 完整 |
| D6 | Makefile + 部署脚本 + 健康检查 | `Makefile` + 3 个 scripts |
| D7 | 端到端：`make deploy-staging` → 5 服务全活 → 真实 HTTP 调用成功 | staging 集群落地 |
| D7.5 | 文档 + Stage 5d 验收 | `tools/scan_stage5d.py` / `verify_stage5d.py` / `docs/work_log_stage5d.txt` |

## 4. 验收标准

| 维度 | 标准 | 验证方式 |
| --- | --- | --- |
| CI | PR 触发后 ≤ 8 分钟全跑完 | GitHub Actions 计时 |
| 镜像 | 5 个服务镜像均 < 500MB，非 root 运行 | `docker images` + `docker inspect` |
| Helm | `helm install` + `helm upgrade` 幂等可重入 | dry-run + 重复部署 5 次 |
| 部署 | staging 集群 5 服务全活，5 健康检查全 200 | `kubectl get pods` + `healthcheck.sh` |
| 回滚 | 5 分钟内回滚到上一版本 | 演练 1 次 |
| 签名 | cosign 签名 + SBOM 完整 | `cosign verify` + `syft` |
| 安全 | bandit / safety / trivy 无 HIGH | CI 输出 |
| 配置 | 所有凭据走 Secret，无明文 | `grep -r "password" deployment/` |

## 5. 风险与回退

| 风险 | 概率 | 影响 | 缓解 / 回退 |
| --- | --- | --- | --- |
| CI 耗时过长 | 中 | 中 | 并行分片 + 缓存 + matrix；超时 8min 报警 |
| Helm 升级失败 | 中 | 高 | `helm rollback` 自动触发；保留 3 个历史 release |
| 镜像层失效 | 低 | 中 | `--cache-from` 显式 + 多阶段复制层 |
| TF 状态损坏 | 低 | 高 | OSS Remote State + 启用 state locking |
| 流量切换有损 | 中 | 高 | 灰度按租户（header `X-Tenant-Id`）路由，10% → 50% → 100% |
| 证书过期 | 低 | 高 | cert-manager 自动续期 + 监控告警 7 天前 |

## 6. 阶段出口

- staging 集群 5 服务可访问、5 健康检查 200；
- 完整 `make` 命令链：`make build && make push && make deploy-staging`；
- 回滚演练通过；
- 镜像签名 + SBOM 完整；
- `tools/verify_stage5d.py` 全 PASS。
