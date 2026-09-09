"""施工合规校验智能体主类（ComplianceAgent）。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agents.base_agent import BaseAgent, register_agent
from agents.compliance_agent.checkers import (
    EnergyChecker,
    FireChecker,
    GreenChecker,
    SeismicChecker,
)
from agents.compliance_agent.outputs import (
    ComplianceReporter,
    ReportArtifacts,
    ViolationRepository,
    ViolationTracker,
)
from agents.compliance_agent.prompts import list_prompts as _list_compliance_prompts
from agents.compliance_agent.regulation_engine import (
    RegulationIndex,
    RegulationLoader,
    VersionManager,
)
from agents.compliance_agent.validators import DocumentValidator, DrawingValidator
from agents.safety_audit_agent.outputs.report_signer import sign_report_content
from common.constants import AgentName
from common.exceptions import AgentParseError, AppException
from common.ids import message_id
from common.timeutils import to_iso, utc_now
from core.a2a.agent_card import Skill
from core.a2a.message import A2AMessage, MessagePart, Task
from core.events import Event, get_event_bus

logger = logging.getLogger("agents.compliance_agent")


@register_agent
class ComplianceAgent(BaseAgent):
    """施工合规校验智能体。"""

    name = AgentName.COMPLIANCE.value
    version = "0.1.0"
    description = "设计文件合规校验（消防/抗震/节能/绿色建筑）"
    skills = [
        Skill(skill_id="fire_check", name="防火合规核查", description="依据 GB 50016 检查设计文件"),
        Skill(skill_id="seismic_check", name="抗震合规核查", description="依据 GB 50011 校验抗震设防"),
        Skill(skill_id="energy_check", name="节能合规核查", description="依据 GB 50189 检查节能设计"),
        Skill(skill_id="green_check", name="绿色建筑核查", description="依据 GB/T 50378 评估绿建指标"),
    ]

    def __init__(
        self,
        *,
        tenant_id: str,
        a2a_url: str = "http://localhost:9101",
        card_path: str = "/agent.json",
        metadata: dict[str, Any] | None = None,
        signer_secret: str | None = None,
        session_factory: Any | None = None,
        auto_register: bool = True,
    ) -> None:
        super().__init__(
            tenant_id=tenant_id, a2a_url=a2a_url,
            card_path=card_path, metadata=metadata,
        )
        # 法规引擎
        self._loader = RegulationLoader()
        self._loader.bootstrap()
        self._index = RegulationIndex(self._loader)
        self._version_mgr = VersionManager(tenant_id, self._loader)
        # 4 类检查器（鸭子类型：均暴露 design_type 属性与 async check 方法）
        self._checkers: list[Any] = [
            FireChecker(), SeismicChecker(),
            EnergyChecker(), GreenChecker(),
        ]
        # 校验器
        self._drawing_val = DrawingValidator()
        self._doc_val = DocumentValidator()
        # 输出
        repo = ViolationRepository(session_factory=session_factory)
        self._tracker = ViolationTracker(tenant_id, repo)
        self._reporter = ComplianceReporter()
        self._signer_secret = signer_secret
        # 提示词触发注册
        _ = _list_compliance_prompts()
        if auto_register:
            self.register()

    # =========================================================
    # A2A handle 主流程
    # =========================================================
    async def handle(self, message: A2AMessage, task: Task) -> A2AMessage:
        try:
            payload = self._extract_payload(message)
            artifacts = await self._run_compliance(payload)
            return self._build_reply(artifacts, message)
        except AgentParseError as e:
            logger.warning("解析失败: %s", e)
            return self._error_reply(message, str(e))
        except AppException as e:
            logger.warning("AppException: %s", e)
            return self._error_reply(message, f"{e.code}: {e.message}")
        except Exception as e:
            logger.exception("compliance_agent 执行失败: %s", e)
            return self._error_reply(message, f"internal error: {e!s}")

    # =========================================================
    # 内部：payload 解析
    # =========================================================
    def _extract_payload(self, message: A2AMessage) -> dict[str, Any]:
        md = dict(message.metadata or {})
        design_doc: dict[str, Any] = {}
        for p in message.parts:
            if p.type == "text" and p.text:
                # 文本部分作为 design_doc 整体（也可被 metadata 覆盖）
                design_doc.setdefault("_text", "")
                design_doc["_text"] = (design_doc["_text"] or "") + p.text
            elif p.type == "data" and p.data:
                md.update(p.data)
        # 合并 data.parts / metadata 中的 design_doc
        # 注意：当文本部分已写入 design_doc（_text）时，不能直接丢弃 data.design_doc，
        # 需把 data.design_doc 的字段并入；文本部分已有的字段优先（setdefault 避免覆盖）。
        if "design_doc" in md:
            dd = md.pop("design_doc")
            if isinstance(dd, dict):
                for k, v in dd.items():
                    design_doc.setdefault(k, v)
        # 抽 project_id / plan_id 顶层字段
        project_id = md.pop("project_id", None)
        plan_id = md.pop("plan_id", None)
        # drawings / document 合并到 design_doc
        for k in ("drawings", "document"):
            v = md.pop(k, None)
            if v is not None:
                design_doc[k] = v
        if not project_id or not plan_id:
            raise AgentParseError(
                "message.metadata 必须包含 project_id 与 plan_id",
                details={"metadata_keys": list(md.keys())},
            )
        return {
            "project_id": str(project_id),
            "plan_id": str(plan_id),
            "design_doc": design_doc,
            "drawings": md.get("drawings") or design_doc.get("drawings"),
            "document": md.get("document") or design_doc.get("document"),
            "checks": {
                "fire": md.get("fire_check", True),
                "seismic": md.get("seismic_check", True),
                "energy": md.get("energy_check", True),
                "green": md.get("green_check", True),
            },
        }

    # =========================================================
    # 内部：合规审查主流程
    # =========================================================
    async def _run_compliance(self, payload: dict[str, Any]) -> ReportArtifacts:
        tenant_id = self.tenant_id
        project_id = payload["project_id"]
        plan_id = payload["plan_id"]
        design_doc = payload["design_doc"]
        checks = payload["checks"]

        # 1) 收集所有适用法规（去重）
        regs_by_type: dict[str, list] = {}
        for ct in ("fire", "seismic", "energy", "green"):
            if not checks.get(ct):
                continue
            regs_by_type[ct] = self._index.search(ct)
        # 合并去重
        seen: dict[str, Any] = {}
        for _ct, regs in regs_by_type.items():
            for r in regs:
                key = f"{r.code}/{r.version}"
                if key not in seen:
                    seen[key] = r
        all_regs = list(seen.values())

        # 2) 4 类 checker 并行（只跑启用的）
        active_checkers = []
        for c in self._checkers:
            if checks.get(c.design_type):
                active_checkers.append(c)
        results = await asyncio.gather(
            *(c.check(design_doc, all_regs, tenant_id=tenant_id)
              for c in active_checkers),
            return_exceptions=False,
        )
        violations: list[Any] = []
        for vs in results:
            violations.extend(vs)  # type: ignore[arg-type]  # gather(return_exceptions=False) 不含异常

        # 3) 校验器（图纸 + 文档）
        # 兼容 drawings 为单张(dict)/多张(list)/非法类型的情况，统一规整成 list[dict]，
        # 跳过非 dict 元素，避免 _check_title_block 对非 dict 调用 .get 触发 AttributeError。
        if payload.get("drawings"):
            raw_drawings = payload["drawings"]
            drawings_list = (
                raw_drawings if isinstance(raw_drawings, list) else [raw_drawings]
            )
            for d in drawings_list:
                if isinstance(d, dict):
                    violations.extend(
                        await self._drawing_val.validate(d, tenant_id=tenant_id)
                    )
        if payload.get("document"):
            violations.extend(
                await self._doc_val.validate(payload["document"], tenant_id=tenant_id)
            )

        # 4) 报告生成
        artifacts = self._reporter.generate(
            tenant_id=tenant_id,
            project_id=project_id,
            plan_id=plan_id,
            design_doc=design_doc,
            violations=violations,
            regulations=all_regs,
        )

        # 5) 落库 + 事件发布
        await self._tracker.record(violations, artifacts.inspection.id)

        # 6) 签章（不阻塞主流程）
        try:
            sign_info = sign_report_content(
                artifacts.report.content, tenant_id, secret=self._signer_secret,
            )
            artifacts.report.signature = sign_info.signature
            artifacts.report.status = type(artifacts.report.status).__members__.get(
                "SIGNED"
            ) or artifacts.report.status
        except Exception as e:  # noqa: BLE001
            logger.warning("合规报告签章失败: %s", e)

        # 7) 发布 inspection.completed 事件
        await self._publish_event_safe(
            "inspection.completed",
            {
                "inspection_id": artifacts.inspection.id,
                "report_id": artifacts.report.id,
                "conclusion": artifacts.report.conclusion.value,
                "violation_count": len(violations),
            },
        )
        return artifacts

    # =========================================================
    # 内部：构造 A2A reply
    # =========================================================
    def _build_reply(
        self, artifacts: ReportArtifacts, src: A2AMessage,
    ) -> A2AMessage:
        rpt = artifacts.report
        summary = (
            f"合规审查完成：{rpt.title}；结论={rpt.conclusion.value}；"
            f"违规项={len(artifacts.violations)}；report_id={rpt.id}"
        )
        return A2AMessage(
            message_id=message_id(),
            tenant_id=src.tenant_id,
            role="agent",
            parts=[
                MessagePart(type="text", text=summary),
                MessagePart(
                    type="file",
                    file_uri=f"report://{rpt.id}",
                    data={
                        "report_id": rpt.id,
                        "title": rpt.title,
                        "conclusion": rpt.conclusion.value,
                    },
                ),
                MessagePart(
                    type="data",
                    data={
                        "report": rpt.model_dump(),
                        "inspection_id": artifacts.inspection.id,
                        "violation_count": len(artifacts.violations),
                        "regulation_versions": artifacts.regulation_versions,
                    },
                ),
            ],
            metadata={
                "report_id": rpt.id,
                "conclusion": rpt.conclusion.value,
                "received_at": to_iso(utc_now()),
            },
        )

    def _error_reply(self, src: A2AMessage, reason: str) -> A2AMessage:
        return A2AMessage(
            message_id=message_id(),
            tenant_id=src.tenant_id,
            role="agent",
            parts=[MessagePart(type="text", text=f"合规审查失败：{reason}")],
            metadata={"error": reason, "received_at": to_iso(utc_now())},
        )

    # =========================================================
    # 内部：发布事件（失败不影响主流程）
    # =========================================================
    async def _publish_event_safe(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            await get_event_bus().publish(
                Event(
                    topic=topic,
                    tenant_id=self.tenant_id,
                    source=self.name,
                    payload=payload,
                )
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("事件发布失败 topic=%s err=%s", topic, e)


# =========================================================
# 便捷构造
# =========================================================
def make_compliance_agent(
    tenant_id: str,
    *,
    a2a_url: str = "http://localhost:9101",
    signer_secret: str | None = None,
    session_factory: Any | None = None,
) -> ComplianceAgent:
    return ComplianceAgent(
        tenant_id=tenant_id, a2a_url=a2a_url,
        signer_secret=signer_secret, session_factory=session_factory,
    )


__all__ = [
    "ComplianceAgent",
    "make_compliance_agent",
]
