"""日志配置：统一入口 + 控制台/滚动文件双输出。"""

from __future__ import annotations

import logging
import logging.config

from config.settings import get_settings

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def build_logging_config(log_level: str, log_dir: str) -> dict:
    """构造 dictConfig 配置。"""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {"format": _FORMAT},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "DEBUG",
                "formatter": "standard",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "INFO",
                "formatter": "standard",
                "filename": f"{log_dir}/app.log",
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            # 降低第三方库噪音
            "uvicorn": {"level": "INFO"},
            "httpx": {"level": "WARNING"},
            "httpcore": {"level": "WARNING"},
            "celery": {"level": "INFO"},
        },
        "root": {
            "level": log_level.upper(),
            "handlers": ["console", "file"],
        },
    }


def setup_logging(log_level: str | None = None) -> None:
    """初始化全局日志。

    Args:
        log_level: 覆盖配置中的日志级别（测试时常用 "DEBUG"）。
    """
    settings = get_settings()
    level = log_level or settings.log_level
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(build_logging_config(level, str(settings.log_dir)))


def get_logger(name: str) -> logging.Logger:
    """获取命名日志器（各模块统一入口）。"""
    return logging.getLogger(name)
