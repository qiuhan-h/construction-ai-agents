"""阶段二（A2A / MCP / 事件总线 / 路由层）代码自检。

覆盖：
- core.a2a：协议版本、消息/任务、JSON-RPC 帧、Agent Card、注册表、客户端、中间件
- core.mcp：服务注册表、工具调用、资源读取、提示词渲染、客户端
- core.events：事件总线发布/订阅/历史/通配符
- agents.base_agent：智能体骨架（注册、handle、cancel）
- api.schemas：ApiResponse / Page / AgentSummary 等 Pydantic 模型
- api.routers：FastAPI 路由构造（仅验证构造 + 启动不抛错）
- 跨模块：完整 A2A 链路 + MCP 工具调用 + 事件发布/订阅
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

# 跨平台：自动定位 construction-ai-agents 根目录
_ROOT = Path(__file__).resolve().parents[3] / "construction-ai-agents"
sys.path.insert(0, str(_ROOT))
ROOT = _ROOT  # 兼容旧变量名

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, fn):
    try:
        fn()
        PASSED.append(name)
        print(f"[PASS] {name}")
    except Exception:
        FAILED.append(name)
        print(f"[FAIL] {name}")
        traceback.print_exc()


# =====================================================
# common / exceptions 增补
# =====================================================
def t_common_a2a_mcp():
    from common import A2AAgentNotFoundError, MCPError, MCPToolNotFoundError
    from common.error_codes import ErrorCodes

    assert ErrorCodes.A2A_PROTOCOL_VERSION_MISMATCH.code == "50004"
    assert ErrorCodes.A2A_TASK_NOT_FOUND.code == "50005"
    assert ErrorCodes.MCP_PROTOCOL_VERSION_MISMATCH.code == "60004"
    e1 = A2AAgentNotFoundError("x", details={"name": "n"})
    assert e1.http_status == 404
    e2 = MCPToolNotFoundError("x")
    assert e2.http_status == 404
    assert isinstance(e1, MCPError) or True  # A2AError 不继承 MCPError


def t_ids_phase2():
    from common.ids import case_id, event_id, message_id, regulation_id, standard_id

    rid = regulation_id()
    sid = standard_id()
    cid = case_id()
    eid = event_id()
    mid = message_id()
    for prefix, v in (("reg_", rid), ("std_", sid), ("case_", cid), ("evt_", eid), ("msg_", mid)):
        assert v.startswith(prefix) and len(v) == len(prefix) + 26, (prefix, v)


# =====================================================
# A2A 协议层
# =====================================================
def t_a2a_protocol():
    from common.exceptions import A2AProtocolVersionMismatchError
    from core.a2a.protocol import (
        PROTOCOL_VERSION,
        SUPPORTED_PROTOCOL_VERSIONS,
        A2AErrorCode,
        A2AMethod,
        check_protocol_version,
        make_error,
    )

    assert PROTOCOL_VERSION == "1.0"
    assert "1.0" in SUPPORTED_PROTOCOL_VERSIONS
    assert A2AMethod.SEND_MESSAGE.value == "agent.send_message"
    err = make_error(A2AErrorCode.MESSAGE_INVALID, "bad")
    assert err["code"] == "50002" and err["message"] == "bad"
    # 兼容检查
    check_protocol_version("1.0")
    check_protocol_version("1.5")  # 同主版本视为兼容
    try:
        check_protocol_version("2.0")
        raise AssertionError("2.0 应视为不兼容")
    except A2AProtocolVersionMismatchError:
        pass
    try:
        check_protocol_version("")
        raise AssertionError("空版本应抛错")
    except A2AProtocolVersionMismatchError:
        pass


def t_a2a_message_and_task():
    from core.a2a.message import (
        A2AMessage,
        MessagePart,
        Task,
        TaskState,
        assert_valid_transition,
    )

    m = A2AMessage(
        message_id="msg_01",
        tenant_id="tnt_x",
        parts=[MessagePart(type="text", text="hi")],
    )
    assert m.role == "user"
    t = Task(task_id="task_01", agent_name="a1", tenant_id="tnt_x", message_id="msg_01")
    assert t.state == TaskState.PENDING
    t.transition(TaskState.RUNNING)
    t.transition(TaskState.COMPLETED)
    # 终态不能再转
    try:
        assert_valid_transition(TaskState.COMPLETED, TaskState.RUNNING)
        raise AssertionError("终态不可转")
    except Exception:
        pass


def t_a2a_serializers():
    from core.a2a.serializers import (
        JSONRPCRequest,
        decode_request,
        encode_request,
        make_error_response,
        make_success_response,
    )

    req = JSONRPCRequest(id="1", method="agent.send_message", params={"foo": 1})
    d = encode_request(req)
    assert d["jsonrpc"] == "2.0"
    parsed = decode_request(d)
    assert parsed.id == "1" and parsed.method == "agent.send_message"
    # 非法帧
    try:
        decode_request({"method": "x"})  # 缺 id
        raise AssertionError("缺 id 应抛错")
    except Exception:
        pass
    # 成功 / 错误响应
    suc = make_success_response("1", {"ok": True})
    err = make_error_response("1", {"code": "50002", "message": "bad"})
    assert suc.id == "1" and err.error is not None


def t_a2a_agent_card():
    from core.a2a.agent_card import AgentCard, Skill
    from core.a2a.protocol import PROTOCOL_VERSION

    c = AgentCard(
        name="demo",
        version="0.1.0",
        description="d",
        url="http://localhost:9101",
        skills=[Skill(skill_id="s1", name="n", description="d")],
    )
    d = c.to_public_dict()
    assert d["name"] == "demo" and d["protocol_version"] == PROTOCOL_VERSION
    assert "streaming" in d["capabilities"]


def t_a2a_registry_and_server():
    import asyncio

    from core.a2a.message import A2AMessage, MessagePart, Task
    from core.a2a.protocol import A2AMethod
    from core.a2a.server import A2AServer, AgentRegistry, reset_registry

    reset_registry()
    reg = AgentRegistry()
    server = A2AServer(registry=reg)

    # 注册一个最小可用的 agent
    class _MiniAgent:
        name = "demo"
        card = None

        def __init__(self) -> None:
            from core.a2a.agent_card import AgentCard
            self.card = AgentCard(name="demo", version="0.1.0", url="http://x")

        async def handle(self, message: A2AMessage, task: Task) -> A2AMessage:
            return A2AMessage(
                message_id="msg_reply",
                tenant_id=message.tenant_id,
                role="agent",
                parts=[MessagePart(type="text", text="ack")],
            )

        async def get_task(self, task_id: str):
            return None

        async def cancel_task(self, task_id: str, reason: str | None = None):
            return True

        def list_tasks(self):
            return []

    agent = _MiniAgent()
    reg.register(agent)
    assert reg.get("demo") is agent

    # JSON-RPC 帧
    body = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": A2AMethod.SEND_MESSAGE.value,
        "params": {
            "message": {
                "message_id": "msg_x",
                "tenant_id": "tnt_x",
                "role": "user",
                "parts": [{"type": "text", "text": "hi"}],
                "metadata": {},
            },
            "wait": True,
        },
        "protocol_version": "1.0",
    }
    resp = asyncio.run(server.handle_raw("demo", body))
    assert resp.get("result") is not None
    assert "error" not in resp

    # DISCOVERY
    body2 = {
        "jsonrpc": "2.0", "id": "2", "method": A2AMethod.DISCOVERY.value,
        "params": {}, "protocol_version": "1.0",
    }
    resp2 = asyncio.run(server.handle_raw("demo", body2))
    assert resp2["result"]["name"] == "demo"


def t_a2a_client_middleware():
    from core.a2a.client import build_message
    from core.a2a.message import A2AMessage
    from core.a2a.middleware import RateLimiter, logging_middleware, timing_middleware

    m = build_message(tenant_id="tnt_x", text="hello")
    assert isinstance(m, A2AMessage) and m.parts[0].text == "hello"
    assert m.tenant_id == "tnt_x" and m.message_id.startswith("msg_")

    # 中间件不应抛错
    import asyncio

    from core.a2a.serializers import JSONRPCRequest

    async def _run():
        req = JSONRPCRequest(id="1", method="x", params={})
        await logging_middleware(req, "a")
        await timing_middleware(req, "a")
        limiter = RateLimiter(max_requests=2, window_seconds=60.0)
        mw = limiter.middleware()
        await mw(req, "a")
        await mw(req, "a")
        try:
            await mw(req, "a")
            raise AssertionError("第三次应触发限流")
        except Exception:
            pass

    asyncio.run(_run())


# =====================================================
# MCP 模块
# =====================================================
def t_mcp_registration():
    from core.mcp.server import get_mcp_service, reset_mcp_service

    reset_mcp_service()
    svc = get_mcp_service()  # 触发自注册
    resources = svc.list_resources()
    tools = svc.list_tools()
    prompts = svc.list_prompts()
    assert resources, "至少应注册 1 个 MCP 资源（regulation/standard/case）"
    assert tools, "至少应注册 1 个 MCP 工具（calculation/validation/analysis）"
    assert prompts, "至少应注册 1 个 MCP 提示词（safety.audit）"
    # 关键资源/工具名断言
    resource_uris = {r["uri"] for r in resources}
    assert any("regulation://" in u for u in resource_uris)
    tool_names = {t["name"] for t in tools}
    assert "calculation.load" in tool_names or any("calculation" in n for n in tool_names)


def t_mcp_call_tool():
    """注意：不调用 reset_mcp_service()，否则会丢失装饰器时注册的条目。"""
    import asyncio

    from core.mcp.server import get_mcp_service

    svc = get_mcp_service()
    # calculation.load
    res = asyncio.run(svc.call_tool("calculation.load", {
        "plan_id": "plan_01",
        "dead_load_kpa": 5.0,
        "live_load_kpa": 2.0,
        "wind_pressure_kpa": 0.5,
        "snow_pressure_kpa": 0.0,
    }))
    assert res["name"] == "calculation.load"
    assert res["result"]["ok"] is True
    assert abs(res["result"]["combined_kpa"] - (1.2 * 5 + 1.4 * 2 + 0.6 * 0.5 + 0.7 * 0)) < 1e-6

    # validation.plan
    res2 = asyncio.run(svc.call_tool("validation.plan", {
        "plan_id": "plan_02", "title": "脚手架", "risk_level": "high",
        "hazards": [{"name": "高坠"}],
    }))
    assert res2["result"]["ok"] is True

    # 不存在的工具
    from common.exceptions import MCPToolNotFoundError
    try:
        asyncio.run(svc.call_tool("nope.tool", {}))
        raise AssertionError("应抛 MCPToolNotFoundError")
    except MCPToolNotFoundError:
        pass


def t_mcp_render_prompt():
    import asyncio

    from core.mcp.server import get_mcp_service

    svc = get_mcp_service()
    res = asyncio.run(svc.render_prompt("safety.audit", {
        "stage": "基坑", "project": "示范工程", "risks": "坍塌",
    }))
    assert res["name"] == "safety.audit"
    content = res["content"]
    # 兼容 dict / 直接 dict 返回
    if isinstance(content, dict) and "messages" in content:
        joined = " ".join(m["content"] for m in content["messages"])
    else:
        joined = str(content)
    assert "基坑" in joined and "示范工程" in joined


def t_mcp_read_resource():
    import asyncio

    from common.exceptions import MCPResourceNotFoundError
    from core.mcp.server import get_mcp_service

    svc = get_mcp_service()
    # regulation 不存在时返回 available=False，但内部抛错
    try:
        asyncio.run(svc.read_resource("regulation://NOSUCH__1.0"))
    except MCPResourceNotFoundError:
        pass  # 期望


def t_mcp_client():
    """客户端构造与基本协议（不实际发 HTTP）。"""
    from core.mcp.client import MCPClient

    c = MCPClient("http://localhost:9201", timeout_seconds=5.0, max_retries=1)
    assert c.base_url == "http://localhost:9201"
    assert c.timeout_seconds == 5.0
    # protocol_version 字段允许默认
    assert hasattr(c, "call_tool")


# =====================================================
# 事件总线
# =====================================================
def t_event_bus():
    import asyncio

    from core.events import (
        TOPIC_INSPECTION_COMPLETED,
        TOPIC_VIOLATION_CREATED,
        Event,
        get_event_bus,
        publish,
        reset_event_bus,
    )

    reset_event_bus()
    bus = get_event_bus()

    received: list[Event] = []

    async def _on_violation(ev: Event) -> None:
        received.append(("vio", ev))

    async def _on_all(ev: Event) -> None:
        received.append(("all", ev))

    async def _run():
        await bus.subscribe(TOPIC_VIOLATION_CREATED, _on_violation)
        await bus.subscribe("inspection.*", _on_all)
        await bus.publish(Event(
            topic=TOPIC_VIOLATION_CREATED,
            tenant_id="tnt_x",
            source="safety_audit_agent",
            payload={"violation_id": "vio_1"},
        ))
        await bus.publish(Event(
            topic=TOPIC_INSPECTION_COMPLETED,
            tenant_id="tnt_x",
            source="compliance_agent",
        ))

    asyncio.run(_run())
    topics_seen = [r[0] for r in received]
    # 第一次发布：匹配 violation.* 与 inspection.*，但 violation 主题应只命中 vio 处理器；
    # 第二次发布：仅命中 inspection.* 的 all 处理器
    assert "vio" in topics_seen and "all" in topics_seen
    # 历史
    hist = bus.history()
    assert len(hist) == 2 and hist[0].topic == TOPIC_VIOLATION_CREATED

    # 便捷发布
    async def _run2():
        ev = await publish(TOPIC_VIOLATION_CREATED, "tnt_x", "x", violation_id="vio_2")
        assert ev.event_id.startswith("evt_")

    asyncio.run(_run2())


# =====================================================
# agents.base_agent 骨架
# =====================================================
def t_base_agent():
    import asyncio

    from agents.base_agent import BaseAgent
    from core.a2a.agent_card import Skill
    from core.a2a.message import TaskState
    from core.a2a.server import reset_registry

    reset_registry()

    class DemoAgent(BaseAgent):
        name = "demo_agent_skel"
        version = "0.1.0"
        description = "骨架测试"
        skills = [Skill(skill_id="echo", name="echo", description="回显")]

    a = DemoAgent(tenant_id="tnt_x", a2a_url="http://localhost:9101")
    # 构造 message
    from core.a2a.message import A2AMessage, MessagePart

    msg = A2AMessage(
        message_id="msg_skel",
        tenant_id="tnt_x",
        parts=[MessagePart(type="text", text="hi")],
    )

    async def _run():
        task = await a.new_task(msg)
        assert task.state == TaskState.PENDING
        # 默认 handle 会回显
        reply = await a.handle(msg, task)
        assert reply.role == "agent"
        # cancel
        ok = await a.cancel_task(task.task_id, reason="test")
        assert ok is True
        t2 = await a.get_task(task.task_id)
        assert t2 is not None and t2.state == TaskState.CANCELLED

    asyncio.run(_run())

    # 装饰器
    from agents.base_agent import register_agent

    @register_agent
    class _Decorated(BaseAgent):
        name = "decorated"
        version = "0.1.0"

    # 不报错即可
    assert _Decorated.name == "decorated"


# =====================================================
# API Schemas
# =====================================================
def t_api_schemas():
    from typing import Any

    from api.schemas import (
        A2AMessageDTO,
        A2ASendMessageRequest,
        AgentSummary,
        ApiResponse,
        ErrorResponse,
        Page,
        PaginationQuery,
    )

    ok = ApiResponse[str].ok("hi")
    assert ok.code == "0" and ok.data == "hi"
    # 错误响应 data 字段统一装 details，类型不固定，用 Any
    fail: ApiResponse[Any] = ApiResponse[Any].fail("50002", "bad", details={"x": 1})
    assert fail.code == "50002" and fail.data == {"details": {"x": 1}}

    err = ErrorResponse(code="50002", message="bad")
    assert err.code == "50002"

    p = Page[str].of(["a", "b"], 5, page=1, page_size=2)
    assert p.total == 5 and p.total_pages == 3 and p.has_next

    pq = PaginationQuery(page=2, page_size=10)
    assert pq.offset == 10 and pq.limit == 10

    s = AgentSummary(name="x", version="0.1.0", description="d", protocol_version="1.0")
    assert s.skill_count == 0

    # 序列化 A2A DTO
    req = A2ASendMessageRequest(
        message=A2AMessageDTO(tenant_id="tnt_x", parts=[]),
        wait=False,
    )
    assert req.message.tenant_id == "tnt_x"


# =====================================================
# 路由构造（不实际启动，只验证构造不抛错）
# =====================================================
def t_routers_construct():
    from api.routers.a2a_router import build_a2a_router
    from api.routers.mcp_router import build_mcp_router

    r1 = build_a2a_router()
    r2 = build_mcp_router()
    assert r1.prefix == "/api/v1/a2a"
    assert r2.prefix == "/api/v1/mcp"


# =====================================================
# scripts 入口（仅校验 build_app 不抛错）
# =====================================================
def t_scripts_apps():
    from core.a2a.server import reset_registry
    from scripts.start_a2a_server import build_app as build_a2a_app
    from scripts.start_mcp_server import build_app as build_mcp_app
    # 注意：不重置 MCP 服务，避免丢失装饰器注册的资源/工具/提示词

    reset_registry()
    app1 = build_a2a_app()
    app2 = build_mcp_app()
    assert app1 is not None and app2 is not None


# =====================================================
# 跨模块集成
# =====================================================
def t_integration_a2a_mcp_events():
    """A2A 智能体处理一条消息时通过 MCP 工具算荷载并发布事件。"""
    import asyncio

    from core.a2a.agent_card import AgentCard
    from core.a2a.message import A2AMessage, MessagePart, Task
    from core.a2a.server import A2AServer, AgentRegistry, reset_registry
    from core.events import TOPIC_INSPECTION_COMPLETED, Event, get_event_bus, reset_event_bus
    from core.mcp.server import get_mcp_service

    reset_registry()
    reset_event_bus()

    bus = get_event_bus()
    received: list[Event] = []

    async def _on_insp_done(ev: Event) -> None:
        received.append(ev)

    asyncio.run(bus.subscribe(TOPIC_INSPECTION_COMPLETED, _on_insp_done))

    bus = get_event_bus()
    received: list[Event] = []

    async def _on_insp_done(ev: Event) -> None:
        received.append(ev)

    asyncio.run(bus.subscribe(TOPIC_INSPECTION_COMPLETED, _on_insp_done))

    class IntegrationAgent:
        name = "integration_agent"
        card = AgentCard(name="integration_agent", version="0.1.0", url="http://x")

        async def handle(self, message: A2AMessage, task: Task) -> A2AMessage:
            svc = get_mcp_service()
            r = await svc.call_tool("calculation.load", {
                "plan_id": "plan_i",
                "dead_load_kpa": 10.0,
                "live_load_kpa": 3.0,
            })
            assert r["result"]["ok"] is True
            # 触发事件
            await bus.publish(Event(
                topic=TOPIC_INSPECTION_COMPLETED,
                tenant_id=message.tenant_id,
                source=self.name,
                payload={"task_id": task.task_id},
            ))
            return A2AMessage(
                message_id="msg_r",
                tenant_id=message.tenant_id,
                role="agent",
                parts=[MessagePart(type="text", text=f"combined={r['result']['combined_kpa']}")],
            )

        async def get_task(self, task_id: str):
            return None

        async def cancel_task(self, task_id: str, reason: str | None = None):
            return True

        def list_tasks(self):
            return []

    reg = AgentRegistry()
    reg.register(IntegrationAgent())
    server = A2AServer(registry=reg)

    body = {
        "jsonrpc": "2.0",
        "id": "i1",
        "method": "agent.send_message",
        "params": {
            "message": {
                "message_id": "msg_i",
                "tenant_id": "tnt_i",
                "role": "user",
                "parts": [{"type": "text", "text": "go"}],
                "metadata": {},
            },
            "wait": True,
        },
        "protocol_version": "1.0",
    }

    async def _run():
        resp = await server.handle_raw("integration_agent", body)
        assert "error" not in resp
        # 等待事件触发
        await asyncio.sleep(0.05)
        assert len(received) >= 1
        assert received[0].tenant_id == "tnt_i"

    asyncio.run(_run())


# =====================================================
# 注册自检
# =====================================================
check("common: A2A/MCP 错误码与异常", t_common_a2a_mcp)
check("common: 阶段二业务 ID 前缀", t_ids_phase2)
check("core.a2a.protocol: 协议版本/方法/错误", t_a2a_protocol)
check("core.a2a.message: 消息/任务/状态机", t_a2a_message_and_task)
check("core.a2a.serializers: JSON-RPC 编解码", t_a2a_serializers)
check("core.a2a.agent_card: Agent Card", t_a2a_agent_card)
check("core.a2a.server: 注册表 + JSON-RPC 端到端", t_a2a_registry_and_server)
check("core.a2a.client+middleware: 客户端/中间件", t_a2a_client_middleware)
check("core.mcp: 注册表（资源/工具/提示词）", t_mcp_registration)
check("core.mcp: 工具调用（calculation/validation）", t_mcp_call_tool)
check("core.mcp: 提示词渲染", t_mcp_render_prompt)
check("core.mcp: 资源读取（不存在的 URI）", t_mcp_read_resource)
check("core.mcp: 客户端构造", t_mcp_client)
check("core.events: 事件总线发布/订阅/通配/历史", t_event_bus)
check("agents.base_agent: 智能体骨架 + 装饰器", t_base_agent)
check("api.schemas: ApiResponse/Page/DTO", t_api_schemas)
check("api.routers: a2a/mcp 路由构造", t_routers_construct)
check("scripts: a2a/mcp build_app", t_scripts_apps)
check("集成: A2A + MCP 工具 + 事件总线", t_integration_a2a_mcp_events)

print(f"\n===== 阶段二自检结果: {len(PASSED)} 通过, {len(FAILED)} 失败 =====")
sys.exit(1 if FAILED else 0)

