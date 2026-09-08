"""阶段一（地基）代码自检：导入 common / models / core.llm 并做基础行为验证。"""

import sys
import traceback
from pathlib import Path

# 跨平台：自动定位 construction-ai-agents 根目录（与脚本同级的子目录）
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


def t_common():
    from common import AgentName, new_id
    from common.constants import InspectionStatus
    from common.error_codes import ErrorCodes

    assert AgentName.SAFETY_AUDIT.value == "safety_audit_agent"
    assert not AgentName.ORCHESTRATOR.is_business
    assert ErrorCodes.LLM_TIMEOUT.code == "40002" and ErrorCodes.LLM_TIMEOUT.http_status == 504
    assert InspectionStatus.PENDING.value == "pending"
    assert new_id("tnt")[:4] == "tnt_"
    t = tenant_id_check()
    assert t.startswith("tnt_") and len(t) == 4 + 26


def tenant_id_check():
    from common.ids import tenant_id

    return tenant_id()


def t_timeutils():
    from datetime import datetime

    from common import utc_now

    now = utc_now()
    assert now.tzinfo is not None, "utc_now 必须返回感知时间"


def t_exceptions():
    from common import LLMTimeoutError

    exc = LLMTimeoutError("boom")
    d = exc.to_dict()
    assert d["code"] == exc.code and d["message"] == "boom"
    assert exc.http_status in (408, 504, 500)


def t_domain():
    from common.constants import AgentName, AuditConclusion, InspectionStatus
    from models.domain import (
        Alert,
        GeoPoint,
        Inspection,
        Project,
        ReviewReport,
        Tenant,
        Violation,
    )

    t = Tenant(name="某建设集团", code="T-001")
    assert t.id.startswith("tnt_")
    p = Project(tenant_id=t.id, name="示范工程", code="P-001")
    assert p.id.startswith("prj_")
    insp = Inspection(tenant_id=t.id, project_id=p.id, agent=AgentName.SAFETY_AUDIT)
    assert insp.status == InspectionStatus.PENDING.value
    v = Violation(
        tenant_id=t.id,
        inspection_id=insp.id,
        regulation_id="JGJ59",
        regulation_version="2011",
        description="临边防护缺失",
    )
    assert v.regulation_version == "2011"
    a = Alert(
        tenant_id=t.id,
        project_id=p.id,
        source="iot",
        title="塔吊力矩超限",
        location=GeoPoint(longitude=120.0, latitude=30.0),
    )
    assert a.level and a.status
    r = ReviewReport(
        tenant_id=t.id,
        project_id=p.id,
        inspection_id=insp.id,
        agent=AgentName.COMPLIANCE,
        title="审核报告",
        content="# 报告正文",
        conclusion=AuditConclusion.PASS,
        regulation_versions={"JGJ59": "2011"},
    )
    assert r.regulation_versions == {"JGJ59": "2011"}


def t_database():
    from models.database import Base
    from models.database.base import enum_column
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    tables = Base.metadata.tables
    expected = {
        "tenants", "projects", "construction_plans",
        "inspections", "violations", "review_reports",
        "alerts", "sensor_devices",
    }
    missing = expected - set(tables)
    assert not missing, f"缺少表: {missing}"

    # 建表到内存 SQLite 验证 DDL 可执行
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        from models.database import TenantTable
        s.add(TenantTable(name="自检租户", code="selftest"))
        s.commit()
        row = s.query(TenantTable).first()
        assert row is not None and row.status

    # enum_column 校验
    from common.constants import ProjectStatus

    col = enum_column(ProjectStatus)
    assert col.native_enum is False or not col.native_enum


def t_vector():
    from models.vector import CaseVector, DocumentVector
    from common.constants import DocType

    dv = DocumentVector(tenant_id="tnt_x", doc_id="reg-1", doc_type=DocType.REGULATION, title="安规", content="条文", version="2024")
    assert dv.id.startswith("docv_")
    cv = CaseVector(case_id="c-1", case_type="坍塌", title="事故", summary="摘要")
    assert cv.id.startswith("casev_")


def t_llm_config():
    from pydantic import SecretStr

    from common.exceptions import LLMNotConfiguredError
    from core.llm import get_llm_model_config

    # 未配置密钥时应显式失败（Settings 默认 llm_api_key 为空串）
    try:
        cfg = get_llm_model_config()
    except LLMNotConfiguredError:
        return
    # 若环境已配置密钥，则校验配置结构
    assert cfg.model and cfg.base_url and cfg.timeout > 0


def t_llm_parse():
    from core.llm import OpenAICompatibleProvider
    from core.llm.config import LLMModelConfig
    from common.exceptions import LLMResponseInvalidError
    from pydantic import SecretStr

    provider = OpenAICompatibleProvider(
        LLMModelConfig("m", "http://x", SecretStr("k"), 5.0, 0, 0.2, 2048)
    )
    resp = provider._parse_response(
        {"choices": [{"message": {"content": "你好"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}}
    )
    assert resp.content == "你好" and resp.usage.total_tokens == 3
    try:
        provider._parse_response({"bad": 1})
        raise AssertionError("应抛 LLMResponseInvalidError")
    except LLMResponseInvalidError:
        pass


def t_prompt():
    from common.exceptions import ValidationError
    from core.llm import PromptTemplate, get_prompt_manager

    pm = get_prompt_manager()
    assert "system.construction_expert" in pm.list_names()
    out = pm.render("system.construction_expert", task_name="方案审核")
    assert "方案审核" in out and "{" not in out
    try:
        pm.render("system.construction_expert")
        raise AssertionError("缺少变量应抛错")
    except ValidationError:
        pass
    pm.register(PromptTemplate(name="t1", text="hello {a}"), overwrite=True)
    assert pm.render("t1", a="x") == "hello x"


def t_tracker():
    from core.llm import TokenTracker

    tk = TokenTracker()
    tk.register_pricing("test-model", 0.001, 0.002)
    cost = tk.record("test-model", 1000, 500, caller="safety_audit_agent")
    total = tk.total(caller="safety_audit_agent")
    assert total["calls"] == 1.0 and total["total_tokens"] == 1500.0
    assert cost > 0
    tk.reset()
    assert tk.total()["calls"] == 0.0


check("common: 枚举/错误码/ID 前缀", t_common)
check("common: utc_now 感知时间", t_timeutils)
check("common: 异常 to_dict", t_exceptions)
check("models.domain: 7 个领域模型", t_domain)
check("models.database: 8 表 DDL（SQLite 内存）", t_database)
check("models.vector: 向量模型", t_vector)
check("core.llm: 未配密钥显式失败 / 配置结构", t_llm_config)
check("core.llm: 响应解析与异常映射", t_llm_parse)
check("core.llm: 提示词注册/渲染/校验", t_prompt)
check("core.llm: token 统计", t_tracker)

print(f"\n===== 自检结果: {len(PASSED)} 通过, {len(FAILED)} 失败 =====")
sys.exit(1 if FAILED else 0)

