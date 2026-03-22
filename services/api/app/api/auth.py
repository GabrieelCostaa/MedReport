import re
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models import User, UserRole
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user_id,
)
from app.core.config import settings

router = APIRouter()
token_router = APIRouter()

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


@router.post("/register")
async def register(
    body: RegisterIn,
    db: AsyncSession = Depends(get_db),
):
    """Cadastro de novo usuário."""
    # Verifica se e-mail já existe
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="E-mail já cadastrado",
        )
    # Valida role
    valid_roles = {r.value for r in UserRole}
    if body.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Role inválido. Use: {', '.join(valid_roles)}",
        )
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
    db.add(user)
    await db.flush()
    await db.refresh(user)
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
            legal_basis_acknowledged=False,
        ),
    }


@token_router.post("/token")
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
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


@router.get("/me")
async def me(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
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
        raise HTTPException(status_code=401, detail="Not authenticated")
    if body.crm and not CRM_REGEX.match(body.crm):
        raise HTTPException(status_code=422, detail="CRM inválido. Use apenas dígitos (4-8 caracteres).")
    if body.crm_uf and body.crm_uf.upper() not in VALID_UFS:
        raise HTTPException(status_code=422, detail=f"UF inválida: {body.crm_uf}")

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

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
        raise HTTPException(status_code=401, detail="Not authenticated")
    from datetime import datetime
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.legal_basis_acknowledged = True
    user.legal_basis_at = datetime.utcnow()
    await db.commit()
    return {}
