"""
API do Assistente Multi-Agente de Relatórios OPME.
Pipeline: Pesquisador (A) -> Redator (B) -> Auditor (C).
"""
import uuid as uuid_mod
from uuid import UUID
from typing import Optional
from datetime import datetime

import asyncio
import json as json_mod

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.session import get_db, AsyncSessionLocal
from app.db.models import Product, Report, ReportTemplate, AuditAction, User
from app.core.security import get_current_user_id, require_current_user_id
from app.services.agents.pipeline import ReportPipeline
from app.services.agents.checklist import ReportChecklist
from app.services.pdf_generator import generate_pdf_bytes
from app.services.audit_service import audit_log

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


# ============================================================================
# Schemas
# ============================================================================

class _AntiGlosaFields(BaseModel):
    """Campos opcionais de identificação exigidos por operadoras (anti-glosa).

    Todos opcionais para não quebrar clientes atuais; renderizados no PDF quando
    presentes e usados como contexto clínico no pipeline quando relevantes.
    """
    paciente_dob: Optional[str] = None            # data de nascimento
    paciente_carteirinha: Optional[str] = None    # nº carteirinha do convênio
    paciente_cpf: Optional[str] = None
    guia_numero: Optional[str] = None             # nº da guia TISS
    atendimento_numero: Optional[str] = None
    cids_secundarios: Optional[list[str]] = None
    materiais_tuss: Optional[list[dict]] = None    # [{"codigo","nome","qtd"}]


class StartReportIn(_AntiGlosaFields):
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
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Preview de evidências disponíveis para um CID (internas + PubMed)."""
    if not cid or len(cid.strip()) < 3:
        return {"cid": cid, "internal_count": 0, "pubmed_count": 0, "total_count": 0, "preview": []}

    from app.services.pubmed_service import get_evidences_preview
    return await get_evidences_preview(db, cid, product_name)


# ============================================================================
# Pipeline Multi-Agente
# ============================================================================

@router.post("/start-report")
@limiter.limit("20/hour")
async def start_report(
    request: Request,
    body: StartReportIn,
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Inicia sessão do pipeline multi-agente.
    1. Busca produto e template
    2. Executa Agente A (Pesquisador)
    3. Retorna perguntas A/B/C se houver lacunas, ou gera direto
    """

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
        user_id=user_id,
        extra_report_fields=_extra_report_fields(body),
    )

    if pipeline_result.get("error"):
        raise HTTPException(status_code=400, detail=pipeline_result["error"])

    if pipeline_result.get("step") == "done":
        report = await _save_report(db, user_id, product, body, pipeline_result)
        pipeline_result["report_id"] = str(report.id)

    return pipeline_result


@router.post("/start-report-stream")
@limiter.limit("20/hour")
async def start_report_stream(
    request: Request,
    body: StartReportIn,
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    SSE: Inicia pipeline com eventos de progresso em tempo real.
    Retorna Server-Sent Events com cada etapa do pipeline.
    """

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
                user_id=user_id,
                extra_report_fields=_extra_report_fields(body),
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
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Recebe respostas A/B/C do médico e avança o pipeline.
    """

    pipeline_result = await ReportPipeline.answer(body.session_id, body.answers, user_id=user_id)

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
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    SSE: Recebe respostas A/B/C e avança pipeline com eventos de progresso.
    """

    async def event_stream():
        progress_queue: asyncio.Queue = asyncio.Queue()

        async def on_progress(step: str, message: str):
            await progress_queue.put({"event": "step", "step": step, "message": message})

        async def run_pipeline():
            pipeline_result = await ReportPipeline.answer(
                body.session_id, body.answers, on_progress=on_progress, user_id=user_id,
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


class GenerateIn(_AntiGlosaFields):
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


# ============================================================================
# Batch Generation
# ============================================================================

class BatchItemIn(BaseModel):
    product_id: str
    paciente_nome: str
    cid: str
    diagnostico: str
    surgery_description: Optional[str] = None
    health_plan: Optional[str] = None
    especialidade: Optional[str] = None


class BatchGenerateIn(BaseModel):
    items: list[BatchItemIn]
    max_concurrency: int = 3


# In-memory batch jobs (use Redis in production)
_BATCH_JOBS: dict[str, dict] = {}


@router.post("/generate-batch")
async def generate_batch(
    body: BatchGenerateIn,
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Batch generation: processes multiple reports concurrently with bounded concurrency.
    Returns a job_id for polling progress via /batch-status/{job_id}.
    """
    import asyncio as _asyncio

    job_id = str(uuid_mod.uuid4())
    job = {
        "job_id": job_id,
        "status": "processing",
        "total": len(body.items),
        "completed": 0,
        "failed": 0,
        "results": [],
    }
    _BATCH_JOBS[job_id] = job

    async def process_items():
        semaphore = _asyncio.Semaphore(body.max_concurrency)

        async def process_one(item: BatchItemIn, index: int):
            async with semaphore:
                # Cada corrotina abre a PRÓPRIA sessão de banco: AsyncSession NÃO é
                # segura para uso concorrente, e a sessão da request já foi fechada
                # (este código roda em background após o retorno). Isolar por paciente
                # elimina o risco de mistura/erro cross-paciente.
                async with AsyncSessionLocal() as sdb:
                    try:
                        result_db = await sdb.execute(
                            select(Product).where(Product.id == UUID(item.product_id))
                        )
                        product = result_db.scalar_one_or_none()
                        if not product:
                            job["results"].append({"index": index, "error": "Produto não encontrado"})
                            job["failed"] += 1
                            return

                        template_result = await sdb.execute(
                            select(ReportTemplate).where(ReportTemplate.produto_id == product.id).limit(1)
                        )
                        template = template_result.scalar_one_or_none()

                        medico_inputs = {
                            "paciente_nome": item.paciente_nome,
                            "cid": item.cid,
                            "diagnostico": item.diagnostico,
                            "surgery_description": item.surgery_description or "",
                            "health_plan": item.health_plan or "",
                            "especialidade": item.especialidade or "",
                        }

                        pipeline_result = await ReportPipeline.start(
                            product=product,
                            template=template,
                            diagnostico=item.diagnostico,
                            cid=item.cid,
                            medico_inputs=medico_inputs,
                            db=sdb,
                            user_id=user_id,
                            extra_report_fields=_extra_report_fields(item),
                        )

                        if pipeline_result.get("step") == "done":
                            report = await _save_report(sdb, user_id, product, item, pipeline_result)
                            await sdb.commit()
                            job["results"].append({
                                "index": index,
                                "report_id": str(report.id),
                                "aprovado": pipeline_result.get("aprovado", False),
                            })
                            job["completed"] += 1
                        else:
                            job["results"].append({"index": index, "status": pipeline_result.get("step")})
                            job["completed"] += 1

                    except Exception as e:
                        job["results"].append({"index": index, "error": str(e)})
                        job["failed"] += 1

        await _asyncio.gather(
            *[process_one(item, i) for i, item in enumerate(body.items)],
            return_exceptions=True,
        )
        job["status"] = "completed"

    # Run in background
    import asyncio
    asyncio.create_task(process_items())

    return {"job_id": job_id, "total": len(body.items), "status": "accepted"}


@router.get("/batch-status/{job_id}")
async def batch_status(
    job_id: str,
    user_id: str = Depends(require_current_user_id),
):
    """Poll batch job progress."""
    job = _BATCH_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "progress": f"{job['completed'] + job['failed']}/{job['total']}",
        "completed": job["completed"],
        "failed": job["failed"],
        "results": job["results"] if job["status"] == "completed" else [],
    }


@router.post("/generate")
@limiter.limit("20/hour")
async def generate_full(
    request: Request,
    body: GenerateIn,
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Executa pipeline completo (A -> B -> C -> Validador).
    strict_mode=true bloqueia PDF se validação hard-coded falhar.
    """

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
        user_id=user_id,
        extra_report_fields=_extra_report_fields(body),
    )

    if pipeline_result.get("error"):
        raise HTTPException(status_code=400, detail=pipeline_result["error"])

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
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Re-gera relatório com ajustes do médico."""

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
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Retorna status do checklist de 6 itens obrigatórios."""

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
    user_id: str = Depends(require_current_user_id),
):
    """
    Checklist rápido (sem LLM) para validação reativa enquanto o médico edita.
    O frontend chama com debounce de 2s a cada edição no textarea.
    """

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
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Captura diferença entre texto IA e edição do médico para aprendizagem futura."""

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
    user_id: str = Depends(require_current_user_id),
):
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
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Gera e retorna PDF do relatório."""
    query = select(Report).where(Report.id == report_id, Report.user_id == user_id)
    result = await db.execute(query)
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")

    product_name = ""
    product_tuss = ""
    registro_anvisa = ""
    if report.product_id:
        prod_result = await db.execute(select(Product).where(Product.id == report.product_id))
        product = prod_result.scalar_one_or_none()
        if product:
            product_name = product.nome or ""
            product_tuss = product.codigo_tuss_sugerido or ""
            registro_anvisa = product.registro_anvisa or ""

    # Emitente (clínica/RQE) do usuário
    clinica_nome = clinica_logo_url = medico_rqe = ""
    u_res = await db.execute(select(User).where(User.id == report.user_id))
    u = u_res.scalar_one_or_none()
    if u:
        clinica_nome = getattr(u, "clinica_nome", "") or ""
        clinica_logo_url = getattr(u, "clinica_logo_url", "") or ""
        medico_rqe = getattr(u, "rqe", "") or ""

    # Extract TUSS from report or product
    tuss_codes = getattr(report, "tuss_codes", None) or []
    if tuss_codes and isinstance(tuss_codes, list):
        codes = [t.get("code", "") if isinstance(t, dict) else str(t) for t in tuss_codes]
        codigo_tuss = ", ".join(c for c in codes if c)
    else:
        codigo_tuss = product_tuss

    checklist = report.checklist_status if isinstance(report.checklist_status, dict) else {}
    aprovado = all(checklist.values()) if checklist else False

    pdf_bytes = generate_pdf_bytes(
        justificativa=report.justificativa_ia or "",
        paciente_nome=report.paciente_nome or "",
        cid=report.cid or "",
        diagnostico_resumo=report.diagnosis or "",
        produto_nome=product_name or report.materials or "",
        convenio=report.health_plan or "",
        especialidade=report.especialidade or "",
        codigo_tuss=codigo_tuss,
        referencias=report.referencias_bib or [],
        checklist=checklist,
        aprovado=aprovado,
        falha_terapeutica=getattr(report, "falha_terapeutica", "") or "",
        risco_nao_realizacao=getattr(report, "risco_nao_realizacao", "") or "",
        base_legal=getattr(report, "base_legal_ans", "") or "",
        medico_rqe=medico_rqe,
        clinica_nome=clinica_nome,
        clinica_logo_url=clinica_logo_url,
        paciente_dob=getattr(report, "paciente_dob", "") or "",
        paciente_carteirinha=getattr(report, "paciente_carteirinha", "") or "",
        paciente_cpf=getattr(report, "paciente_cpf", "") or "",
        guia_numero=getattr(report, "guia_numero", "") or "",
        atendimento_numero=getattr(report, "atendimento_numero", "") or "",
        cids_secundarios=getattr(report, "cids_secundarios", None) or [],
        materiais_tuss=getattr(report, "materiais_tuss", None) or [],
        registro_anvisa=registro_anvisa,
        compliance_texto=getattr(report, "compliance_texto", "") or "",
    )

    # LGPD audit: log PDF export
    await audit_log(
        db, AuditAction.EXPORT, "report",
        resource_id=str(report.id),
        user_id=user_id,
        justification="Exportação de relatório em PDF (obrigação legal TISS, LGPD Art. 11)",
    )
    await db.commit()

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


def _extra_report_fields(body) -> dict:
    """Campos administrativos anti-glosa do request (não vão para o prompt do LLM;
    são carregados pela sessão e persistidos no Report ao final)."""
    return {
        k: getattr(body, k, None)
        for k in (
            "paciente_dob", "paciente_carteirinha", "paciente_cpf",
            "guia_numero", "atendimento_numero", "cids_secundarios", "materiais_tuss",
        )
        if getattr(body, k, None)
    }


async def _save_report(db, user_id, product, body, pipeline_result, request: Request = None) -> Report:
    """Cria Report a partir do resultado do pipeline."""
    report = Report(
        user_id=UUID(user_id) if user_id else None,
        product_id=product.id,
        status="review",
        paciente_nome=body.paciente_nome,
        paciente_dob=getattr(body, "paciente_dob", None),
        paciente_carteirinha=getattr(body, "paciente_carteirinha", None),
        paciente_cpf=getattr(body, "paciente_cpf", None),
        guia_numero=getattr(body, "guia_numero", None),
        atendimento_numero=getattr(body, "atendimento_numero", None),
        especialidade=body.especialidade or pipeline_result.get("especialidade"),
        cid=body.cid,
        cids_secundarios=getattr(body, "cids_secundarios", None),
        diagnosis=body.diagnostico,
        surgery_description=body.surgery_description,
        materials=product.nome,
        materiais_tuss=getattr(body, "materiais_tuss", None),
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
        compliance_texto=pipeline_result.get("compliance_texto"),
        operadora_registro_ans=pipeline_result.get("operadora_registro_ans"),
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)

    # LGPD audit: log report generation
    await audit_log(
        db, AuditAction.GENERATE, "report",
        resource_id=str(report.id),
        user_id=user_id,
        justification="Geração de relatório OPME via pipeline multi-agente (tutela da saúde, LGPD Art. 11)",
        metadata={"product_id": str(product.id), "cid": body.cid},
    )

    await db.commit()
    return report


async def _save_report_from_session(db, user_id, session, pipeline_result) -> Report:
    """Cria Report a partir de session + resultado."""
    product = session.product
    inputs = session.medico_inputs

    extra = getattr(session, "extra_report_fields", None) or {}
    report = Report(
        user_id=UUID(user_id) if user_id else None,
        product_id=product.id,
        status="review",
        paciente_nome=inputs.get("paciente_nome", ""),
        paciente_dob=extra.get("paciente_dob"),
        paciente_carteirinha=extra.get("paciente_carteirinha"),
        paciente_cpf=extra.get("paciente_cpf"),
        guia_numero=extra.get("guia_numero"),
        atendimento_numero=extra.get("atendimento_numero"),
        cids_secundarios=extra.get("cids_secundarios"),
        materiais_tuss=extra.get("materiais_tuss"),
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
        compliance_texto=pipeline_result.get("compliance_texto"),
        operadora_registro_ans=pipeline_result.get("operadora_registro_ans"),
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
