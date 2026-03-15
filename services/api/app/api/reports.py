from uuid import UUID
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models import Report
from app.core.security import get_current_user_id
from app.services.tiss import build_guia_solicitacao_xml, build_guia_pdf

router = APIRouter()


class ReportCreate(BaseModel):
    cid: str
    diagnosis: str
    surgery_description: str
    materials: Optional[str] = None
    health_plan: Optional[str] = None


class ReportOut(BaseModel):
    id: str
    status: str
    cid: Optional[str] = None
    diagnosis: Optional[str] = None
    surgery_description: Optional[str] = None
    materials: Optional[str] = None
    health_plan: Optional[str] = None
    created_at: str
    inconsistencies: Optional[list] = None
    patient_diagnosis: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("")
async def list_reports(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=1000, description="Items per page"),
):
    # TODO: re-enable auth when ready
    if user_id:
        base = select(Report).where(Report.user_id == UUID(user_id))
    else:
        base = select(Report)

    # Total count
    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar() or 0

    # Paginated query
    offset = (page - 1) * per_page
    result = await db.execute(
        base.order_by(Report.created_at.desc()).offset(offset).limit(per_page)
    )
    reports = result.scalars().all()

    return {
        "items": [
            {
                "id": str(r.id),
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "patient_diagnosis": r.diagnosis,
            }
            for r in reports
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if total > 0 else 1,
    }


@router.get("/{report_id}")
async def get_report(
    report_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # TODO: re-enable auth when ready
    if user_id:
        result = await db.execute(
            select(Report).where(Report.id == report_id, Report.user_id == UUID(user_id))
        )
    else:
        result = await db.execute(
            select(Report).where(Report.id == report_id)
        )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "id": str(r.id),
        "status": r.status,
        "cid": r.cid,
        "diagnosis": r.diagnosis,
        "surgery_description": r.surgery_description,
        "materials": r.materials,
        "health_plan": r.health_plan,
        "created_at": r.created_at.isoformat() if r.created_at else "",
        "inconsistencies": r.inconsistencies or [],
    }


@router.post("")
async def create_report(
    body: ReportCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # TODO: re-enable auth when ready
    report = Report(
        user_id=UUID(user_id) if user_id else None,
        status="draft",
        cid=body.cid,
        diagnosis=body.diagnosis,
        surgery_description=body.surgery_description,
        materials=body.materials,
        health_plan=body.health_plan,
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)
    return {"id": str(report.id)}


@router.post("/{report_id}/sign")
async def sign_report(
    report_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # TODO: re-enable auth when ready
    if user_id:
        result = await db.execute(
            select(Report).where(Report.id == report_id, Report.user_id == UUID(user_id))
        )
    else:
        result = await db.execute(
            select(Report).where(Report.id == report_id)
        )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    from datetime import datetime
    r.status = "signed"
    r.signed_at = datetime.utcnow()
    await db.flush()
    return {}


@router.post("/review/upload")
async def review_upload(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Upload de arquivo para revisão: extrai texto, compara com TUSS e retorna inconsistências."""
    content = (await file.read()).decode("utf-8", errors="ignore")
    inconsistencies = await _review_text(db, content)
    return {"inconsistencies": inconsistencies}


@router.post("/review/text")
async def review_text(
    body: dict,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Revisão por texto colado: compara com TUSS e retorna inconsistências."""
    text = body.get("text") or ""
    inconsistencies = await _review_text(db, text)
    return {"inconsistencies": inconsistencies}


async def _review_text(db: AsyncSession, text: str) -> list[dict]:
    """Identifica possíveis códigos no texto e valida contra TUSS; retorna lista de {field, message}."""
    import re
    from app.db.models import TussTerm
    from sqlalchemy import select
    inconsistencies = []
    # Códigos TUSS são numéricos (ex.: 30701020)
    possible_codes = re.findall(r"\b(\d{8,10})\b", text)
    for code in set(possible_codes):
        r = await db.execute(select(TussTerm).where(TussTerm.code == code).limit(1))
        if r.scalar_one_or_none() is None:
            inconsistencies.append({"field": "codigo_tuss", "message": f"Código {code} não encontrado na tabela TUSS."})
    if not text.strip():
        inconsistencies.append({"field": "conteudo", "message": "Nenhum texto fornecido."})
    return inconsistencies


@router.get("/{report_id}/download")
async def download_report(
    report_id: UUID,
    format: str = Query("pdf", regex="^(pdf|xml|docx)$"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # TODO: re-enable auth when ready
    if user_id:
        result = await db.execute(
            select(Report).where(Report.id == report_id, Report.user_id == UUID(user_id))
        )
    else:
        result = await db.execute(
            select(Report).where(Report.id == report_id)
        )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    if format == "xml":
        xml_str = build_guia_solicitacao_xml(r)
        return Response(
            content=xml_str,
            media_type="application/xml",
            headers={"Content-Disposition": f"attachment; filename=guia-tiss-{report_id}.xml"},
        )
    if format == "docx":
        from app.services.docx_generator import generate_docx_bytes
        checklist = r.checklist_status if hasattr(r, "checklist_status") else None
        refs = r.referencias_bib if hasattr(r, "referencias_bib") else []
        docx_bytes = generate_docx_bytes(
            justificativa=r.justificativa_ia or "",
            paciente_nome=r.paciente_nome or "",
            cid=r.cid or "",
            diagnostico_resumo=r.diagnosis or "",
            produto_nome=getattr(r, "product_nome", "") or "",
            convenio=r.health_plan or "",
            especialidade=r.especialidade or "",
            codigo_tuss="",
            referencias=refs if isinstance(refs, list) else [],
            checklist=checklist if isinstance(checklist, dict) else None,
            aprovado=True,
        )
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename=relatorio-{report_id}.docx"},
        )
    pdf_bytes = build_guia_pdf(r)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=relatorio-{report_id}.pdf"},
    )
