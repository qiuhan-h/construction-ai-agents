"""启动 Celery worker（4d）。

设计（O3 / 4d D8）：
- broker 走 ``services.celery_app.app``；缺包时降级为 mock 模式（空跑 + 信号退出）；
- mock 模式下注册 SIGINT / SIGTERM handler 优雅退出；
- worker 启动失败时打印明确错误 + 回退 mock；
- 额外注入 ``celery_app.conf["agent_manager"]`` 供编排器节点任务使用（4c+）；

用法：
    python scripts/start_worker.py
    python scripts/start_worker.py --queues default,alerts
    python scripts/start_worker.py --concurrency 2
    python scripts/start_worker.py --mock          # 强制走 mock 模式
    python scripts/start_worker.py --loglevel DEBUG
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from typing import Any

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger("scripts.start_worker")


# =====================================================
# 工具
# =====================================================
def _build_celery_app() -> Any:
    """构造 Celery 应用（含 AgentManager 注入）。"""
    from services.celery_app import app
    # 注入 AgentManager（worker 端用于执行 agent.handle）
    try:
        from api.dependencies.agent_manager import get_agent_manager
        app.conf["agent_manager"] = get_agent_manager()
        logger.info("已注入 AgentManager 到 celery_app.conf")
    except Exception as e:  # noqa: BLE001
        logger.warning("AgentManager 注入失败（节点任务将走 mock 完成）: %s", e)
        app.conf["agent_manager"] = None
    # 注入 WorkflowEngine（用于 _dispatch_node 解析 TaskSpec）
    try:
        from core.orchestrator.workflow_engine import WorkflowEngine
        app.conf["workflow_engine"] = WorkflowEngine()
    except Exception as e:  # noqa: BLE001
        logger.warning("WorkflowEngine 注入失败: %s", e)
        app.conf["workflow_engine"] = None
    return app


def _install_signal_handlers(loop_running: bool = False) -> None:
    """注册 SIGINT / SIGTERM handler，让 Ctrl+C 优雅退出。"""
    def _handler(signum, _frame):  # noqa: ANN001
        logger.info("收到信号 %s，准备退出...", signum)
        sys.exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError) as e:  # noqa: PERF203
            logger.debug("注册信号 %s 失败: %s", sig, e)


# =====================================================
# Mock 模式
# =====================================================
def run_mock(args: argparse.Namespace) -> int:
    """不实际拉起 worker，循环 sleep 直到被信号打断。"""
    _install_signal_handlers()
    logger.warning(
        "运行在 mock 模式（celery_app 未就绪或 --mock 强制）："
        "broker=%s queues=%s",
        "memory", args.queues,
    )
    print(
        f"  worker (mock)  pid={os.getpid()}  "
        f"queues={args.queues}  Ctrl+C to exit"
    )
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("mock worker exit")
        return 0


# =====================================================
# Celery worker 模式
# =====================================================
def run_celery_worker(args: argparse.Namespace) -> int:
    """拉起 celery worker。"""
    try:
        app = _build_celery_app()
    except Exception as e:  # noqa: BLE001
        logger.error("构造 celery_app 失败: %s", e)
        if args.fallback_mock:
            logger.warning("降级 mock 模式")
            return run_mock(args)
        return 1

    broker = app.conf.broker_url or ""
    if not broker or broker.startswith("memory"):
        logger.info(
            "检测到 broker=memory://，任务在内存执行；"
            "若仅验证 worker 启动，可继续。"
        )

    queues = [q.strip() for q in args.queues.split(",") if q.strip()] or ["default"]
    argv = [
        "worker",
        "-Q",
        ",".join(queues),
        f"--concurrency={args.concurrency}",
        f"--loglevel={args.loglevel.upper()}",
    ]
    logger.info(
        "启动 celery worker: queues=%s concurrency=%s loglevel=%s",
        queues, args.concurrency, args.loglevel,
    )
    try:
        app.worker_main(argv=argv)
        return 0
    except KeyboardInterrupt:
        logger.info("celery worker KeyboardInterrupt 退出")
        return 0
    except SystemExit as e:
        # celery worker 退出码
        rc = int(e.code) if isinstance(e.code, int) else 0
        logger.info("celery worker 退出: rc=%s", rc)
        return rc


# =====================================================
# CLI
# =====================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="阶段 4d：启动 Celery worker")
    parser.add_argument(
        "--queues",
        default="default",
        help="逗号分隔的队列名（默认 default）",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="worker 并发数（默认 2）",
    )
    parser.add_argument(
        "--loglevel",
        default="INFO",
        help="日志级别（默认 INFO）",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="强制走 mock 模式（不拉起 celery worker）",
    )
    parser.add_argument(
        "--fallback-mock",
        action="store_true",
        help="celery_app 加载失败时降级 mock",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=args.loglevel.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    # 强制 mock
    if args.mock:
        return run_mock(args)

    # 尝试拉起 celery
    try:
        from services.celery_app import app  # noqa: F401
    except Exception as e:  # noqa: BLE001
        logger.warning("celery_app 加载失败: %s", e)
        if args.fallback_mock:
            return run_mock(args)
        return 1

    return run_celery_worker(args)


if __name__ == "__main__":
    sys.exit(main())
