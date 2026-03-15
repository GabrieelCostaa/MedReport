"""
API do Assistente Multi-Agente de Relatórios OPME.
Pipeline: Pesquisador (A) -> Redator (B) -> Auditor (C).
"""
from uuid import UUID
from typing import Optional
from datetime import datetime

import asyncio
import json as json_mod

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models import Product, Report, ReportTemplate
from app.core.security import get_current_user_id
from app.services.agents.pipeline import ReportPipeline
from app.services.agents.checklist import ReportChecklist
from app.services.pdf_generator import generate_pdf_bytes

router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class StartReportIn(BaseModel):
    product_id: str
    paciente_nome: str
    cid: str
    diagnostico: str
    surgery_description: Optional[str] = None
    health_plan: Optional[str] = None
    especialidade: Optional[str] = None


class AnswerIn(BaseModel):
    session_id: str
    answers: dict  # {"falha_terapeutica": "Opção selecionada", ...}


class RegenerateIn(BaseModel):
    session_id: str
    report_id: Optional[str] = None
    adjustments: dict  # Campos a ajustar


class ChatIn(BaseModel):
    message: str


class ChatOut(BaseModel):
    reply: str
    report_id: str | None = None


# ============================================================================
# PubMed Evidences Preview
# ============================================================================

@router.get("/evidences-preview")
async def evidences_preview(
    cid: str,
    product_name: str = "",
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Preview de evidências disponíveis para um CID (internas + PubMed)."""
    if False:  # TODO: re-enable auth
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not cid or len(cid.strip()) < 3:
        return {"cid": cid, "internal_count": 0, "pubmed_count": 0, "total_count": 0, "preview": []}

    from app.services.pubmed_service import get_evidences_preview
    return await get_evidences_preview(db, cid, product_name)


# ============================================================================
# Pipeline Multi-Agente
# ============================================================================

@router.post("/start-report")
async def start_report(
    body: StartReportIn,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Inicia sessão do pipeline multi-agente.
    1. Busca produto e template
    2. Executa Agente A (Pesquisador)
    3. Retorna perguntas A/B/C se houver lacunas, ou gera direto
    """
    if False:  # TODO: re-enable auth
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.execute(
        select(Product).where(Product.id == UUID(body.product_id))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    template_result = await db.execute(
        select(ReportTemplate).where(ReportTemplate.produto_id == product.id).limit(1)
    )
    template = template_result.scalar_one_or_none()

    medico_inputs = {
        "paciente_nome": body.paciente_nome,
        "cid": body.cid,
        "diagnostico": body.diagnostico,
        "surgery_description": body.surgery_description or "",
        "health_plan": body.health_plan or "",
        "especialidade": body.especialidade or "",
    }

    pipeline_result = await ReportPipeline.start(
        product=product,
        template=template,
        diagnostico=body.diagnostico,
        cid=body.cid,
        medico_inputs=medico_inputs,
        db=db,
    )

    if pipeline_result.get("step") == "done":
        report = await _save_report(db, user_id, product, body, pipeline_result)
        pipeline_result["report_id"] = str(report.id)

    return pipeline_result


@router.post("/start-report-stream")
async def start_report_stream(
    body: StartReportIn,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    SSE: Inicia pipeline com eventos de progresso em tempo real.
    Retorna Server-Sent Events com cada etapa do pipeline.
    """
    if False:  # TODO: re-enable auth
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.execute(
        select(Product).where(Product.id == UUID(body.product_id))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    template_result = await db.execute(
        select(ReportTemplate).where(ReportTemplate.produto_id == product.id).limit(1)
    )
    template = template_result.scalar_one_or_none()

    medico_inputs = {
        "paciente_nome": body.paciente_nome,
        "cid": body.cid,
        "diagnostico": body.diagnostico,
        "surgery_description": body.surgery_description or "",
        "health_plan": body.health_plan or "",
        "especialidade": body.especialidade or "",
    }

    async def event_stream():
        progress_queue: asyncio.Queue = asyncio.Queue()

        async def on_progress(step: str, message: str):
            await progress_queue.put({"event": "step", "step": step, "message": message})

        async def run_pipeline():
            pipeline_result = await ReportPipeline.start(
                product=product,
                template=template,
                diagnostico=body.diagnostico,
                cid=body.cid,
                medico_inputs=medico_inputs,
                db=db,
                on_progress=on_progress,
            )
            if pipeline_result.get("step") == "done":
                report = await _save_report(db, user_id, product, body, pipeline_result)
                pipeline_result["report_id"] = str(report.id)
            await progress_queue.put({"event": "done", "data": pipeline_result})

        task = asyncio.create_task(run_pipeline())

        while True:
            msg = await progress_queue.get()
            event_type = msg.pop("event", "step")
            if event_type == "done":
                yield f"event: done\ndata: {json_mod.dumps(msg.get('data', {}))}\n\n"
                break
            else:
                yield f"event: step\ndata: {json_mod.dumps(msg)}\n\n"

        await task

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/answer")
async def answer_questions(
    body: AnswerIn,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Recebe respostas A/B/C do médico e avança o pipeline.
    """
    if False:  # TODO: re-enable auth
        raise HTTPException(status_code=401, detail="Not authenticated")

    pipeline_result = await ReportPipeline.answer(body.session_id, body.answers)

    if pipeline_result.get("error"):
        raise HTTPException(status_code=404, detail=pipeline_result["error"])

    if pipeline_result.get("step") == "done":
        session = ReportPipeline.get_session(body.session_id)
        report = await _save_report_from_session(db, user_id, session, pipeline_result)
        pipeline_result["report_id"] = str(report.id)

    return pipeline_result


@router.post("/answer-stream")
async def answer_stream(
    body: AnswerIn,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    SSE: Recebe respostas A/B/C e avança pipeline com eventos de progresso.
    """
    if False:  # TODO: re-enable auth
        raise HTTPException(status_code=401, detail="Not authenticated")

    async def event_stream():
        progress_queue: asyncio.Queue = asyncio.Queue()

        async def on_progress(step: str, message: str):
            await progress_queue.put({"event": "step", "step": step, "message": message})

        async def run_pipeline():
            pipeline_result = await ReportPipeline.answer(
                body.session_id, body.answers, on_progress=on_progress,
            )
            if pipeline_result.get("error"):
                await progress_queue.put({"event": "error", "data": pipeline_result})
                return
            if pipeline_result.get("step") == "done":
                session = ReportPipeline.get_session(body.session_id)
                if session:
                    report = await _save_report_from_session(db, user_id, session, pipeline_result)
                    pipeline_result["report_id"] = str(report.id)
            await progress_queue.put({"event": "done", "data": pipeline_result})

        task = asyncio.create_task(run_pipeline())

        while True:
            msg = await progress_queue.get()
            event_type = msg.pop("event", "step")
            if event_type == "done":
                yield f"event: done\ndata: {json_mod.dumps(msg.get('data', {}))}\n\n"
                break
            elif event_type == "error":
                yield f"event: error\ndata: {json_mod.dumps(msg.get('data', {}))}\n\n"
                break
            else:
                yield f"event: step\ndata: {json_mod.dumps(msg)}\n\n"

        await task

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class GenerateIn(BaseModel):
    product_id: str
    paciente_nome: str
    cid: str
    diagnostico: str
    surgery_description: Optional[str] = None
    health_plan: Optional[str] = None
    especialidade: Optional[str] = None
    report_id: Optional[str] = None
    strict_mode: bool = True
    use_search: bool = True


@router.post("/generate")
async def generate_full(
    body: GenerateIn,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Executa pipeline completo (A -> B -> C -> Validador).
    strict_mode=true bloqueia PDF se validação hard-coded falhar.
    """
    if False:  # TODO: re-enable auth
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.execute(
        select(Product).where(Product.id == UUID(body.product_id))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    template_result = await db.execute(
        select(ReportTemplate).where(ReportTemplate.produto_id == product.id).limit(1)
    )
    template = template_result.scalar_one_or_none()

    medico_inputs = {
        "paciente_nome": body.paciente_nome,
        "cid": body.cid,
        "diagnostico": body.diagnostico,
        "surgery_description": body.surgery_description or "",
        "health_plan": body.health_plan or "",
        "especialidade": body.especialidade or "",
    }

    pipeline_result = await ReportPipeline.start(
        product=product,
        template=template,
        diagnostico=body.diagnostico,
        cid=body.cid,
        medico_inputs=medico_inputs,
        db=db,
    )

    if pipeline_result.get("step") == "done":
        audit_summary = pipeline_result.get("audit_summary", {})
        hard_val = audit_summary.get("hard_validation", {})
        if body.strict_mode and not hard_val.get("passed", True):
            pipeline_result["pdf_blocked"] = True
            pipeline_result["pdf_blocked_reason"] = "Validação hard-coded detectou discrepância técnica"

        if body.report_id:
            existing = await db.execute(
                select(Report).where(Report.id == UUID(body.report_id))
            )
            report = existing.scalar_one_or_none()
            if report:
                _update_report_from_result(report, pipeline_result)
                await db.commit()
                pipeline_result["report_id"] = body.report_id
        else:
            report = await _save_report(
                db, user_id, product,
                type('Body', (), {
                    'paciente_nome': body.paciente_nome,
                    'cid': body.cid,
                    'diagnostico': body.diagnostico,
                    'surgery_description': body.surgery_description,
                    'health_plan': body.health_plan,
                    'especialidade': body.especialidade,
                })(),
                pipeline_result,
            )
            pipeline_result["report_id"] = str(report.id)

    return pipeline_result


@router.post("/regenerate")
async def regenerate(
    body: RegenerateIn,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Re-gera relatório com ajustes do médico."""
    if False:  # TODO: re-enable auth
        raise HTTPException(status_code=401, detail="Not authenticated")

    pipeline_result = await ReportPipeline.regenerate(body.session_id, body.adjustments)

    if pipeline_result.get("error"):
        raise HTTPException(status_code=404, detail=pipeline_result["error"])

    if pipeline_result.get("step") == "done" and body.report_id:
        report_result = await db.execute(
            select(Report).where(Report.id == UUID(body.report_id))
        )
        report = report_result.scalar_one_or_none()
        if report:
            _update_report_from_result(report, pipeline_result)
            await db.commit()

    return pipeline_result


@router.get("/checklist/{report_id}")
async def get_checklist(
    report_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Retorna status do checklist de 6 itens obrigatórios."""
    if False:  # TODO: re-enable auth
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    checklist = ReportChecklist.evaluate(report)
    approved = ReportChecklist.is_approved(report)
    missing = ReportChecklist.missing_items(report)

    return {
        "approved": approved,
        "checklist": checklist,
        "missing": missing,
    }


# ============================================================================
# Checklist Reativo (debounced pelo frontend)
# ============================================================================

class QuickCheckIn(BaseModel):
    justificativa_ia: Optional[str] = None
    diagnostico: Optional[str] = None
    falha_terapeutica: Optional[str] = None
    risco_nao_realizacao: Optional[str] = None
    base_legal_ans: Optional[str] = None
    referencias_bib: Optional[list[str]] = None


@router.post("/quick-check")
async def quick_checklist(
    body: QuickCheckIn,
    user_id: str = Depends(get_current_user_id),
):
    """
    Checklist rápido (sem LLM) para validação reativa enquanto o médico edita.
    O frontend chama com debounce de 2s a cada edição no textarea.
    """
    if False:  # TODO: re-enable auth
        raise HTTPException(status_code=401, detail="Not authenticated")

    text = (body.justificativa_ia or "").lower()
    checklist = {
        "diagnostico": {
            "ok": bool(body.diagnostico and len(body.diagnostico.strip()) > 5),
            "label": "Diagnóstico do paciente",
        },
        "justificativa_tecnica": {
            "ok": bool(body.justificativa_ia and len(body.justificativa_ia.strip()) > 100),
            "label": "Justificativa técnica com diferenciais do material",
        },
        "falha_terapeutica": {
            "ok": bool(body.falha_terapeutica and len(body.falha_terapeutica.strip()) > 5),
            "label": "Falha terapêutica prévia",
        },
        "risco_nao_realizacao": {
            "ok": bool(body.risco_nao_realizacao and len(body.risco_nao_realizacao.strip()) > 5),
            "label": "Risco da não realização",
        },
        "base_legal_ans": {
            "ok": bool(body.base_legal_ans) or "rn 395" in text or "resolução" in text or "ans" in text,
            "label": "Base legal ANS (RN 395)",
        },
        "referencia_bibliografica": {
            "ok": bool(body.referencias_bib and len(body.referencias_bib) > 0),
            "label": "Referência bibliográfica",
        },
    }

    approved = all(item["ok"] for item in checklist.values())

    return {
        "approved": approved,
        "checklist": checklist,
    }


# ============================================================================
# Learning Loop — Captura de Edições
# ============================================================================

class SaveEditIn(BaseModel):
    report_id: str
    original_text: str
    edited_text: str
    especialidade: Optional[str] = None


@router.post("/save-edit")
async def save_edit(
    body: SaveEditIn,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Captura diferença entre texto IA e edição do médico para aprendizagem futura."""
    if False:  # TODO: re-enable auth
        raise HTTPException(status_code=401, detail="Not authenticated")

    if body.original_text == body.edited_text:
        return {"saved": False, "reason": "no_changes"}

    from app.services.diff_engine import compute_structured_diff
    from app.db.models import ReportEdit

    diff_result = compute_structured_diff(body.original_text, body.edited_text)

    edit = ReportEdit(
        report_id=UUID(body.report_id),
        user_id=UUID(user_id) if user_id else None,
        especialidade=body.especialidade,
        original_text=body.original_text,
        edited_text=body.edited_text,
        diff_json=diff_result["diff"],
        edit_type=diff_result["edit_type"],
    )
    db.add(edit)
    await db.commit()

    return {"saved": True, "edit_type": diff_result["edit_type"], "changes_count": diff_result["changes_count"]}


# ============================================================================
# Chat legado (mantido para compatibilidade)
# ============================================================================

@router.post("/chat")
async def chat(
    body: ChatIn,
    user_id: str = Depends(get_current_user_id),
):
    if False:  # TODO: re-enable auth
        raise HTTPException(status_code=401, detail="Not authenticated")
    reply = (
        "Para criar um relatório, use o fluxo guiado na aba 'Novo Relatório'. "
        "Selecione o material OPME e preencha os dados do paciente. "
        "O assistente irá gerar a justificativa técnica automaticamente."
    )
    return ChatOut(reply=reply, report_id=None)


# ============================================================================
# PDF Download
# ============================================================================

@router.get("/download-pdf/{report_id}")
async def download_pdf(
    report_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Gera e retorna PDF do relatório."""
    # TODO: re-enable auth scoping
    query = select(Report).where(Report.id == report_id)
    if user_id:
        query = query.where(Report.user_id == user_id)
    result = await db.execute(query)
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")

    product_name = ""
    if report.product_id:
        prod_result = await db.execute(select(Product).where(Product.id == report.product_id))
        product = prod_result.scalar_one_or_none()
        product_name = product.nome if product else ""

    checklist = report.checklist_status if isinstance(report.checklist_status, dict) else {}
    aprovado = all(checklist.values()) if checklist else False

    pdf_bytes = generate_pdf_bytes(
        justificativa=report.justificativa_ia or "",
        paciente_nome=report.paciente_nome or "",
        cid=report.cid or "",
        diagnostico_resumo=report.diagnosis or "",
        produto_nome=product_name,
        convenio=report.health_plan or "",
        especialidade=report.especialidade or "",
        referencias=report.referencias_bib or [],
        checklist=checklist,
        aprovado=aprovado,
    )

    safe_name = (report.paciente_nome or "relatorio").replace(" ", "_")
    filename = f"relatorio_opme_{safe_name}_{report.cid or 'sem_cid'}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============================================================================
# Helpers
# ============================================================================

def _build_tuss_codes(product) -> list[dict] | None:
    """Monta lista de códigos TUSS a partir do produto."""
    code = getattr(product, "codigo_tuss_sugerido", None)
    if code:
        return [{"code": code, "source": "product"}]
    return None


async def _save_report(db, user_id, product, body, pipeline_result) -> Report:
    """Cria Report a partir do resultado do pipeline."""
    report = Report(
        user_id=UUID(user_id) if user_id else None,
        product_id=product.id,
        status="review",
        paciente_nome=body.paciente_nome,
        especialidade=body.especialidade or pipeline_result.get("especialidade"),
        cid=body.cid,
        diagnosis=body.diagnostico,
        surgery_description=body.surgery_description,
        materials=product.nome,
        health_plan=body.health_plan,
        tuss_codes=_build_tuss_codes(product),
        justificativa_ia=pipeline_result.get("justificativa", ""),
        falha_terapeutica=pipeline_result.get("falha_terapeutica", ""),
        risco_nao_realizacao=pipeline_result.get("risco_nao_realizacao", ""),
        base_legal_ans=pipeline_result.get("base_legal", ""),
        referencias_bib=pipeline_result.get("referencias", []),
        agent_audit_log=pipeline_result.get("audit_log", []),
        checklist_status=pipeline_result.get("checklist", {}),
        ai_session_id=pipeline_result.get("session_id"),
        approval_score=pipeline_result.get("approval_score"),
        approval_score_details=pipeline_result.get("approval_componentes"),
        compliance_mode=pipeline_result.get("compliance_mode"),
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)
    await db.commit()
    return report


async def _save_report_from_session(db, user_id, session, pipeline_result) -> Report:
    """Cria Report a partir de session + resultado."""
    product = session.product
    inputs = session.medico_inputs

    report = Report(
        user_id=UUID(user_id) if user_id else None,
        product_id=product.id,
        status="review",
        paciente_nome=inputs.get("paciente_nome", ""),
        especialidade=inputs.get("especialidade", ""),
        cid=inputs.get("cid", ""),
        diagnosis=inputs.get("diagnostico", ""),
        surgery_description=inputs.get("surgery_description", ""),
        materials=product.nome,
        health_plan=inputs.get("health_plan", ""),
        tuss_codes=_build_tuss_codes(product),
        justificativa_ia=pipeline_result.get("justificativa", ""),
        falha_terapeutica=pipeline_result.get("falha_terapeutica", ""),
        risco_nao_realizacao=pipeline_result.get("risco_nao_realizacao", ""),
        base_legal_ans=pipeline_result.get("base_legal", ""),
        referencias_bib=pipeline_result.get("referencias", []),
        agent_audit_log=pipeline_result.get("audit_log", []),
        checklist_status=pipeline_result.get("checklist", {}),
        ai_session_id=session.session_id,
        approval_score=pipeline_result.get("approval_score"),
        approval_score_details=pipeline_result.get("approval_componentes"),
        compliance_mode=pipeline_result.get("compliance_mode"),
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)
    await db.commit()
    return report


def _update_report_from_result(report, pipeline_result):
    """Atualiza Report com resultado de regeneração."""
    report.justificativa_ia = pipeline_result.get("justificativa", report.justificativa_ia)
    report.falha_terapeutica = pipeline_result.get("falha_terapeutica", report.falha_terapeutica)
    report.risco_nao_realizacao = pipeline_result.get("risco_nao_realizacao", report.risco_nao_realizacao)
    report.base_legal_ans = pipeline_result.get("base_legal", report.base_legal_ans)
    report.referencias_bib = pipeline_result.get("referencias", report.referencias_bib)
    report.agent_audit_log = pipeline_result.get("audit_log", report.agent_audit_log)
    report.checklist_status = pipeline_result.get("checklist", report.checklist_status)
    report.updated_at = datetime.utcnow()
