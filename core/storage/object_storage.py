# 阶段六 6b 预留：对象存储后端（OSS / S3 / MinIO）。
# 用途：报告 PDF、BIM 模型切片、日志归档等大文件上传至云端对象存储。
# 接口：upload(key, stream, content_type) -> url / download(key) -> stream / delete(key)。
# 实现：阿里云 OSS 优先（oss2），兼容 S3 协议（boto3），dev 环境降级到本地磁盘。
