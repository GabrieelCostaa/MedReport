import logging
import re
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

from app.db.session import get_db
from app.db.models import User, UserRole
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user_id,
    get_raw_token,
    revoke_token,
)
from jose import jwt as jose_jwt
from app.core.config import settings

router = APIRouter()
token_router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

VALID_UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO",
    "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
    "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}
CRM_REGEX = re.compile(r"^\d{4,8}$")


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    nome: str | None = None
    crm: str | None = None
    crm_uf: str | None = None
    legal_basis_acknowledged: bool

    class Config:
        from_attributes = True


class RegisterIn(BaseModel):
    email: str
    password: str
    role: str = "medico"
    nome: str | None = None
    crm: str | None = None
    crm_uf: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if settings.TESTING_MODE:
            if len(v) < 6:
                raise ValueError("Senha deve ter ao menos 6 caracteres")
            return v
        if len(v) < 8:
            raise ValueError("Senha deve ter ao menos 8 caracteres")
        if not any(c.isupper() for c in v):
            raise ValueError("Senha deve conter ao menos uma letra maiúscula")
        if not any(c.islower() for c in v):
            raise ValueError("Senha deve conter ao menos uma letra minúscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("Senha deve conter ao menos um número")
        return v


def _register_rate_limit() -> str:
    return "1000/hour" if settings.TESTING_MODE else "5/hour"


def _login_rate_limit() -> str:
    return "1000/minute" if settings.TESTING_MODE else "10/minute"


@router.post("/register")
@limiter.limit(_register_rate_limit)
async def register(
    request: Request,
    body: RegisterIn,
    db: AsyncSession = Depends(get_db),
):
    """Cadastro de novo usuário."""
    ip = request.client.host if request.client else "unknown"
    # Verifica se e-mail já existe — mensagem genérica para não confirmar existência
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        logger.warning("auth.register.duplicate email_hash=%s ip=%s", hash(body.email), ip)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Não foi possível criar a conta. Verifique os dados e tente novamente.",
        )
    # Valida role
    valid_roles = {r.value for r in UserRole}
    if body.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Role inválido. Use: {', '.join(valid_roles)}",
        )
    if not settings.TESTING_MODE:
        # Valida nome (não vazio se fornecido)
        if body.nome is not None and not body.nome.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Nome não pode ser vazio.",
            )
        # Valida CRM e UF se fornecidos
        if body.crm and not CRM_REGEX.match(body.crm):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="CRM inválido. Use apenas dígitos (4-8 caracteres).",
            )
        if body.crm_uf and body.crm_uf.upper() not in VALID_UFS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"UF inválida: {body.crm_uf}",
            )
    user = User(
        email=body.email,
        hashed_password=get_password_hash(body.password),
        role=body.role,
        nome=body.nome,
        crm=body.crm,
        crm_uf=body.crm_uf.upper() if body.crm_uf else None,
    )
    if settings.TESTING_MODE:
        from datetime import datetime
        user.legal_basis_acknowledged = True
        user.legal_basis_at = datetime.utcnow()
    db.add(user)
    await db.flush()
    await db.refresh(user)
    logger.info("auth.register.success user_id=%s role=%s ip=%s", user.id, user.role, ip)
    # Gera token automaticamente (login após registro)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserOut(
            id=str(user.id),
            email=user.email,
            role=user.role.value if hasattr(user.role, 'value') else user.role,
            nome=user.nome,
            crm=user.crm,
            crm_uf=user.crm_uf,
            legal_basis_acknowledged=user.legal_basis_acknowledged or False,
        ),
    }


@token_router.post("/token")
@limiter.limit(_login_rate_limit)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        logger.warning("auth.login.failed email=%s ip=%s", form.username, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    logger.info("auth.login.success user_id=%s ip=%s", user.id, ip)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserOut(
            id=str(user.id),
            email=user.email,
            role=user.role.value,
            nome=user.nome,
            crm=user.crm,
            crm_uf=user.crm_uf,
            legal_basis_acknowledged=user.legal_basis_acknowledged or False,
        ),
    }


@router.get("/config")
async def auth_config():
    """Configuração pública do auth — frontend usa para ajustar o formulário."""
    return {"testing_mode": settings.TESTING_MODE}


@router.get("/me")
async def me(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    if not user_id:
        raise HTTPException(status_code=401, detail="Autenticação necessária")
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return UserOut(
        id=str(user.id),
        email=user.email,
        role=user.role.value,
        nome=user.nome,
        crm=user.crm,
        crm_uf=user.crm_uf,
        legal_basis_acknowledged=user.legal_basis_acknowledged or False,
    )


class UpdateProfileIn(BaseModel):
    nome: str | None = None
    crm: str | None = None
    crm_uf: str | None = None


@router.patch("/me")
async def update_me(
    body: UpdateProfileIn,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    if not user_id:
        raise HTTPException(status_code=401, detail="Autenticação necessária")
    if body.crm and not CRM_REGEX.match(body.crm):
        raise HTTPException(status_code=422, detail="CRM inválido. Use apenas dígitos (4-8 caracteres).")
    if body.crm_uf and body.crm_uf.upper() not in VALID_UFS:
        raise HTTPException(status_code=422, detail=f"UF inválida: {body.crm_uf}")

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if body.nome is not None:
        user.nome = body.nome
    if body.crm is not None:
        user.crm = body.crm
    if body.crm_uf is not None:
        user.crm_uf = body.crm_uf.upper()

    await db.commit()
    await db.refresh(user)
    return UserOut(
        id=str(user.id),
        email=user.email,
        role=user.role.value,
        nome=user.nome,
        crm=user.crm,
        crm_uf=user.crm_uf,
        legal_basis_acknowledged=user.legal_basis_acknowledged or False,
    )


@token_router.post("/logout")
async def logout(
    request: Request,
    token: str = Depends(get_raw_token),
):
    """Invalida o token atual adicionando seu jti à blacklist."""
    if token:
        try:
            payload = jose_jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            jti = payload.get("jti")
            if jti:
                revoke_token(jti)
                ip = request.client.host if request.client else "unknown"
                logger.info("auth.logout.success jti=%s ip=%s", jti, ip)
        except Exception:
            pass  # Token já expirado ou inválido — logout é idempotente
    return {"detail": "Logout realizado com sucesso"}


@router.post("/legal-basis")
async def acknowledge_legal_basis(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Registra ciência das bases legais para tratamento de dados (LGPD Art. 11).
    Não é apenas consentimento - inclui obrigação legal (TISS), tutela da saúde, etc.
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="Autenticação necessária")
    from datetime import datetime
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.legal_basis_acknowledged = True
    user.legal_basis_at = datetime.utcnow()
    await db.commit()
    return {}
