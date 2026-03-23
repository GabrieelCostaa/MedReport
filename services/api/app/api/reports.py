import hashlib
from datetime import datetime
from uuid import UUID
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models import Report, Product, User
from app.core.security import get_current_user_id
from app.services.tiss import build_guia_solicitacao_xml

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
    """Assina eletronicamente o relatório: gera PDF selado com QR Code e hash SHA-256."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Busca relatório
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")

    # Verifica propriedade
    if str(report.user_id) != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    # Verifica se já assinado
    if report.status == "signed":
        raise HTTPException(status_code=409, detail="Relatório já assinado")

    # Busca dados do médico
    user_result = await db.execute(select(User).where(User.id == UUID(str(user_id))))
    user = user_result.scalar_one_or_none()
    if not user or not user.crm:
        raise HTTPException(
            status_code=422,
            detail="Complete seu perfil com CRM antes de assinar.",
        )

    # Resolve produto
    product_name = ""
    codigo_tuss = ""
    if getattr(report, "product_id", None):
        prod_result = await db.execute(select(Product).where(Product.id == report.product_id))
        product = prod_result.scalar_one_or_none()
        if product:
            product_name = product.nome or ""
            codigo_tuss = product.codigo_tuss_sugerido or ""

    tuss_codes = getattr(report, "tuss_codes", None) or []
    if tuss_codes and isinstance(tuss_codes, list):
        codes = [t.get("code", "") if isinstance(t, dict) else str(t) for t in tuss_codes]
        codigo_tuss = ", ".join(c for c in codes if c) or codigo_tuss

    checklist = report.checklist_status if isinstance(getattr(report, "checklist_status", None), dict) else None
    refs = report.referencias_bib if isinstance(getattr(report, "referencias_bib", None), list) else []
    aprovado = all(checklist.values()) if checklist else True

    signed_at = datetime.utcnow()
    signed_at_str = signed_at.strftime("%d/%m/%Y às %H:%M:%S UTC")
    medico_crm_fmt = f"CRM/{user.crm_uf} {user.crm}" if user.crm_uf else f"CRM {user.crm}"

    from app.core.config import settings
    verification_url = f"{settings.API_BASE_URL}/api/reports/{report_id}/verify"

    # Gera PDF com bloco de assinatura e QR Code
    from app.services.pdf_generator import generate_pdf_bytes
    try:
        pdf_bytes = generate_pdf_bytes(
            justificativa=report.justificativa_ia or "",
            paciente_nome=report.paciente_nome or "",
            cid=report.cid or "",
            diagnostico_resumo=report.diagnosis or "",
            produto_nome=product_name or report.materials or "",
            convenio=report.health_plan or "",
            especialidade=getattr(report, "especialidade", "") or "",
            codigo_tuss=codigo_tuss,
            referencias=refs,
            checklist=checklist,
            aprovado=aprovado,
            falha_terapeutica=getattr(report, "falha_terapeutica", "") or "",
            risco_nao_realizacao=getattr(report, "risco_nao_realizacao", "") or "",
            base_legal=getattr(report, "base_legal_ans", "") or "",
            medico_nome=user.nome or "",
            medico_crm=medico_crm_fmt,
            signed_at_str=signed_at_str,
            # hash ainda não existe — será calculado após gerar o PDF
            signature_hash="",
            verification_url=verification_url,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")

    # Calcula SHA-256 do PDF gerado
    signature_hash = hashlib.sha256(pdf_bytes).hexdigest()

    # Persiste em transação única
    report.signed_at = signed_at
    report.status = "signed"
    report.medico_nome = user.nome
    report.medico_crm = user.crm
    report.medico_crm_uf = user.crm_uf
    report.signature_hash = signature_hash
    report.pdf_signed_bytes = pdf_bytes
    await db.commit()

    return {
        "signed_at": signed_at.isoformat() + "Z",
        "signature_hash": signature_hash,
        "medico_nome": user.nome,
        "medico_crm": user.crm,
        "medico_crm_uf": user.crm_uf,
        "verification_url": verification_url,
    }


@router.get("/{report_id}/verify")
async def verify_report(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Verifica autenticidade de um relatório assinado. Endpoint público (sem autenticação)."""
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")

    if report.status != "signed" or not report.signature_hash:
        return {
            "autêntico": False,
            "status": "não assinado",
            "documento_id": str(report_id),
        }

    return {
        "autêntico": True,
        "status": "assinado",
        "documento_id": str(report_id),
        "medico_nome": report.medico_nome,
        "medico_crm": report.medico_crm,
        "medico_crm_uf": report.medico_crm_uf,
        "assinado_em": report.signed_at.isoformat() + "Z" if report.signed_at else None,
        "sha256": report.signature_hash,
    }


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

    # PDF assinado: serve o arquivo selado salvo no momento da assinatura
    if format == "pdf" and r.status == "signed" and getattr(r, "pdf_signed_bytes", None):
        return Response(
            content=r.pdf_signed_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=relatorio-{report_id}-assinado.pdf"},
        )

    if format == "xml":
        xml_str = build_guia_solicitacao_xml(r)
        return Response(
            content=xml_str,
            media_type="application/xml",
            headers={"Content-Disposition": f"attachment; filename=guia-tiss-{report_id}.xml"},
        )
    # Resolve product name and TUSS code
    product_name = ""
    product_tuss = ""
    if hasattr(r, "product_id") and r.product_id:
        prod_result = await db.execute(select(Product).where(Product.id == r.product_id))
        product = prod_result.scalar_one_or_none()
        if product:
            product_name = product.nome or ""
            product_tuss = product.codigo_tuss_sugerido or ""

    # Extract TUSS from report.tuss_codes JSON or product
    tuss_codes = getattr(r, "tuss_codes", None) or []
    if tuss_codes and isinstance(tuss_codes, list):
        codes = [t.get("code", "") if isinstance(t, dict) else str(t) for t in tuss_codes]
        codigo_tuss = ", ".join(c for c in codes if c)
    else:
        codigo_tuss = product_tuss

    checklist = r.checklist_status if isinstance(getattr(r, "checklist_status", None), dict) else None
    refs = r.referencias_bib if isinstance(getattr(r, "referencias_bib", None), list) else []
    aprovado = all(checklist.values()) if checklist else False

    common_kwargs = dict(
        justificativa=r.justificativa_ia or "",
        paciente_nome=r.paciente_nome or "",
        cid=r.cid or "",
        diagnostico_resumo=r.diagnosis or "",
        produto_nome=product_name or r.materials or "",
        convenio=r.health_plan or "",
        especialidade=getattr(r, "especialidade", "") or "",
        codigo_tuss=codigo_tuss,
        referencias=refs,
        checklist=checklist,
        aprovado=aprovado,
        falha_terapeutica=getattr(r, "falha_terapeutica", "") or "",
        risco_nao_realizacao=getattr(r, "risco_nao_realizacao", "") or "",
        base_legal=getattr(r, "base_legal_ans", "") or "",
        medico_nome=getattr(r, "medico_nome", "") or "",
        medico_crm=(
            f"CRM/{r.medico_crm_uf} {r.medico_crm}"
            if getattr(r, "medico_crm", None) and getattr(r, "medico_crm_uf", None)
            else (getattr(r, "medico_crm", "") or "")
        ),
    )

    if format == "docx":
        from app.services.docx_generator import generate_docx_bytes
        docx_bytes = generate_docx_bytes(**common_kwargs)
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename=relatorio-{report_id}.docx"},
        )

    from app.services.pdf_generator import generate_pdf_bytes
    pdf_bytes = generate_pdf_bytes(**common_kwargs)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=relatorio-{report_id}.pdf"},
    )
