from uuid import UUID
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
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
):
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    result = await db.execute(
        select(Report).where(Report.user_id == UUID(user_id)).order_by(Report.created_at.desc())
    )
    reports = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "patient_diagnosis": r.diagnosis,
        }
        for r in reports
    ]


@router.get("/{report_id}")
async def get_report(
    report_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.user_id == UUID(user_id))
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
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    report = Report(
        user_id=UUID(user_id),
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
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.user_id == UUID(user_id))
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
    format: str = Query("pdf", regex="^(pdf|xml)$"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.user_id == UUID(user_id))
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
    pdf_bytes = build_guia_pdf(r)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=relatorio-{report_id}.pdf"},
    )
