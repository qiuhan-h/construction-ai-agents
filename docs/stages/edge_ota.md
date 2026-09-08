# 7e-4 边缘设备 OTA 升级流程

> 用途：现场监控设备（边缘节点）固件 OTA 升级流程。
>
> 适用设备：ESP32/树莓派等 IoT 边缘设备，通过 MQTT 与后端通信。

## 1. OTA 架构

```
后端 API  ──发布任务──>  MQTT broker  ──推送──>  边缘设备
                                                      │
后端 API  <──状态上报──  MQTT broker  <──进度上报──  边缘设备
```

## 2. 发布流程

### 2.1 准备固件

```
1. 编译固件：pio run --target build  # 或平台等效命令
2. 生成固件包：firmware-v1.2.0.bin    # 需要补充实际链接：固件版本号
3. 上传到对象存储：oss cp firmware-v1.2.0.bin oss://caai-firmware/  # 需要补充实际链接：OSS bucket
4. 计算固件哈希：sha256sum firmware-v1.2.0.bin
```

### 2.2 创建 OTA 任务

```bash
# 通过 API 创建 OTA 任务
curl -X POST https://api.example.com/api/v1/ota/tasks \  # 需要补充实际链接：真实域名
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d '{
    "version": "v1.2.0",  # 需要补充实际链接：固件版本
    "url": "https://oss.example.com/caai-firmware/firmware-v1.2.0.bin",  # 需要补充实际链接：固件下载URL
    "sha256": "__需要补充实际链接：固件SHA256__",
    "target_devices": ["device-001", "device-002"],  # 需要补充实际链接：目标设备列表
    "rollout_strategy": "canary"  # canary（10%→50%→100%）或 full
  }'
```

### 2.3 灰度发布

| 阶段 | 设备比例 | 观察时间 | 通过标准 |
|---|---|---|---|
| Canary | 10% | 15 分钟 | 失败率 < 5%，无崩溃 |
| Ramp | 50% | 30 分钟 | 失败率 < 2%，无崩溃 |
| Full | 100% | 持续监控 | 无异常 |

### 2.4 状态监控

```
MQTT 主题：
  - ota/device-001/progress    # 上报进度 0-100%
  - ota/device-001/status      # 状态：downloading/installing/rebooting/success/failed
  - ota/device-001/error       # 错误信息（失败时）
```

## 3. 回滚流程

### 3.1 自动回滚

设备在升级后 5 分钟内未上报心跳 → 自动回滚到上一版本。

### 3.2 手动回滚

```bash
# 发布回滚任务
curl -X POST https://api.example.com/api/v1/ota/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "version": "v1.1.9",  # 需要补充实际链接：回滚版本号
    "url": "https://oss.example.com/caai-firmware/firmware-v1.1.9.bin",
    "sha256": "__需要补充实际链接：固件SHA256__",
    "target_devices": ["device-001", "device-002"],
    "rollout_strategy": "full",
    "is_rollback": true
  }'
```

## 4. 安全要求

| 项 | 要求 |
|---|---|
| 固件签名 | 固件包必须使用 Ed25519 签名，设备验签后才安装 |
| 下载通道 | HTTPS + 预共享密钥认证 |
| 版本校验 | 设备拒绝降级（低于当前版本的固件不安装，除非标记 is_rollback=true） |
| 断电恢复 | 升级前写入 backup 分区，断电后自动恢复 |
| 超时处理 | 下载超时 10 分钟、安装超时 5 分钟，超时自动回滚 |

## 5. 验收清单

- [ ] 固件包已签名
- [ ] SHA256 已计算
- [ ] OTA 任务已创建
- [ ] Canary 阶段 15 分钟无异常
- [ ] 全量发布完成
- [ ] 全部设备上报 success 状态
- [ ] 回滚任务已测试
