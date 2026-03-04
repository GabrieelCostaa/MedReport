"""Cria tabelas e insere dados iniciais (seed)."""
import asyncio
from sqlalchemy import text
from app.db.session import engine, Base, AsyncSessionLocal
from app.db.models import User, TussTerm, UserRole
from app.core.security import get_password_hash


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed():
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        r = await db.execute(select(User).where(User.email == "medico@opme.com"))
        if r.scalar_one_or_none():
            return
        user = User(
            email="medico@opme.com",
            hashed_password=get_password_hash("senha123"),
            role=UserRole.medico,
            consent_accepted=False,
        )
        db.add(user)
        await db.flush()
        # TUSS sample (em produção virá do site ANS)
        for code, term in [
            ("30701020", "Radiografia de tórax"),
            ("30901047", "Artroplastia total de joelho"),
            ("30901055", "Artroplastia total de quadril"),
            ("31001010", "Prótese de quadril"),
            ("31001029", "Prótese de joelho"),
        ]:
            t = TussTerm(code=code, term=term, table_source="procedimentos")
            db.add(t)
        await db.commit()


async def main():
    await create_tables()
    await seed()
    print("DB initialized and seeded.")


if __name__ == "__main__":
    asyncio.run(main())
