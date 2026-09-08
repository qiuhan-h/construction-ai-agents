"""施工安全审核智能体主类（SafetyAuditAgent）。

流程：
1) 解析 A2A message.parts 拿到 plan 文本 / drawing 路径 / hazards / loads；
2) 解析方案（plan_parser）→ 拿到 PlanFields；
3) 计算（load_calculator / risk_assessor / structural_analyzer）；
4) 检索（case_retriever）；
5) 整改建议（recommendation_engine）；
6) 生成报告（report_generator → Markdown + 结构化 ReviewReport）；
7) 签章（report_signer → HMAC-SHA256）；
8) 事件发布：
   - 任意 CRITICAL 风险 → TOPIC_ALERT_TRIGGERED
   - 报告签章完成 → TOPIC_REPORT_SIGNED
   - 审查完成 → TOPIC_INSPECTION_COMPLETED
9) 返回 A2A reply（text=总结 / file=Markdown / data=report_id+signature）。
"""

from __future__ import annotations

import logging
from typing import Any

from common.constants import AgentName, ReportStatus
from common.exceptions import AgentParseError
from common.ids import event_id, message_id
from common.timeutils import to_iso, utc_now
from core.a2a.agent_card import Skill
from core.a2a.message import A2AMessage, MessagePart, Task

# 注意：避免在 import 期触发 self.import 自引用
from agents.base_agent import BaseAgent, register_agent
from agents.safety_audit_agent.calculators import (
    HazardInput,
    LECAssessor,
    LoadCalculator,
    LoadInputs,
    LoadResult,
    RiskAssessment,
    RiskLevel,
    StructuralAnalyzer,
)
from agents.safety_audit_agent.knowledge_base import (
    CaseRetriever,
    StandardLoader,
)
from agents.safety_audit_agent.parsers import PlanParser
from agents.safety_audit_agent.outputs import (
    RecommendationEngine,
    ReportArtifacts,
    ReportGenerator,
    sign_report_content,
)
from agents.safety_audit_agent.prompts import (
    PROMPT_PLAN_REVIEW,
    PROMPT_REPORT_DRAFT,
    list_prompts as _list_safety_prompts,
)

logger = logging.getLogger("agents.safety_audit_agent")


@register_agent
class SafetyAuditAgent(BaseAgent):
    """施工安全审核智能体。"""

    name = AgentName.SAFETY_AUDIT.value
    version = "0.1.0"
    description = "施工方案/图纸/规范审查，输出结构化报告与整改建议"
    skills = [
        Skill(
            skill_id="plan_review",
            name="方案审查",
            description="解析施工方案文本并执行 LEC 风险评估，输出审查报告",
        ),
        Skill(
            skill_id="load_combination",
            name="荷载组合",
            description="按 GB 50009 计算 1.2D+1.4L+0.6W+0.7S 荷载组合",
        ),
    ]

    def __init__(
        self,
        *,
        tenant_id: str,
        a2a_url: str = "http://localhost:9101",
        card_path: str = "/agent.json",
        metadata: dict[str, Any] | None = None,
        signer_secret: str | None = None,
        auto_register: bool = True,
    ) -> None:
        super().__init__(
            tenant_id=tenant_id,
            a2a_url=a2a_url,
            card_path=card_path,
            metadata=metadata,
        )
        self._plan_parser = PlanParser()
        self._load_calc = LoadCalculator()
        self._risk = LECAssessor()
        self._struct = StructuralAnalyzer()
        self._cases = CaseRetriever()
        self._stds = StandardLoader()
        self._rec_eng = RecommendationEngine()
        self._report_gen = ReportGenerator(agent=AgentName.SAFETY_AUDIT)
        self._signer_secret = signer_secret
        # 提示词模板触发注册
        _ = _list_safety_prompts()
        if auto_register:
            self.register()

    # =====================================================
    # A2A handle 主流程
    # =====================================================
    async def handle(self, message: A2AMessage, task: Task) -> A2AMessage:
        """处理一条 A2A 消息并返回审查结果。"""
        try:
            payload = self._extract_payload(message)
            artifacts = await self._run_review(payload)
            return self._build_reply(artifacts, message)
        except AgentParseError as e:
            logger.warning("解析失败: %s", e)
            return self._error_reply(message, str(e))
        except Exception as e:  # noqa: BLE001
            logger.exception("智能体执行失败: %s", e)
            return self._error_reply(message, f"internal error: {e!s}")

    # =====================================================
    # 内部：解析 + 计算 + 生成
    # =====================================================
    def _extract_payload(self, message: A2AMessage) -> dict[str, Any]:
        """从 A2AMessage 提取业务字段。

        期望 message.metadata 至少包含：
            project_id: str
            plan_id: str
            （可选）plan_text / drawing_meta / hazards / loads
        """
        md = dict(message.metadata or {})
        plan_text = None
        for p in message.parts:
            if p.type == "text" and p.text:
                plan_text = (plan_text or "") + p.text
            elif p.type == "data" and p.data:
                # 业务字段直接放在 data
                md.update(p.data)
        if not plan_text and "plan_text" in md:
            plan_text = md["plan_text"]
        project_id = md.get("project_id")
        plan_id = md.get("plan_id")
        if not project_id or not plan_id:
            raise AgentParseError(
                "message.metadata 必须包含 project_id 与 plan_id",
                details={"metadata_keys": list(md.keys())},
            )
        return {
            "project_id": str(project_id),
            "plan_id": str(plan_id),
            "plan_text": plan_text or "",
            "hazards": md.get("hazards") or [],
            "loads": md.get("loads") or {},
            "drawing_meta": md.get("drawing_meta"),
            "regulation_codes": md.get("regulation_codes") or [],
        }

    async def _run_review(self, payload: dict[str, Any]) -> ReportArtifacts:
        tenant_id = self.tenant_id
        project_id = payload["project_id"]
        plan_id = payload["plan_id"]
        plan_text = payload["plan_text"]

        # 1) 解析方案
        plan_fields = self._plan_parser.parse_text(plan_text)
        if payload.get("hazards"):
            # 合并外部 hazards
            existing = {h["name"] for h in plan_fields.hazards}
            for h in payload["hazards"]:
                name = h.get("name")
                if name and name not in existing:
                    plan_fields.hazards.append({"name": name, "source": "a2a_metadata"})
                    existing.add(name)
        if payload.get("loads"):
            # 单条 load 转换失败不应导致整个 plan 解析崩溃：逐项隔离
            for k, v in payload["loads"].items():
                try:
                    plan_fields.loads[k] = float(v)
                except (TypeError, ValueError) as e:
                    logger.warning(
                        "跳过非法 load 项 %s=%r，原因: %s", k, v, e
                    )

        # 2) 荷载组合
        load_result: LoadResult | None = None
        if plan_fields.loads:
            load_result = await self._load_calc.combined_load(
                LoadInputs(
                    plan_id=plan_id,
                    dead_load_kpa=plan_fields.loads.get("dead", 0.0),
                    live_load_kpa=plan_fields.loads.get("live", 0.0),
                    wind_pressure_kpa=plan_fields.loads.get("wind", 0.45),
                    snow_pressure_kpa=plan_fields.loads.get("snow", 0.30),
                )
            )

        # 3) 风险评估
        hazard_inputs: list[HazardInput] = []
        for h in plan_fields.hazards:
            name = h["name"]
            # 默认 LEC 取中间档；后续可由 a2a 消息覆盖
            likelihood = float(h.get("likelihood", 1.0))
            exposure = float(h.get("exposure", 2.0))
            consequence = float(h.get("consequence", 7.0))
            hazard_inputs.append(
                HazardInput(
                    name=name,
                    likelihood=likelihood,
                    exposure=exposure,
                    consequence=consequence,
                    note=h.get("source"),
                )
            )
        risk: RiskAssessment | None = None
        if hazard_inputs:
            risk = await self._risk.assess(hazard_inputs)

        # 4) 案例检索
        query = " ".join(
            [plan_fields.project_name or "", plan_fields.stage or ""]
            + [h["name"] for h in plan_fields.hazards]
        )
        related_cases = await self._cases.search_cases(tenant_id, query, top_k=3)

        # 5) 法规/标准（首版硬编码：JGJ 80-2011 安全检查标准 + GB 50009-2012）
        related_regs: list[dict[str, Any]] = [
            {"code": "JGJ80", "version": "2011", "name": "建筑施工高处作业安全技术规范"},
            {"code": "GB50009", "version": "2012", "name": "建筑结构荷载规范"},
        ]
        # 6) 整改建议
        rec_set = self._rec_eng.from_risk(risk) if risk else self._rec_eng.from_risk(
            RiskAssessment(
                items=[],
                max_score=0.0,
                # max_level 类型为 RiskLevel（非 Optional）；此处处于 risk 为空的
                # else 分支，原写法 risk.max_level if risk else None 会传 None 违反注解，
                # 改用 NEGLIGIBLE 作为安全默认值（与 LECAssessor 空载默认一致）。
                max_level=RiskLevel.NEGLIGIBLE,
                requires_alert=False,
            )
        )

        # 7) 生成报告
        artifacts = self._report_gen.generate(
            tenant_id=tenant_id,
            project_id=project_id,
            plan_id=plan_id,
            plan_fields=plan_fields,
            load_result=load_result,
            risk_assessment=risk,
            related_cases=related_cases,
            related_regulations=related_regs,
            recommendations=rec_set,
        )

        # 8) 签章（不抛错；失败仅记日志）
        try:
            sign_info = sign_report_content(
                artifacts.report.content,
                tenant_id,
                secret=self._signer_secret,
            )
            # 在结构化报告上记录签名（保持 ReviewReport 不变；签名通过 reply 透传）
            artifacts.report.signature = sign_info.signature
            artifacts.report.status = ReportStatus.SIGNED
            await self._publish_event_safe(
                "report.signed",
                {
                    "report_id": artifacts.report.id,
                    "sha256": sign_info.sha256,
                    "signature": sign_info.signature,
                },
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("报告签章失败（不影响主流程）: %s", e)

        # 9) 告警（CRITICAL）
        if risk and risk.requires_alert:
            await self._publish_event_safe(
                "alert.triggered",
                {
                    "report_id": artifacts.report.id,
                    "max_score": risk.max_score,
                    "max_level": risk.max_level.value,
                    "hazard_count": len(risk.items),
                },
            )

        # 10) 审查完成事件
        await self._publish_event_safe(
            "inspection.completed",
            {
                "report_id": artifacts.report.id,
                "inspection_id": artifacts.inspection.id,
                "conclusion": artifacts.report.conclusion.value,
            },
        )
        return artifacts

    # =====================================================
    # 内部：构建 A2A 回复
    # =====================================================
    def _build_reply(
        self, artifacts: ReportArtifacts, src: A2AMessage
    ) -> A2AMessage:
        rpt = artifacts.report
        summary = (
            f"审查完成：{rpt.title}；结论={rpt.conclusion.value}；"
            f"report_id={rpt.id}"
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
                        "signature": rpt.signature,
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
            parts=[MessagePart(type="text", text=f"审查失败：{reason}")],
            metadata={"error": reason, "received_at": to_iso(utc_now())},
        )

    # =====================================================
    # 内部：发布事件（失败不影响主流程）
    # =====================================================
    async def _publish_event_safe(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            from core.events import Event, get_event_bus

            bus = get_event_bus()
            await bus.publish(
                Event(
                    topic=topic,
                    tenant_id=self.tenant_id,
                    source=self.name,
                    payload=payload,
                )
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("事件发布失败 topic=%s err=%s", topic, e)


# =====================================================
# 便捷构造
# =====================================================
def make_safety_audit_agent(
    tenant_id: str,
    *,
    a2a_url: str = "http://localhost:9101",
    signer_secret: str | None = None,
) -> SafetyAuditAgent:
    return SafetyAuditAgent(
        tenant_id=tenant_id,
        a2a_url=a2a_url,
        signer_secret=signer_secret,
    )


__all__ = [
    "SafetyAuditAgent",
    "make_safety_audit_agent",
    "PROMPT_PLAN_REVIEW",
    "PROMPT_REPORT_DRAFT",
]
