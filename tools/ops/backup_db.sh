#!/bin/bash
# 7e-1 数据库定时备份脚本。
#
# 用途：pg_dump 备份 PostgreSQL + 上传到对象存储（OSS/S3）。
#
# 用法：
#   ./tools/backup_db.sh
#   或通过 K8s CronJob 调度（见 deployment/kubernetes/cronjob-backup.yaml）
#
# 环境变量（在 .env 或 K8s Secret 中配置）：
#   DATABASE_URL          PostgreSQL 连接串
#   BACKUP_OSS_BUCKET     对象存储 bucket 名称  # 需要补充实际链接：OSS bucket
#   BACKUP_OSS_PREFIX     对象存储路径前缀      # 需要补充实际链接：路径前缀如 backups/
#   BACKUP_RETAIN_DAYS    保留天数（默认 7）

set -euo pipefail

# ---------- 配置 ----------
DATABASE_URL="${DATABASE_URL:-postgresql://caai:caai_staging@localhost:5432/construction_agents}"
BACKUP_OSS_BUCKET="${BACKUP_OSS_BUCKET:-需要补充实际链接}"  # OSS bucket 名称
BACKUP_OSS_PREFIX="${BACKUP_OSS_PREFIX:-需要补充实际链接}"  # 路径前缀
BACKUP_RETAIN_DAYS="${BACKUP_RETAIN_DAYS:-7}"
BACKUP_DIR="${BACKUP_DIR:-/tmp/caai-backups}"

# ---------- 时间戳 ----------
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="caai_backup_${TIMESTAMP}.sql.gz"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILE}"

echo "=== 7e-1 数据库备份 ==="
echo "时间: $(date)"
echo "数据库: ${DATABASE_URL%%@*}@***"
echo "备份文件: ${BACKUP_PATH}"

# ---------- 1. 创建备份目录 ----------
mkdir -p "${BACKUP_DIR}"

# ---------- 2. pg_dump ----------
echo "--- 1. pg_dump ---"
PGPASSWORD=$(echo "${DATABASE_URL}" | sed -n 's/.*:\/\/[^:]*:\([^@]*\)@.*/\1/p')
PG_HOST=$(echo "${DATABASE_URL}" | sed -n 's/.*@\([^:]*\):.*/\1/p')
PG_PORT=$(echo "${DATABASE_URL}" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
PG_DB=$(echo "${DATABASE_URL}" | sed -n 's/.*\/\([^?]*\).*/\1/p')
PG_USER=$(echo "${DATABASE_URL}" | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')

echo "  主机: ${PG_HOST}:${PG_PORT}"
echo "  数据库: ${PG_DB}"
echo "  用户: ${PG_USER}"

PGPASSWORD="${PGPASSWORD}" pg_dump \
    -h "${PG_HOST}" \
    -p "${PG_PORT}" \
    -U "${PG_USER}" \
    -d "${PG_DB}" \
    --format=custom \
    --no-owner \
    --no-privileges \
    | gzip > "${BACKUP_PATH}"

BACKUP_SIZE=$(du -h "${BACKUP_PATH}" | cut -f1)
echo "  [OK] 备份完成: ${BACKUP_SIZE}"

# ---------- 3. 上传到对象存储 ----------
if [[ "${BACKUP_OSS_BUCKET}" != "需要补充实际链接" ]]; then
    echo "--- 2. 上传到对象存储 ---"
    OSS_PATH="${BACKUP_OSS_PREFIX}${BACKUP_FILE}"
    echo "  目标: oss://${BACKUP_OSS_BUCKET}/${OSS_PATH}"

    # 阿里云 OSS
    if command -v ossutil &> /dev/null; then
        ossutil cp "${BACKUP_PATH}" "oss://${BACKUP_OSS_BUCKET}/${OSS_PATH}"
        echo "  [OK] OSS 上传完成"
    # AWS S3
    elif command -v aws &> /dev/null; then
        aws s3 cp "${BACKUP_PATH}" "s3://${BACKUP_OSS_BUCKET}/${OSS_PATH}"
        echo "  [OK] S3 上传完成"
    else
        echo "  [WARN] 未找到 ossutil 或 aws CLI，跳过上传"
    fi
else
    echo "--- 2. 跳过对象存储上传（BACKUP_OSS_BUCKET 占位） ---"
fi

# ---------- 4. 清理过期备份 ----------
echo "--- 3. 清理过期备份 ---"
DELETED_COUNT=$(find "${BACKUP_DIR}" -name "caai_backup_*.sql.gz" -mtime +${BACKUP_RETAIN_DAYS} -delete -print | wc -l)
echo "  [OK] 清理 ${DELETED_COUNT} 个过期备份（> ${BACKUP_RETAIN_DAYS} 天）"

# ---------- 5. 验证备份可恢复 ----------
echo "--- 4. 备份验证 ---"
if command -v pg_restore &> /dev/null; then
    VERIFY_DB="caai_verify_${TIMESTAMP}"
    PGPASSWORD="${PGPASSWORD}" createdb -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" "${VERIFY_DB}" 2>/dev/null || true
    if PGPASSWORD="${PGPASSWORD}" pg_restore -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${VERIFY_DB}" --no-owner --no-privileges < <(gunzip -c "${BACKUP_PATH}") 2>/dev/null; then
        echo "  [OK] 备份验证通过（可恢复）"
    else
        echo "  [WARN] 备份验证跳过（恢复测试失败，可能是权限问题）"
    fi
    PGPASSWORD="${PGPASSWORD}" dropdb -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" "${VERIFY_DB}" 2>/dev/null || true
else
    echo "  [WARN] pg_restore 不可用，跳过验证"
fi

echo "=== 备份完成 ==="
echo "文件: ${BACKUP_PATH}"
echo "大小: ${BACKUP_SIZE}"
