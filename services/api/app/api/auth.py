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


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    legal_basis_acknowledged: bool

    class Config:
        from_attributes = True


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
