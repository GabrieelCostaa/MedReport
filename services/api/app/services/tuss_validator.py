"""
Validador TUSS + TISS + Anvisa.

Valida:
- Código TUSS 19 contra base oficial (tuss_materials)
- Campo/guia correto segundo TISS Organizacional (tiss_rules)
- Registro Anvisa ativo (anvisa_products)
- REGRA CRÍTICA: TUSS 19 só pode ir para Anexo OPME, NUNCA para Honorários
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class TussValidation:
    codigo: str
    valido: bool
    nome: Optional[str] = None
    grupo: Optional[str] = None
    mensagem: str = ""


@dataclass
class TissValidation:
    tipo_guia: str
    campo: str
    codigo: str
    permitido: bool
    mensagem: str = ""


@dataclass
class AnvisaStatusResult:
    registro: str
    status: str  # ativo | vencido | suspenso | cancelado | desconhecido
    data_validade: Optional[datetime] = None
    alerta: Optional[str] = None


class TussValidator:
    """Validador de códigos TUSS, regras TISS e status Anvisa."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def validate_opme_code(self, codigo_tuss: str) -> TussValidation:
        """Valida código TUSS contra Tabela 19 (materiais) E Tabela 22 (procedimentos)."""
        from app.db.models import TussMaterial, TussProcedure

        # Check Table 19 (Materials/OPME) first
        result = await self.db.execute(
            select(TussMaterial).where(TussMaterial.codigo_tuss == codigo_tuss)
        )
        material = result.scalar_one_or_none()

        if material:
            if not material.ativo:
                return TussValidation(
                    codigo=codigo_tuss,
                    valido=False,
                    nome=material.nome,
                    grupo=material.grupo,
                    mensagem=f"Código TUSS {codigo_tuss} existe mas está inativo",
                )
            return TussValidation(
                codigo=codigo_tuss,
                valido=True,
                nome=material.nome,
                grupo=material.grupo,
                mensagem="Código TUSS válido e ativo (Tabela 19 — Material/OPME)",
            )

        # Check Table 22 (Procedures)
        result = await self.db.execute(
            select(TussProcedure).where(TussProcedure.codigo_tuss == codigo_tuss)
        )
        procedure = result.scalar_one_or_none()

        if procedure:
            if not procedure.ativo:
                return TussValidation(
                    codigo=codigo_tuss,
                    valido=False,
                    nome=procedure.nome,
                    grupo=procedure.grupo,
                    mensagem=f"Código TUSS {codigo_tuss} existe mas está inativo",
                )
            return TussValidation(
                codigo=codigo_tuss,
                valido=True,
                nome=procedure.nome,
                grupo=procedure.grupo,
                mensagem="Código TUSS válido e ativo (Tabela 22 — Procedimento)",
            )

        return TussValidation(
            codigo=codigo_tuss,
            valido=False,
            mensagem=f"Código TUSS {codigo_tuss} não encontrado na base oficial (Tabelas 19 e 22)",
        )

    async def validate_tiss_field(self, tipo_guia: str, campo: str, codigo: str) -> TissValidation:
        """
        Valida se código TUSS pode ser usado no campo/guia especificado.
        REGRA CRÍTICA: TUSS 19 (materiais) NUNCA pode ir para campos de Honorários.
        """
        from app.db.models import TissRule

        if campo.lower() in ("honorarios", "honorário", "honorario") and codigo:
            from app.db.models import TussMaterial
            is_material = await self.db.execute(
                select(TussMaterial.codigo_tuss).where(TussMaterial.codigo_tuss == codigo).limit(1)
            )
            if is_material.scalar_one_or_none():
                return TissValidation(
                    tipo_guia=tipo_guia,
                    campo=campo,
                    codigo=codigo,
                    permitido=False,
                    mensagem=(
                        f"GLOSA: Código TUSS 19 '{codigo}' (material/OPME) não pode ser usado "
                        f"em campo de Honorários. Deve ir para Anexo de Solicitação de OPME."
                    ),
                )

        result = await self.db.execute(
            select(TissRule).where(
                TissRule.tipo_guia == tipo_guia,
                TissRule.campo == campo,
            )
        )
        rule = result.scalar_one_or_none()

        if not rule:
            return TissValidation(
                tipo_guia=tipo_guia, campo=campo, codigo=codigo,
                permitido=True, mensagem="Sem regra TISS específica encontrada",
            )

        if rule.regra == "proibido":
            return TissValidation(
                tipo_guia=tipo_guia, campo=campo, codigo=codigo,
                permitido=False,
                mensagem=f"TISS proíbe uso neste campo: {rule.descricao or ''}",
            )

        return TissValidation(
            tipo_guia=tipo_guia, campo=campo, codigo=codigo,
            permitido=True, mensagem=f"TISS: {rule.regra}",
        )

    async def search_materials(self, query: str, limit: int = 20) -> list:
        """Busca materiais TUSS por texto normalizado."""
        from app.db.models import TussMaterial

        normalized_q = query.strip().lower()
        result = await self.db.execute(
            select(TussMaterial).where(
                or_(
                    TussMaterial.display_normalized.contains(normalized_q),
                    TussMaterial.nome.ilike(f"%{query}%"),
                    TussMaterial.codigo_tuss == query.strip(),
                )
            ).limit(limit)
        )
        return result.scalars().all()

    async def check_anvisa_status(self, registro: str) -> AnvisaStatusResult:
        """
        Verifica status do registro ANVISA.
        Estratégia: API Gateway (principal) → banco local (fallback).
        """
        try:
            from app.services.anvisa_service import consultar_registro
            result = await consultar_registro(self.db, registro)

            if result.sucesso:
                alerta = None
                if result.status in ("vencido", "suspenso", "cancelado"):
                    alerta = (
                        f"ALERTA CRÍTICO: Registro Anvisa {registro} está {result.status} "
                        f"(fonte: {result.fonte}). Isto invalida o critério 5 do STF (ADI 7.265)."
                    )
                return AnvisaStatusResult(
                    registro=registro,
                    status=result.status,
                    data_validade=result.data_validade,
                    alerta=alerta,
                )

            return AnvisaStatusResult(
                registro=registro,
                status="desconhecido",
                alerta="Registro Anvisa não encontrado na API Gateway nem no banco local.",
            )
        except Exception as e:
            logger.warning("ANVISA check failed, falling back to DB-only: %s", e)
            # Fallback direto ao banco (comportamento anterior)
            from app.db.models import AnvisaProduct
            result = await self.db.execute(
                select(AnvisaProduct).where(AnvisaProduct.registro == registro)
            )
            product = result.scalar_one_or_none()
            if not product:
                return AnvisaStatusResult(
                    registro=registro,
                    status="desconhecido",
                    alerta="Registro Anvisa não encontrado. Execute verificação.",
                )
            alerta = None
            if product.status.value in ("vencido", "suspenso", "cancelado"):
                alerta = (
                    f"ALERTA CRÍTICO: Registro Anvisa {registro} está {product.status.value}."
                )
            return AnvisaStatusResult(
                registro=registro,
                status=product.status.value,
                data_validade=product.data_validade,
                alerta=alerta,
            )

    async def get_compatible_procedures(self, material_code: str) -> list:
        """Busca procedimentos do Rol potencialmente compatíveis com o material."""
        from app.db.models import RolProcedure

        result = await self.db.execute(
            select(RolProcedure).limit(50)
        )
        return result.scalars().all()
