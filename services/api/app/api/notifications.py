"""Notificações: alertas de novas cotações e prazos (stub; em produção integrar email/push)."""
from fastapi import APIRouter, Depends
from app.core.security import get_current_user_id

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(user_id: str = Depends(get_current_user_id)):
    if not user_id:
        return {"items": []}
    # Stub: em produção buscar de tabela notifications filtrada por user_id
    return {"items": []}


@router.put("/preferences")
async def update_preferences(
    body: dict,
    user_id: str = Depends(get_current_user_id),
):
    """Preferências: email, in-app, etc."""
    if not user_id:
        return {}
    return {"ok": True}
