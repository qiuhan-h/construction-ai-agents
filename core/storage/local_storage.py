# 阶段六 6d 预留：本地文件存储后端。
# 用途：边缘端离线模式下替代 OSS，将报告 PDF / 附件缓存到本地磁盘。
# 接口：save(key, data) -> path / load(key) -> data / delete(key) / exists(key)。
# 与 core/storage/sqlalchemy_repos.py 互补：ORM 管结构化数据，本模块管文件二进制。
