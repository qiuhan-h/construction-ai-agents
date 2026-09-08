# 阶段七 7d：生产发布流程

> 阶段目标：预发环境通过 Go/No-Go 预检后，执行滚动发布、上线验证、观察期巡检。
>
> 前置条件：7a 生产硬化 + 7b 接口联调 + 7c 预发验证 全部通过。

## 1. 发布窗口

| 项 | 值 |
|---|---|
| 推荐时段 | 周二/周三 02:00-04:00（低峰期，便于值班响应） |
| 避免时段 | 周五周末前、节假日前、月底财务结算日 |
| 预计耗时 | 镜像构建 10 分钟 + 滚动发布 15 分钟 + 验证 10 分钟 = 35 分钟 |
| 回滚窗口 | 发布后 30 分钟内可快速回滚；超时需走 downgrade 流程 |

## 2. 发布前预检（Day 0）

```bash
# 1. Go/No-Go 预检
APP_ENV=prod python tools/ops/go_nogo_checklist.py
# 预期：exit 0 (GO) 或 exit 2 (GO WITH WARNING，需签字)
# exit 1 (NO-GO) 必须解决阻断项后重新预检

# 2. 全量回归
python tools/verify/verify_all.py
# 预期：14/14 通过 100%

# 3. 生产配置校验
APP_ENV=prod python tools/verify/verify_prod_config.py
# 预期：[OK] 生产配置校验通过

# 4. E2E 冒烟
python -m pytest tests/e2e/ -v
# 预期：全通过
```

## 3. 镜像构建与推送

```bash
# 1. 标记版本
export RELEASE_VERSION=v1.0.0  # 需要补充实际链接：真实版本号
export IMAGE_REGISTRY=registry.example.com  # 需要补充实际链接：镜像仓库地址
docker tag caai-api:latest $IMAGE_REGISTRY/caai-api:$RELEASE_VERSION
docker tag caai-worker:latest $IMAGE_REGISTRY/caai-worker:$RELEASE_VERSION
docker tag caai-a2a:latest $IMAGE_REGISTRY/caai-a2a:$RELEASE_VERSION
docker tag caai-mcp:latest $IMAGE_REGISTRY/caai-mcp:$RELEASE_VERSION
docker tag caai-streamlit:latest $IMAGE_REGISTRY/caai-streamlit:$RELEASE_VERSION

# 2. 推送镜像
docker push $IMAGE_REGISTRY/caai-api:$RELEASE_VERSION
docker push $IMAGE_REGISTRY/caai-worker:$RELEASE_VERSION
docker push $IMAGE_REGISTRY/caai-a2a:$RELEASE_VERSION
docker push $IMAGE_REGISTRY/caai-mcp:$RELEASE_VERSION
docker push $IMAGE_REGISTRY/caai-streamlit:$RELEASE_VERSION

# 3. 记录前一版本 tag（用于回滚）
export PREV_VERSION=v0.9.9  # 需要补充实际链接：前一稳定版本号
```

## 4. 滚动发布（K8s）

```bash
# 1. 更新 K8s manifests 镜像 tag
sed -i "s|caai-api:.*|caai-api:$RELEASE_VERSION|g" deployment/kubernetes/*.yaml
sed -i "s|caai-worker:.*|caai-worker:$RELEASE_VERSION|g" deployment/kubernetes/*.yaml
sed -i "s|caai-a2a:.*|caai-a2a:$RELEASE_VERSION|g" deployment/kubernetes/*.yaml
sed -i "s|caai-mcp:.*|caai-mcp:$RELEASE_VERSION|g" deployment/kubernetes/*.yaml
sed -i "s|caai-streamlit:.*|caai-streamlit:$RELEASE_VERSION|g" deployment/kubernetes/*.yaml

# 2. 应用配置（先 ConfigMap/Secret，再 Deployment）
kubectl apply -f deployment/kubernetes/secrets.yaml
kubectl apply -f deployment/kubernetes/configmap.yaml  # 需要补充实际链接：如存在
kubectl apply -f deployment/kubernetes/api-deployment.yaml  # 需要补充实际链接：实际文件名
kubectl apply -f deployment/kubernetes/worker-deployment.yaml
kubectl apply -f deployment/kubernetes/a2a-deployment.yaml
kubectl apply -f deployment/kubernetes/mcp-deployment.yaml
kubectl apply -f deployment/kubernetes/streamlit-deployment.yaml

# 3. 滚动更新
kubectl set image deployment/caai-api api=$IMAGE_REGISTRY/caai-api:$RELEASE_VERSION
kubectl set image deployment/caai-worker worker=$IMAGE_REGISTRY/caai-worker:$RELEASE_VERSION
kubectl rollout status deployment/caai-api --timeout=300s
kubectl rollout status deployment/caai-worker --timeout=300s

# 4. 数据库迁移
kubectl exec deploy/caai-api -- alembic upgrade head

# 5. 等待就绪
kubectl wait --for=condition=ready pod -l app=caai-api --timeout=180s
kubectl wait --for=condition=ready pod -l app=caai-worker --timeout=180s
```

## 5. 流量切换（蓝绿/金丝雀）

```bash
# 选项 A：蓝绿（推荐）
kubectl patch service caai-api -p '{"spec":{"selector":{"version":"'$RELEASE_VERSION'"}}}'
# 旧版本 Pod 保留 30 分钟用于回滚

# 选项 B：金丝雀（10% → 50% → 100%）
kubectl patch service caai-api -p '{"spec":{"selector":{"canary":"10"}}}'
# 观察 5 分钟后逐步提升
kubectl patch service caai-api -p '{"spec":{"selector":{"canary":"50"}}}'
# 观察 10 分钟后全量
kubectl patch service caai-api -p '{"spec":{"selector":{"canary":"100"}}}'
```

## 6. 发布后验证

```bash
# 1. 健康检查
curl https://api.example.com/api/v1/health/healthz  # 需要补充实际链接：真实域名
curl https://api.example.com/api/v1/health/readyz

# 2. E2E 冒烟
python tools/smoke/smoke_7b_real.py
python tools/smoke/smoke_e2e.py

# 3. 上线验证脚本
python tools/verify/verify_post_deploy.py  # 7d-3 将创建
```

## 7. 回滚流程

### 快速回滚（发布后 30 分钟内）

```bash
# 1. 切换镜像 tag 到前一版本
kubectl set image deployment/caai-api api=$IMAGE_REGISTRY/caai-api:$PREV_VERSION
kubectl set image deployment/caai-worker worker=$IMAGE_REGISTRY/caai-worker:$PREV_VERSION
kubectl rollout status deployment/caai-api --timeout=180s
kubectl rollout status deployment/caai-worker --timeout=180s

# 2. 数据库回滚（如有 migration）
kubectl exec deploy/caai-api -- alembic downgrade -1

# 3. 验证
curl https://api.example.com/api/v1/health/healthz
```

### 回滚演练

```bash
# 定期演练（建议每月一次）
python tools/ops/rollback_drill.py  # 7d-4 将创建
```

## 8. 发布后观察期（7d-5）

| 时段 | 频率 | 检查项 |
|---|---|---|
| 0-1h | 每 5 分钟 | healthz + readyz + 错误率 + 响应时间 |
| 1-4h | 每 15 分钟 | 同上 + 资源占用 + 日志异常 |
| 4-24h | 每 30 分钟 | 同上 + 配额使用 + 租户活跃度 |
| 24-72h | 每 2 小时 | 同上 + 告警通道 + 备份状态 |

## 9. 发布签字单

```
项目: 建筑工程智能体集群
版本: __需要补充实际链接：版本号__
日期: __需要补充实际链接：发布日期__

Go/No-Go 预检: [ ] GO  [ ] GO WITH WARNING  [ ] NO-GO
签字: __需要补充实际链接：预检负责人__

镜像构建: [ ] 完成  签字: __需要补充实际链接：构建负责人__
滚动发布: [ ] 完成  签字: __需要补充实际链接：发布负责人__
上线验证: [ ] 完成  签字: __需要补充实际链接：验证负责人__
观察期 0-1h: [ ] 完成  签字: __需要补充实际链接：值班人员__

最终状态: [ ] 上线成功  [ ] 回滚  [ ] 推迟
备注: __需要补充实际链接：补充说明__
```

## 10. 通讯录

| 角色 | 姓名 | 联系方式 |
|---|---|---|
| 发布负责人 | __需要补充实际链接：姓名__ | __需要补充实际链接：手机/钉钉__ |
| 值班工程师 | __需要补充实际链接：姓名__ | __需要补充实际链接：手机/钉钉__ |
| DBA | __需要补充实际链接：姓名__ | __需要补充实际链接：手机/钉钉__ |
| 运维负责人 | __需要补充实际链接：姓名__ | __需要补充实际链接：手机/钉钉__ |
```
