"""
Serviço de consulta à ANVISA para validação de registros de produtos OPME.

Estratégia: API Gateway (OAuth2) como principal, banco local como fallback.

Fluxo:
  1. API Gateway ANVISA (OAuth2 client_credentials) → dados frescos
  2. Fallback: banco local (anvisa_products) → dados do último download
  3. Salva resultado da API no banco para cache persistente

Baseado na implementação do DMC (backend/connectors/anvisa.py).
"""
import logging
import time
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AnvisaProduct, AnvisaStatus

logger = logging.getLogger(__name__)


# ── OAuth2 Token Cache ────────────────────────────────────────────────────

_token_cache = {
    "access_token": None,
    "expires_at": 0.0,
}


async def _get_token() -> Optional[str]:
    """
    Obtém token OAuth2 via client_credentials grant.
    Cacheia em memória com buffer de 60s antes da expiração.
    """
    if not settings.ANVISA_CLIENT_ID or not settings.ANVISA_CLIENT_SECRET:
        logger.debug("ANVISA credentials not configured, skipping API")
        return None

    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                settings.ANVISA_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.ANVISA_CLIENT_ID,
                    "client_secret": settings.ANVISA_CLIENT_SECRET,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()
            _token_cache["access_token"] = data["access_token"]
            _token_cache["expires_at"] = now + data.get("expires_in", 3600) - 60
            logger.info("ANVISA OAuth2 token obtained (expires in %ds)", data.get("expires_in", 3600))
            return _token_cache["access_token"]
    except Exception as e:
        logger.warning("ANVISA OAuth2 token failed: %s", e)
        return None


# ── API Gateway Queries ───────────────────────────────────────────────────

@dataclass
class AnvisaResult:
    """Resultado padronizado de consulta ANVISA."""
    registro: str
    nome_comercial: str = ""
    nome_tecnico: str = ""
    fabricante: str = ""
    classe_risco: str = ""
    status: str = ""  # ativo, vencido, suspenso, cancelado
    data_validade: Optional[datetime] = None
    fonte: str = ""  # "api_gateway" | "banco_local" | "not_found"
    sucesso: bool = False
    dados_raw: Optional[dict] = None


async def _consultar_api_gateway(registro: str) -> Optional[AnvisaResult]:
    """
    Consulta registro na API Gateway ANVISA (OAuth2).
    Retorna None se falhar (para cair no fallback).
    """
    token = await _get_token()
    if not token:
        return None

    url = f"{settings.ANVISA_GATEWAY_URL}/consulta/saude"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "filter": {"numeroRegistro": registro},
        "page": 1,
        "pageSize": 10,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.ANVISA_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)

            if resp.status_code == 401:
                # Token expirado — limpar cache e tentar novamente
                _token_cache["access_token"] = None
                _token_cache["expires_at"] = 0
                token = await _get_token()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    resp = await client.post(url, json=payload, headers=headers)

            resp.raise_for_status()
            data = resp.json()

        # Parse response — formato paginado: {"content": [...], "pageable": {...}}
        items = data.get("content", []) if isinstance(data, dict) else data
        if isinstance(items, list) and not items:
            return AnvisaResult(registro=registro, fonte="api_gateway", sucesso=False)

        item = items[0] if isinstance(items, list) else items

        # Normalizar status (campo "situacao" pode ser string ou nested)
        situacao_raw = ""
        if isinstance(item.get("situacao"), str):
            situacao_raw = item["situacao"].upper()
        elif isinstance(item.get("situacao"), dict):
            situacao_raw = (item["situacao"].get("descricao", "") or "").upper()

        # Verificar flag "cancelado" (int: 0 ou 1)
        is_cancelado = item.get("cancelado", 0)
        if isinstance(is_cancelado, int) and is_cancelado == 1:
            situacao_raw = "CANCELADO"

        # Verificar vencimento
        vencimento = item.get("vencimento", {})
        is_vencido = vencimento.get("vencido", False) if isinstance(vencimento, dict) else False

        status_map = {
            "VIGENTE": "ativo", "ATIVO": "ativo", "VÁLIDO": "ativo",
            "VENCIDO": "vencido", "CANCELADO": "cancelado", "INVÁLIDO": "cancelado",
            "SUSPENSO": "suspenso",
        }
        status = status_map.get(situacao_raw, "vencido" if is_vencido else "ativo")

        # Parse data_validade (pode ser epoch millis ou string)
        data_val = None
        val_raw = item.get("dataVencimento") or (vencimento.get("data") if isinstance(vencimento, dict) else None)
        if isinstance(val_raw, (int, float)) and val_raw > 0:
            # Epoch milliseconds
            data_val = datetime.fromtimestamp(val_raw / 1000, tz=timezone.utc)
        elif isinstance(val_raw, str) and val_raw not in ("VIGENTE", ""):
            for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
                try:
                    data_val = datetime.strptime(val_raw.split("T")[0], fmt)
                    break
                except ValueError:
                    continue

        # Extrair empresa (pode ser nested dict)
        empresa = item.get("empresa", {})
        fabricante = ""
        if isinstance(empresa, dict):
            fabricante = empresa.get("razaoSocial", "") or ""
        else:
            fabricante = item.get("razaoSocial", "") or item.get("fabricante", "") or ""

        return AnvisaResult(
            registro=registro,
            nome_comercial=item.get("produto", "") or item.get("nomeProduto", "") or item.get("nomeComercial", "") or "",
            nome_tecnico=item.get("nomeTecnico", "") or "",
            fabricante=fabricante,
            classe_risco=item.get("siglaRiscoProduto", "") or item.get("classeRisco", "") or "",
            status=status,
            data_validade=data_val,
            fonte="api_gateway",
            sucesso=True,
            dados_raw=item,
        )

    except httpx.TimeoutException:
        logger.warning("ANVISA API Gateway timeout for %s", registro)
        return None
    except Exception as e:
        logger.warning("ANVISA API Gateway error for %s: %s", registro, e)
        return None


# ── Banco Local (Fallback) ────────────────────────────────────────────────

async def _consultar_banco_local(db: AsyncSession, registro: str) -> Optional[AnvisaResult]:
    """Consulta registro no banco local (anvisa_products)."""
    try:
        result = await db.execute(
            select(AnvisaProduct).where(AnvisaProduct.registro == registro)
        )
        record = result.scalar_one_or_none()
        if not record:
            return None

        return AnvisaResult(
            registro=registro,
            nome_comercial=record.nome_comercial or "",
            nome_tecnico=record.nome_tecnico or "",
            fabricante=record.fabricante or "",
            classe_risco=record.classe_risco or "",
            status=record.status.value if record.status else "ativo",
            data_validade=record.data_validade,
            fonte="banco_local",
            sucesso=True,
            dados_raw=record.dados_json,
        )
    except Exception as e:
        logger.warning("ANVISA banco local error for %s: %s", registro, e)
        return None


# ── Persistir resultado da API no banco ───────────────────────────────────

async def _persist_to_db(db: AsyncSession, result: AnvisaResult):
    """Salva/atualiza resultado da API no banco para cache persistente."""
    if not result.sucesso or result.fonte != "api_gateway":
        return

    try:
        existing = await db.execute(
            select(AnvisaProduct).where(AnvisaProduct.registro == result.registro)
        )
        record = existing.scalar_one_or_none()

        status_enum = getattr(AnvisaStatus, result.status, AnvisaStatus.ativo)

        if record:
            record.nome_comercial = result.nome_comercial or record.nome_comercial
            record.nome_tecnico = result.nome_tecnico or record.nome_tecnico
            record.fabricante = result.fabricante or record.fabricante
            record.classe_risco = result.classe_risco or record.classe_risco
            record.status = status_enum
            record.data_validade = result.data_validade or record.data_validade
            record.data_consulta = datetime.now(timezone.utc)
            record.dados_json = result.dados_raw
        else:
            record = AnvisaProduct(
                registro=result.registro,
                nome_comercial=result.nome_comercial,
                nome_tecnico=result.nome_tecnico,
                fabricante=result.fabricante,
                status=status_enum,
                classe_risco=result.classe_risco,
                data_validade=result.data_validade,
                data_consulta=datetime.now(timezone.utc),
                dados_json=result.dados_raw,
            )
            db.add(record)

        await db.flush()
    except Exception as e:
        logger.warning("ANVISA persist failed for %s: %s", result.registro, e)


# ── API Pública ───────────────────────────────────────────────────────────

async def consultar_registro(
    db: AsyncSession,
    registro: str,
) -> AnvisaResult:
    """
    Consulta registro ANVISA com fallback.

    Fluxo:
      1. API Gateway (OAuth2) → dados frescos, salva no banco
      2. Banco local → fallback se API falhar
      3. Not found → retorna resultado vazio

    Args:
        db: Database session
        registro: Número de registro ANVISA (ex: "80030810056")

    Returns:
        AnvisaResult com dados do produto e fonte da informação
    """
    if not registro:
        return AnvisaResult(registro="", fonte="not_found", sucesso=False)

    # Normalizar: remover pontos, traços, espaços
    registro_clean = registro.strip().replace(".", "").replace("-", "").replace(" ", "")

    # 1. Tentar API Gateway (principal)
    api_result = await _consultar_api_gateway(registro_clean)
    if api_result and api_result.sucesso:
        await _persist_to_db(db, api_result)
        logger.info("ANVISA %s: found via API Gateway (%s)", registro_clean, api_result.status)
        return api_result

    # 2. Fallback: banco local
    db_result = await _consultar_banco_local(db, registro_clean)
    if db_result:
        logger.info("ANVISA %s: found in local DB (fallback)", registro_clean)
        return db_result

    # 3. Not found
    logger.info("ANVISA %s: not found in API or DB", registro_clean)
    return AnvisaResult(registro=registro_clean, fonte="not_found", sucesso=False)


async def validar_registro_ativo(
    db: AsyncSession,
    registro: str,
) -> dict:
    """
    Valida se registro ANVISA está ativo (STF Critério 5).

    Returns:
        {
            "valido": True/False,
            "status": "ativo"/"vencido"/"cancelado"/"suspenso"/"not_found",
            "nome_comercial": "...",
            "classe_risco": "...",
            "fonte": "api_gateway"/"banco_local"/"not_found",
            "motivo": "Explicação quando inválido"
        }
    """
    result = await consultar_registro(db, registro)

    if not result.sucesso:
        return {
            "valido": False,
            "status": "not_found",
            "nome_comercial": "",
            "classe_risco": "",
            "fonte": result.fonte,
            "motivo": f"Registro {registro} não encontrado na base ANVISA",
        }

    valido = result.status == "ativo"
    motivo = ""
    if not valido:
        motivos = {
            "vencido": f"Registro {registro} com validade expirada",
            "cancelado": f"Registro {registro} foi cancelado pela ANVISA",
            "suspenso": f"Registro {registro} está suspenso pela ANVISA",
        }
        motivo = motivos.get(result.status, f"Status: {result.status}")

    return {
        "valido": valido,
        "status": result.status,
        "nome_comercial": result.nome_comercial,
        "classe_risco": result.classe_risco,
        "fonte": result.fonte,
        "motivo": motivo,
        "data_validade": result.data_validade.isoformat() if result.data_validade else None,
    }
