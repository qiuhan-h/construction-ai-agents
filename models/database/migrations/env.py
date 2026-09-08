"""Alembic 迁移环境：连接串由 config.get_settings() 注入。

运行方式（仓库根目录）：
    alembic revision --autogenerate -m "initial schema"
    alembic upgrade head
"""

from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# 保证 `python -m alembic` 或从任意工作目录运行时都能导入项目包
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from config import get_settings  # noqa: E402
from models.database import (  # noqa: E402,F401  导入即注册全部表元数据
    AlertTable,
    CaseTable,
    ConstructionPlanTable,
    GeofenceTable,
    GeofenceViolationTable,
    InspectionTable,
    ProjectTable,
    RegulationTable,
    ReviewReportTable,
    SensorDeviceTable,
    StandardTable,
    TenantTable,
    ViolationTable,
)
from models.database.base import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 连接串统一来自全局配置（环境变量 > 分环境 YAML > 默认值），
# 不依赖 alembic.ini 中的硬编码
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL 脚本，不建立连接。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：建立连接执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
