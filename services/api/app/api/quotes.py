"""
API de Cotações RPA.
Endpoints para ingestão, listagem, exportação e integração ERP.
"""
from uuid import UUID
from typing import Optional
from datetime import datetime
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Header, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.db.models import (
    Quote, QuoteItem, QuoteAttachment, QuoteBudget, RpaRun,
    QuoteStatus, BuyerType, RpaRunStatus, PortalConfig
)
from app.core.security import get_current_user_id
from app.core.config import settings

router = APIRouter()


# ============================================================================
# Schemas de entrada/saída
# ============================================================================

class BuyerInfo(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None


class DeliveryInfo(BaseModel):
    city: Optional[str] = None
    state: Optional[str] = None
    notes: Optional[str] = None


class QuoteItemIngest(BaseModel):
    line_no: Optional[str] = None
    product_code_raw: Optional[str] = None
    product_name_raw: Optional[str] = None
    qty: Optional[str] = None
    uom: Optional[str] = None
    brand_pref: Optional[str] = None
    specs: Optional[str] = None
    comments: Optional[str] = None


class AttachmentIngest(BaseModel):
    filename: str
    mime_type: Optional[str] = None
    size_bytes: Optional[str] = None
    storage_uri: Optional[str] = None
    sha256: Optional[str] = None


class RpaRunInfo(BaseModel):
    run_id: Optional[str] = None
    captcha_encountered: bool = False
    pages_visited: Optional[str] = None


class QuoteIngestItem(BaseModel):
    """Schema completo para ingestão de cotação do RPA."""
    tenant_id: Optional[str] = None
    external_id: Optional[str] = None
    portal: str
    status: str = "open"
    published_at: Optional[str] = None
    deadline: Optional[str] = None
    captured_at: Optional[str] = None
    buyer: Optional[BuyerInfo] = None
    delivery: Optional[DeliveryInfo] = None
    description: Optional[str] = None
    notes_raw: Optional[str] = None
    currency: str = "BRL"
    items: list[QuoteItemIngest] = Field(default_factory=list)
    attachments: list[AttachmentIngest] = Field(default_factory=list)
    rpa_run: Optional[RpaRunInfo] = None
    raw_payload: Optional[dict] = None


class QuoteIngest(BaseModel):
    quotes: list[QuoteIngestItem]


class BudgetCreate(BaseModel):
    items: list[dict]
    total_value: Optional[str] = None
    payment_terms: Optional[str] = None
    delivery_days: Optional[str] = None
    validity_days: Optional[str] = None
    notes: Optional[str] = None


class BudgetApprove(BaseModel):
    approved_by: str


class ErpWebhookPayload(BaseModel):
    event: str
    quotation_id: str
    tenant_id: Optional[str] = None


# ============================================================================
# Helpers
# ============================================================================

def _check_ingest_key(x_api_key: str | None = Header(None), authorization: str | None = Header(None)) -> bool:
    if not settings.INGEST_API_KEY:
        return True
    token = (authorization or "").replace("Bearer ", "").strip() if authorization else None
    return (x_api_key == settings.INGEST_API_KEY) or (token == settings.INGEST_API_KEY)


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _parse_status(value: str) -> QuoteStatus:
    try:
        return QuoteStatus(value)
    except ValueError:
        return QuoteStatus.pending


def _parse_buyer_type(value: Optional[str]) -> Optional[BuyerType]:
    if not value:
        return None
    try:
        return BuyerType(value)
    except ValueError:
        return BuyerType.other


# ============================================================================
# Endpoints de Ingestão (RPA)
# ============================================================================

@router.post("/ingest")
async def ingest_quotes(
    body: QuoteIngest,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(None),
    authorization: str | None = Header(None),
):
    """
    Endpoint para RPA/robôs enviarem cotações coletadas.
    Requer INGEST_API_KEY se configurado.
    
    Suporta:
    - Cotações com itens e anexos
    - Idempotência por portal + external_id
    - Registro de execução RPA
    """
    if settings.INGEST_API_KEY and not _check_ingest_key(x_api_key, authorization):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    
    created_quotes = []
    updated_quotes = []
    created_items = 0
    created_attachments = 0
    
    for q in body.quotes:
        existing = None
        if q.external_id:
            result = await db.execute(
                select(Quote).where(
                    and_(Quote.portal == q.portal, Quote.external_id == q.external_id)
                )
            )
            existing = result.scalar_one_or_none()
        
        if existing:
            existing.status = _parse_status(q.status)
            existing.deadline = _parse_datetime(q.deadline)
            existing.captured_at = _parse_datetime(q.captured_at) or datetime.utcnow()
            if q.buyer:
                existing.buyer_name = q.buyer.name
                existing.buyer_type = _parse_buyer_type(q.buyer.type)
            if q.delivery:
                existing.delivery_city = q.delivery.city
                existing.delivery_state = q.delivery.state
                existing.delivery_notes = q.delivery.notes
            existing.description = q.description
            existing.notes_raw = q.notes_raw
            existing.payload = q.raw_payload
            updated_quotes.append(str(existing.id))
            quote = existing
        else:
            quote = Quote(
                tenant_id=q.tenant_id,
                portal=q.portal,
                external_id=q.external_id,
                status=_parse_status(q.status),
                published_at=_parse_datetime(q.published_at),
                deadline=_parse_datetime(q.deadline),
                captured_at=_parse_datetime(q.captured_at) or datetime.utcnow(),
                buyer_name=q.buyer.name if q.buyer else None,
                buyer_type=_parse_buyer_type(q.buyer.type if q.buyer else None),
                delivery_city=q.delivery.city if q.delivery else None,
                delivery_state=q.delivery.state if q.delivery else None,
                delivery_notes=q.delivery.notes if q.delivery else None,
                description=q.description,
                notes_raw=q.notes_raw,
                currency=q.currency,
                payload=q.raw_payload or {},
            )
            db.add(quote)
            await db.flush()
            created_quotes.append(str(quote.id))
        
        for item_data in q.items:
            item = QuoteItem(
                quote_id=quote.id,
                line_no=item_data.line_no,
                product_code_raw=item_data.product_code_raw,
                product_name_raw=item_data.product_name_raw,
                qty=item_data.qty,
                uom=item_data.uom,
                brand_pref=item_data.brand_pref,
                specs=item_data.specs,
                comments=item_data.comments,
            )
            db.add(item)
            created_items += 1
        
        for att_data in q.attachments:
            attachment = QuoteAttachment(
                quote_id=quote.id,
                filename=att_data.filename,
                mime_type=att_data.mime_type,
                size_bytes=att_data.size_bytes,
                storage_uri=att_data.storage_uri,
                sha256=att_data.sha256,
                downloaded_at=datetime.utcnow() if att_data.storage_uri else None,
                download_status="success" if att_data.storage_uri else "pending",
            )
            db.add(attachment)
            created_attachments += 1
    
    await db.commit()
    
    return {
        "created": created_quotes,
        "updated": updated_quotes,
        "items_created": created_items,
        "attachments_created": created_attachments,
    }


# ============================================================================
# Endpoints de Listagem
# ============================================================================

@router.get("")
async def list_quotes(
    portal: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    buyer_type: Optional[str] = Query(None),
    deadline_before: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Lista cotações com filtros."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    q = select(Quote)
    
    if portal:
        q = q.where(Quote.portal == portal)
    if status:
        q = q.where(Quote.status == _parse_status(status))
    if tenant_id:
        q = q.where(Quote.tenant_id == tenant_id)
    if buyer_type:
        q = q.where(Quote.buyer_type == _parse_buyer_type(buyer_type))
    if deadline_before:
        dt = _parse_datetime(deadline_before)
        if dt:
            q = q.where(Quote.deadline <= dt)
    
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    
    q = q.order_by(Quote.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    quotes = result.scalars().all()
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": str(quote.id),
                "external_id": quote.external_id or "",
                "portal": quote.portal,
                "status": quote.status.value if hasattr(quote.status, 'value') else quote.status,
                "buyer_name": quote.buyer_name,
                "buyer_type": quote.buyer_type.value if quote.buyer_type else None,
                "deadline": quote.deadline.isoformat() if quote.deadline else None,
                "delivery_city": quote.delivery_city,
                "delivery_state": quote.delivery_state,
                "description": (quote.description or "")[:200],
                "created_at": quote.created_at.isoformat() if quote.created_at else "",
            }
            for quote in quotes
        ]
    }


@router.get("/stats")
async def get_quotes_stats(
    portal: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Estatísticas agregadas de cotações."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    base_q = select(Quote)
    if portal:
        base_q = base_q.where(Quote.portal == portal)
    if tenant_id:
        base_q = base_q.where(Quote.tenant_id == tenant_id)
    
    total = (await db.execute(
        select(func.count()).select_from(base_q.subquery())
    )).scalar() or 0
    
    by_status = {}
    for status in QuoteStatus:
        count = (await db.execute(
            select(func.count()).select_from(
                base_q.where(Quote.status == status).subquery()
            )
        )).scalar() or 0
        by_status[status.value] = count
    
    by_portal = {}
    portal_counts = await db.execute(
        select(Quote.portal, func.count()).group_by(Quote.portal)
    )
    for row in portal_counts:
        by_portal[row[0]] = row[1]
    
    return {
        "total": total,
        "by_status": by_status,
        "by_portal": by_portal,
    }


@router.get("/{quote_id}")
async def get_quote(
    quote_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Obtém detalhes de uma cotação com itens e anexos."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    
    items_result = await db.execute(
        select(QuoteItem).where(QuoteItem.quote_id == quote_id)
    )
    items = items_result.scalars().all()
    
    attachments_result = await db.execute(
        select(QuoteAttachment).where(QuoteAttachment.quote_id == quote_id)
    )
    attachments = attachments_result.scalars().all()
    
    return {
        "id": str(quote.id),
        "external_id": quote.external_id,
        "portal": quote.portal,
        "status": quote.status.value if hasattr(quote.status, 'value') else quote.status,
        "buyer_name": quote.buyer_name,
        "buyer_type": quote.buyer_type.value if quote.buyer_type else None,
        "published_at": quote.published_at.isoformat() if quote.published_at else None,
        "deadline": quote.deadline.isoformat() if quote.deadline else None,
        "captured_at": quote.captured_at.isoformat() if quote.captured_at else None,
        "delivery": {
            "city": quote.delivery_city,
            "state": quote.delivery_state,
            "notes": quote.delivery_notes,
        },
        "description": quote.description,
        "notes_raw": quote.notes_raw,
        "currency": quote.currency,
        "created_at": quote.created_at.isoformat() if quote.created_at else "",
        "items": [
            {
                "id": str(item.id),
                "line_no": item.line_no,
                "product_code_raw": item.product_code_raw,
                "product_name_raw": item.product_name_raw,
                "normalized_sku": item.normalized_sku,
                "qty": item.qty,
                "uom": item.uom,
                "brand_pref": item.brand_pref,
                "specs": item.specs,
                "comments": item.comments,
            }
            for item in items
        ],
        "attachments": [
            {
                "id": str(att.id),
                "filename": att.filename,
                "mime_type": att.mime_type,
                "size_bytes": att.size_bytes,
                "storage_uri": att.storage_uri,
                "download_status": att.download_status,
            }
            for att in attachments
        ],
    }


# ============================================================================
# Exportação CSV
# ============================================================================

@router.get("/export/csv")
async def export_quotes_csv(
    portal: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Exporta cotações em formato CSV."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    q = select(Quote)
    if portal:
        q = q.where(Quote.portal == portal)
    if status:
        q = q.where(Quote.status == _parse_status(status))
    if tenant_id:
        q = q.where(Quote.tenant_id == tenant_id)
    
    q = q.order_by(Quote.created_at.desc()).limit(1000)
    result = await db.execute(q)
    quotes = result.scalars().all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        "tenant_id", "portal", "external_id", "quote_id", "status",
        "published_at", "deadline", "captured_at",
        "buyer_name", "buyer_type", "delivery_city", "delivery_state",
        "description", "created_at"
    ])
    
    for quote in quotes:
        writer.writerow([
            quote.tenant_id or "",
            quote.portal,
            quote.external_id or "",
            str(quote.id),
            quote.status.value if hasattr(quote.status, 'value') else quote.status,
            quote.published_at.isoformat() if quote.published_at else "",
            quote.deadline.isoformat() if quote.deadline else "",
            quote.captured_at.isoformat() if quote.captured_at else "",
            quote.buyer_name or "",
            quote.buyer_type.value if quote.buyer_type else "",
            quote.delivery_city or "",
            quote.delivery_state or "",
            (quote.description or "")[:200],
            quote.created_at.isoformat() if quote.created_at else "",
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=quotes_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    )


# ============================================================================
# Orçamentos
# ============================================================================

@router.post("/{quote_id}/budget")
async def create_budget(
    quote_id: UUID,
    body: BudgetCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Cria orçamento para uma cotação."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    
    budget = QuoteBudget(
        quote_id=quote_id,
        tenant_id=quote.tenant_id,
        items=body.items,
        total_value=body.total_value,
        payment_terms=body.payment_terms,
        delivery_days=body.delivery_days,
        validity_days=body.validity_days,
        notes=body.notes,
        status="draft",
    )
    db.add(budget)
    await db.flush()
    await db.refresh(budget)
    await db.commit()
    
    return {"id": str(budget.id), "status": "draft"}


@router.post("/{quote_id}/budget/{budget_id}/approve")
async def approve_budget(
    quote_id: UUID,
    budget_id: UUID,
    body: BudgetApprove,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Aprova orçamento para envio."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    result = await db.execute(
        select(QuoteBudget).where(
            QuoteBudget.id == budget_id,
            QuoteBudget.quote_id == quote_id,
        )
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    
    if budget.status != "draft":
        raise HTTPException(status_code=400, detail="Budget already approved or submitted")
    
    budget.status = "approved"
    budget.approved_by = body.approved_by
    budget.approved_at = datetime.utcnow()
    await db.commit()
    
    return {"status": "approved"}


@router.post("/{quote_id}/budget/{budget_id}/submit")
async def submit_budget(
    quote_id: UUID,
    budget_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Submete orçamento (marca como enviado)."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    result = await db.execute(
        select(QuoteBudget).where(
            QuoteBudget.id == budget_id,
            QuoteBudget.quote_id == quote_id,
        )
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    
    budget.status = "submitted"
    budget.submitted_at = datetime.utcnow()
    
    quote_result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = quote_result.scalar_one_or_none()
    if quote:
        quote.status = QuoteStatus.sent
    
    await db.commit()
    
    return {"status": "submitted"}


# ============================================================================
# Webhook ERP
# ============================================================================

@router.post("/webhook/erp")
async def erp_webhook(
    body: ErpWebhookPayload,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(None),
    authorization: str | None = Header(None),
):
    """
    Webhook para receber eventos do ERP.
    
    Eventos suportados:
    - quotation.synced: ERP sincronizou cotação
    - quotation.won: Cotação ganha
    - quotation.lost: Cotação perdida
    """
    if settings.INGEST_API_KEY and not _check_ingest_key(x_api_key, authorization):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    
    try:
        quote_uuid = UUID(body.quotation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid quotation_id")
    
    result = await db.execute(select(Quote).where(Quote.id == quote_uuid))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    
    if body.event == "quotation.synced":
        budget_result = await db.execute(
            select(QuoteBudget).where(QuoteBudget.quote_id == quote_uuid).order_by(QuoteBudget.created_at.desc())
        )
        budget = budget_result.scalar_one_or_none()
        if budget:
            budget.erp_synced = True
            budget.erp_sync_at = datetime.utcnow()
    
    elif body.event == "quotation.won":
        quote.status = QuoteStatus.won
    
    elif body.event == "quotation.lost":
        quote.status = QuoteStatus.lost
    
    else:
        raise HTTPException(status_code=400, detail=f"Unknown event: {body.event}")
    
    await db.commit()
    
    return {"status": "processed", "event": body.event}


@router.get("/webhook/erp/pending")
async def get_pending_for_erp(
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(None),
    authorization: str | None = Header(None),
):
    """
    Lista cotações pendentes de sincronização com ERP.
    Endpoint para ERP fazer pull de novas cotações.
    """
    if settings.INGEST_API_KEY and not _check_ingest_key(x_api_key, authorization):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    
    q = select(Quote).where(Quote.status.in_([QuoteStatus.open, QuoteStatus.pending]))
    if tenant_id:
        q = q.where(Quote.tenant_id == tenant_id)
    
    q = q.order_by(Quote.created_at.desc()).limit(limit)
    result = await db.execute(q)
    quotes = result.scalars().all()
    
    return {
        "count": len(quotes),
        "items": [
            {
                "id": str(quote.id),
                "external_id": quote.external_id,
                "portal": quote.portal,
                "status": quote.status.value if hasattr(quote.status, 'value') else quote.status,
                "deadline": quote.deadline.isoformat() if quote.deadline else None,
                "buyer_name": quote.buyer_name,
                "delivery_city": quote.delivery_city,
                "delivery_state": quote.delivery_state,
                "links": {
                    "detail": f"/api/quotes/{quote.id}",
                }
            }
            for quote in quotes
        ]
    }


# ============================================================================
# Métricas RPA
# ============================================================================

@router.get("/rpa/runs")
async def list_rpa_runs(
    portal: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Lista execuções RPA."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    q = select(RpaRun)
    if portal:
        q = q.where(RpaRun.portal_name == portal)
    if status:
        try:
            q = q.where(RpaRun.status == RpaRunStatus(status))
        except ValueError:
            pass
    
    q = q.order_by(RpaRun.created_at.desc()).limit(limit)
    result = await db.execute(q)
    runs = result.scalars().all()
    
    return {
        "items": [
            {
                "id": str(run.id),
                "portal": run.portal_name,
                "status": run.status.value if hasattr(run.status, 'value') else run.status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "duration_seconds": run.duration_seconds,
                "quotes_found": run.quotes_found,
                "quotes_new": run.quotes_new,
                "items_captured": run.items_captured,
                "captcha_encountered": run.captcha_encountered,
                "login_failed": run.login_failed,
                "error_message": run.error_message,
            }
            for run in runs
        ]
    }


@router.get("/rpa/stats")
async def get_rpa_stats(
    portal: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Estatísticas de execuções RPA."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    base_q = select(RpaRun)
    if portal:
        base_q = base_q.where(RpaRun.portal_name == portal)
    
    total = (await db.execute(
        select(func.count()).select_from(base_q.subquery())
    )).scalar() or 0
    
    success = (await db.execute(
        select(func.count()).select_from(
            base_q.where(RpaRun.status == RpaRunStatus.success).subquery()
        )
    )).scalar() or 0
    
    failed = (await db.execute(
        select(func.count()).select_from(
            base_q.where(RpaRun.status == RpaRunStatus.failed).subquery()
        )
    )).scalar() or 0
    
    captcha_count = (await db.execute(
        select(func.count()).select_from(
            base_q.where(RpaRun.captcha_encountered == True).subquery()
        )
    )).scalar() or 0
    
    return {
        "total_runs": total,
        "successful_runs": success,
        "failed_runs": failed,
        "success_rate": (success / total * 100) if total > 0 else 0,
        "captcha_encounters": captcha_count,
    }
