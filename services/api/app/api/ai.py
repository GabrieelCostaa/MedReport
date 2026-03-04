from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import get_current_user_id

router = APIRouter()


class ChatIn(BaseModel):
    message: str


class ChatOut(BaseModel):
    reply: str
    report_id: str | None = None


@router.post("/chat")
async def chat(
    body: ChatIn,
    user_id: str = Depends(get_current_user_id),
):
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Placeholder: em produção integrar LLM (OpenAI/etc) e serviço de relatórios para criar report_id quando o assistente tiver dados suficientes
    reply = (
        "Recebi sua mensagem. Para criar o relatório automaticamente, informe: CID, diagnóstico, "
        "descrição da cirurgia e materiais necessários. Você também pode usar o formulário na aba 'Formulário'."
    )
    return ChatOut(reply=reply, report_id=None)
