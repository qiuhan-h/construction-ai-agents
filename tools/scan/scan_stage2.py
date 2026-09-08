"""统计阶段二目标文件的当前状态（已写 / 0 字节 / 不存在）。"""
import os
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[3] / "construction-ai-agents")  # 跨平台
STAGE2 = [
    "core/a2a/__init__.py",
    "core/a2a/agent_card.py",
    "core/a2a/client.py",
    "core/a2a/message.py",
    "core/a2a/middleware.py",
    "core/a2a/protocol.py",
    "core/a2a/serializers.py",
    "core/a2a/server.py",
    "core/mcp/__init__.py",
    "core/mcp/client.py",
    "core/mcp/server.py",
    "core/mcp/prompts/__init__.py",
    "core/mcp/prompts/safety_prompts.py",
    "core/mcp/resources/__init__.py",
    "core/mcp/resources/case_resource.py",
    "core/mcp/resources/regulation_resource.py",
    "core/mcp/resources/standard_resource.py",
    "core/mcp/tools/__init__.py",
    "core/mcp/tools/analysis_tools.py",
    "core/mcp/tools/calculation_tools.py",
    "core/mcp/tools/validation_tools.py",
    "core/events/__init__.py",
    "core/events/event_bus.py",
    "core/events/events.py",
    "api/__init__.py",
    "api/schemas/a2a_schemas.py",
    "api/schemas/agent_schemas.py",
    "api/schemas/response_schemas.py",
    "api/schemas/pagination.py",
    "api/routers/a2a_router.py",
    "api/routers/mcp_router.py",
    "agents/__init__.py",
    "agents/base_agent.py",
    "config/logging_config.py",
    "scripts/start_a2a_server.py",
    "scripts/start_mcp_server.py",
]

print(f"{'path':60} {'size':>8}  {'status'}")
print("-" * 90)
exists = empty = missing = 0
for rel in STAGE2:
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        print(f"{rel:60} {'':>8}  MISSING")
        missing += 1
        continue
    size = os.path.getsize(p)
    if size == 0:
        print(f"{rel:60} {size:>8}  EMPTY")
        empty += 1
    else:
        print(f"{rel:60} {size:>8}  OK")
        exists += 1
print("-" * 90)
print(f"已实现: {exists}    0 字节占位: {empty}    不存在: {missing}    合计: {len(STAGE2)}")

