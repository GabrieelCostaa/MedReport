"""
Auto-enriquecimento de produtos OPME via LLM.

Quando um produto não tem ficha técnica completa (descricao_tecnica,
diferenciais_clinicos, indicacoes), gera automaticamente usando:
1. Dados Anvisa (nome técnico, modelos, fabricante)
2. PubMed (evidências científicas)
3. GPT-4o (síntese da ficha técnica)

Resultado é salvo no banco — primeira consulta gera, próximas são instantâneas.
"""
import json
import logging
from typing import Optional

from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Product, AnvisaProduct

logger = logging.getLogger(__name__)

# Campos que indicam que o produto precisa de enriquecimento
CRITICAL_FIELDS = ["descricao_tecnica", "diferenciais_clinicos"]


def needs_enrichment(product: Product) -> bool:
    """Verifica se o produto precisa de auto-enriquecimento."""
    for field in CRITICAL_FIELDS:
        value = getattr(product, field, None)
        if not value or len(str(value).strip()) < 20:
            return True
    return False


async def _fetch_anvisa_context(db: AsyncSession, product: Product) -> dict:
    """Busca dados complementares da tabela Anvisa."""
    context = {}

    registro = getattr(product, "registro_anvisa", None)
    if not registro:
        return context

    result = await db.execute(
        select(AnvisaProduct).where(AnvisaProduct.registro == registro)
    )
    anvisa = result.scalar_one_or_none()

    if anvisa:
        context["nome_tecnico_anvisa"] = getattr(anvisa, "nome_tecnico", None) or ""
        context["nome_comercial_anvisa"] = anvisa.nome_comercial or ""
        context["fabricante"] = anvisa.fabricante or ""
        context["classe_risco"] = anvisa.classe_risco or ""
        context["status_anvisa"] = anvisa.status.value if anvisa.status else ""
        # Modelos/apresentações (truncar para não estourar prompt)
        modelos = getattr(anvisa, "modelos_descricao", None) or ""
        context["modelos"] = modelos[:2000] if modelos else ""

    return context


async def _fetch_pubmed_context(product: Product, cid: str = "") -> str:
    """Busca artigos PubMed relevantes para o produto."""
    try:
        from app.services.pubmed_service import get_evidences_for_cid
        from app.db.session import AsyncSessionLocal

        # Buscar evidências usando o nome do produto
        async with AsyncSessionLocal() as db:
            articles = await get_evidences_for_cid(
                db, cid or "", product.nome, product.nome,
            )

        if not articles:
            return "Nenhum artigo PubMed encontrado."

        parts = []
        for a in articles[:5]:
            parts.append(
                f"- {a.get('autor', '?')} ({a.get('ano', '?')}): "
                f"{a.get('snippet', '')[:300]}"
            )
        return "\n".join(parts)

    except Exception as e:
        logger.warning("PubMed para enriquecimento falhou: %s", e)
        return ""


ENRICHMENT_PROMPT = """Você é um especialista em dispositivos médicos (OPME) no Brasil.

Com base nos dados abaixo, gere a ficha técnica deste produto médico.

DADOS DISPONÍVEIS:
Nome do produto: {nome}
Linha: {linha}
Registro Anvisa: {registro}
Nome técnico (Anvisa): {nome_tecnico}
Fabricante: {fabricante}
Classe de risco: {classe_risco}
Modelos/apresentações registrados: {modelos}

DADOS TÉCNICOS JÁ CONHECIDOS:
Viscosidade: {viscosidade}
Peso molecular: {peso_molecular}
Concentração: {concentracao}

EVIDÊNCIAS CIENTÍFICAS (PubMed):
{pubmed_context}

REGRAS:
1. Use APENAS informações que possam ser inferidas dos dados acima ou de conhecimento médico estabelecido.
2. NÃO invente dados técnicos específicos (números, percentuais) sem fonte.
3. Se não souber um campo, escreva "Dados não disponíveis na base pública".
4. Descreva o mecanismo de ação do produto de forma técnica e precisa.
5. Para diferenciais, compare com a categoria genérica do dispositivo.

SAÍDA (JSON):
{{
  "descricao_tecnica": "Descrição técnica completa do produto (composição, mecanismo de ação, apresentação). Mínimo 100 caracteres.",
  "diferenciais_clinicos": "Diferenciais clínicos vs alternativas genéricas. Mínimo 100 caracteres.",
  "indicacoes": "Indicações terapêuticas aprovadas. Lista completa.",
  "contraindicacoes": "Contraindicações conhecidas."
}}"""


async def _generate_enrichment(product: Product, anvisa_ctx: dict, pubmed_ctx: str) -> dict:
    """Chama GPT-4o para gerar ficha técnica."""
    import openai

    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY não configurada — enriquecimento impossível")
        return {}

    prompt = ENRICHMENT_PROMPT.format(
        nome=product.nome or "",
        linha=getattr(product, "linha", "") or "",
        registro=getattr(product, "registro_anvisa", "") or "",
        nome_tecnico=anvisa_ctx.get("nome_tecnico_anvisa", ""),
        fabricante=anvisa_ctx.get("fabricante", ""),
        classe_risco=anvisa_ctx.get("classe_risco", ""),
        modelos=anvisa_ctx.get("modelos", "")[:1000],
        viscosidade=getattr(product, "viscosidade", "") or "Não informado",
        peso_molecular=getattr(product, "peso_molecular", "") or "Não informado",
        concentracao=getattr(product, "concentracao", "") or "Não informado",
        pubmed_context=pubmed_ctx or "Nenhuma evidência disponível.",
    )

    client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL_ENRICHMENT,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Gere a ficha técnica completa deste produto médico."},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=2000,
    )

    raw = response.choices[0].message.content
    return json.loads(raw)


async def enrich_product(
    db: AsyncSession,
    product: Product,
    cid: str = "",
    on_progress=None,
) -> bool:
    """
    Auto-enriquece um produto com ficha técnica gerada por LLM.

    Retorna True se o produto foi enriquecido, False se já estava completo
    ou se o enriquecimento falhou.
    """
    if not needs_enrichment(product):
        return False

    logger.info("Auto-enriquecimento iniciado: %s (id=%s)", product.nome, product.id)

    if on_progress:
        await on_progress("enriching", f"Gerando ficha técnica de {product.nome}...")

    try:
        # 1. Buscar contexto Anvisa
        anvisa_ctx = await _fetch_anvisa_context(db, product)

        # 2. Buscar contexto PubMed
        pubmed_ctx = await _fetch_pubmed_context(product, cid)

        # 3. Gerar ficha via LLM
        enrichment = await _generate_enrichment(product, anvisa_ctx, pubmed_ctx)

        if not enrichment:
            logger.warning("Enriquecimento retornou vazio para %s", product.nome)
            return False

        # 4. Atualizar produto no banco (só campos vazios)
        updates = {}
        field_map = {
            "descricao_tecnica": "descricao_tecnica",
            "diferenciais_clinicos": "diferenciais_clinicos",
            "indicacoes": "indicacoes",
            "contraindicacoes": "contraindicacoes",
        }

        for json_key, db_field in field_map.items():
            current = getattr(product, db_field, None)
            new_value = enrichment.get(json_key, "")
            # Só preenche se campo está vazio e o novo valor é substancial
            if (not current or len(str(current).strip()) < 20) and new_value and len(new_value) >= 20:
                updates[db_field] = new_value

        if not updates:
            logger.info("Nenhum campo para enriquecer em %s", product.nome)
            return False

        enriched_fields = list(updates.keys())
        valores_anteriores = {k: getattr(product, k, None) for k in enriched_fields}

        # Marca de proveniência: este texto foi ESCRITO POR UM MODELO, e o
        # prompt permite "conhecimento médico estabelecido" — não é dado
        # oficial. Sem esta marca, o Auditor recebe tudo como "verdade
        # absoluta" e valida o laudo contra a saída de outro modelo.
        from app.services.provenance import build_provenance, ORIGEM_LLM
        marcas = build_provenance(
            getattr(product, "campos_gerados_ia", None),
            enriched_fields,
            origem=ORIGEM_LLM,
            modelo=settings.OPENAI_MODEL_ENRICHMENT,
        )
        updates["campos_gerados_ia"] = marcas

        # UPDATE tipado pelo model (e não SQL cru como antes): a coluna nova é
        # JSON e cada driver serializa dict de um jeito — o construtor do
        # SQLAlchemy resolve isso para SQLite e Postgres. Continua não exigindo
        # que `product` esteja anexado a esta session.
        await db.execute(
            sql_update(Product).where(Product.id == product.id).values(**updates)
        )

        # Trilha de auditoria: guarda o valor ANTERIOR de cada campo, que é o
        # que torna esta escrita reversível (antes não havia rollback algum).
        try:
            from app.services.audit_service import audit_log
            from app.db.models import AuditAction
            await audit_log(
                db,
                AuditAction.GENERATE,
                resource_type="product",
                resource_id=str(product.id),
                changes={
                    campo: {"old": valores_anteriores.get(campo), "new": updates.get(campo)}
                    for campo in enriched_fields
                },
                justification="Ficha técnica gerada por LLM (auto-enriquecimento de produto incompleto)",
                metadata={
                    "origem": ORIGEM_LLM,
                    "modelo": settings.OPENAI_MODEL_ENRICHMENT,
                    "cid_contexto": cid,
                    "produto_nome": product.nome,
                },
            )
        except Exception as e:  # nunca bloqueia o enriquecimento
            logger.warning("AuditLog do enriquecimento falhou (non-blocking): %s", e)

        await db.commit()

        # Atualizar objeto em memória (o mesmo laudo em curso já usa a ficha)
        for k, v in updates.items():
            setattr(product, k, v)
        logger.info(
            "Produto enriquecido: %s — campos: %s",
            product.nome, ", ".join(enriched_fields),
        )

        if on_progress:
            await on_progress(
                "enriching",
                f"Ficha técnica de {product.nome} gerada ({len(enriched_fields)} campos)",
            )

        return True

    except Exception as e:
        logger.exception("Auto-enriquecimento falhou para %s: %s", product.nome, e)
        if on_progress:
            await on_progress("enriching", f"Enriquecimento indisponível — continuando sem ficha...")
        return False
