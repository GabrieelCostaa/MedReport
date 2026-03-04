"""
Mock de integração ERP: endpoints que simulam push/pull de preços e estoque.
Em produção, substituir por conectores reais (webhooks, filas).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.core.security import get_current_user_id

router = APIRouter(prefix="/api/erp", tags=["erp"])


class PriceItem(BaseModel):
    product_code: str
    description: str
    unit_price: float
    currency: str = "BRL"


class StockItem(BaseModel):
    product_code: str
    quantity: int
    warehouse: Optional[str] = None


# Dados mock em memória (em produção: ERP real)
MOCK_PRICES = [
    {"product_code": "PRT-001", "description": "Prótese joelho", "unit_price": 15000.0},
    {"product_code": "PRT-002", "description": "Prótese quadril", "unit_price": 18000.0},
]
MOCK_STOCK = [
    {"product_code": "PRT-001", "quantity": 10, "warehouse": "SP"},
    {"product_code": "PRT-002", "quantity": 5, "warehouse": "SP"},
]


@router.get("/prices")
async def get_prices(user_id: str = Depends(get_current_user_id)):
    """Retorna tabela de preços (pull). ERP real exporia isso ou receberia webhook."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"items": MOCK_PRICES}


@router.get("/stock")
async def get_stock(user_id: str = Depends(get_current_user_id)):
    """Retorna estoque (pull)."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"items": MOCK_STOCK}


@router.post("/quotes/sync")
async def sync_quote_to_erp(
    body: dict,
    user_id: str = Depends(get_current_user_id),
):
    """Simula envio de cotação/orçamento para o ERP (webhook)."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"ok": True, "message": "Mock ERP received quote sync"}
