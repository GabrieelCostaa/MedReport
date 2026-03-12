"""
ETL: Consulta de status de registro Anvisa para Produtos para Saúde.

Portal: https://consultas.anvisa.gov.br/#/saude/
Critério 5 do STF (ADI 7.265): Registro ativo na Anvisa é requisito obrigatório.
"""
import asyncio
import re
from datetime import datetime

import httpx
from sqlalchemy import select

ANVISA_API_BASE = "https://consultas.anvisa.gov.br/api/consulta/saude/produto"


async def query_anvisa_product(registro: str) -> dict | None:
    """
    Consulta a API pública da Anvisa para status de registro de produto para saúde.
    Retorna dict com dados ou None se falhar.
    """
    clean_reg = re.sub(r"[^\dX]", "", registro.upper())
    if not clean_reg:
        return None

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        try:
            resp = await client.get(
                f"{ANVISA_API_BASE}/{clean_reg}",
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 200:
                return resp.json()
            resp = await client.get(
                ANVISA_API_BASE,
                params={"filter[registro]": clean_reg},
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    return data[0]
                if isinstance(data, dict) and data.get("content"):
                    return data["content"][0] if data["content"] else None
        except (httpx.HTTPError, KeyError, IndexError):
            pass

    return None


def parse_anvisa_response(data: dict) -> dict:
    """Normaliza a resposta da Anvisa para nosso modelo."""
    if not data:
        return {
            "registro": "",
            "nome_comercial": None,
            "fabricante": None,
            "status": "desconhecido",
            "data_validade": None,
            "classe_risco": None,
            "dados_json": None,
        }

    situacao = (data.get("situacao") or data.get("situacaoRegistro") or
                data.get("status") or "").lower()

    status_map = {
        "válido": "ativo", "valido": "ativo", "ativo": "ativo", "vigente": "ativo",
        "vencido": "vencido", "expirado": "vencido",
        "suspenso": "suspenso",
        "cancelado": "cancelado", "caduco": "cancelado",
    }
    parsed_status = "ativo"
    for key, val in status_map.items():
        if key in situacao:
            parsed_status = val
            break

    validade_str = data.get("dataValidade") or data.get("dataVencimento") or data.get("validade")
    validade = None
    if validade_str:
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                validade = datetime.strptime(validade_str[:19], fmt)
                break
            except (ValueError, TypeError):
                continue

    if validade and validade < datetime.utcnow() and parsed_status == "ativo":
        parsed_status = "vencido"

    return {
        "registro": data.get("registro") or data.get("numeroRegistro") or "",
        "nome_comercial": data.get("nomeProduto") or data.get("nomeComercial"),
        "fabricante": data.get("razaoSocial") or data.get("fabricante") or data.get("empresa"),
        "status": parsed_status,
        "data_validade": validade,
        "classe_risco": data.get("classeRisco") or data.get("classe"),
        "dados_json": data,
    }


async def check_and_update_anvisa(db_session, registro: str) -> dict:
    """Consulta Anvisa e atualiza/cria registro no banco."""
    from app.db.models import AnvisaProduct, AnvisaStatus

    raw = await query_anvisa_product(registro)
    parsed = parse_anvisa_response(raw)

    status_enum = getattr(AnvisaStatus, parsed["status"], AnvisaStatus.ativo)

    existing = await db_session.execute(
        select(AnvisaProduct).where(AnvisaProduct.registro == registro)
    )
    existing = existing.scalar_one_or_none()

    if existing:
        existing.nome_comercial = parsed["nome_comercial"] or existing.nome_comercial
        existing.fabricante = parsed["fabricante"] or existing.fabricante
        existing.status = status_enum
        existing.data_validade = parsed["data_validade"]
        existing.classe_risco = parsed["classe_risco"]
        existing.data_consulta = datetime.utcnow()
        existing.dados_json = parsed["dados_json"]
        action = "updated"
    else:
        product = AnvisaProduct(
            registro=registro,
            nome_comercial=parsed["nome_comercial"],
            fabricante=parsed["fabricante"],
            status=status_enum,
            data_validade=parsed["data_validade"],
            classe_risco=parsed["classe_risco"],
            data_consulta=datetime.utcnow(),
            dados_json=parsed["dados_json"],
        )
        db_session.add(product)
        action = "created"

    await db_session.commit()
    return {"action": action, "registro": registro, "status": parsed["status"]}


async def run_etl(db_session=None, registros: list[str] | None = None):
    """Verifica status Anvisa para uma lista de registros."""
    if not registros:
        print("[ANVISA ETL] Nenhum registro para verificar")
        return {"checked": 0}

    results = []
    for reg in registros:
        print(f"[ANVISA ETL] Consultando {reg}...")
        if db_session:
            r = await check_and_update_anvisa(db_session, reg)
        else:
            raw = await query_anvisa_product(reg)
            r = parse_anvisa_response(raw)
        results.append(r)

    print(f"[ANVISA ETL] {len(results)} registros verificados")
    return {"checked": len(results), "results": results}


if __name__ == "__main__":
    asyncio.run(run_etl(registros=["80117900XXX"]))
