"""
Agente A: O Pesquisador (The Researcher).
Busca evidências científicas e identifica lacunas que exigem input do médico.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings
from .prompts import RESEARCHER_SYSTEM

logger = logging.getLogger(__name__)


@dataclass
class Evidence:
    texto: str
    referencia: str
    relevancia: str = "media"


@dataclass
class GapQuestion:
    secao: str
    pergunta: str
    opcoes: list[dict] = field(default_factory=list)


@dataclass
class ResearchResult:
    evidencias: list[Evidence] = field(default_factory=list)
    referencias: list[str] = field(default_factory=list)
    lacunas: list[GapQuestion] = field(default_factory=list)
    sugestao_tuss: Optional[str] = None
    especialidade_detectada: Optional[str] = None
    raw_response: Optional[str] = None


def _build_product_context(product) -> str:
    parts = [f"Nome: {product.nome}"]
    if product.linha:
        parts.append(f"Linha: {product.linha}")
    if product.descricao_tecnica:
        parts.append(f"Descrição técnica: {product.descricao_tecnica}")
    if product.diferenciais_clinicos:
        parts.append(f"Diferenciais clínicos: {product.diferenciais_clinicos}")
    if product.indicacoes:
        parts.append(f"Indicações: {product.indicacoes}")
    if product.viscosidade:
        parts.append(f"Viscosidade: {product.viscosidade}")
    if product.peso_molecular:
        parts.append(f"Peso molecular: {product.peso_molecular}")
    if product.concentracao:
        parts.append(f"Concentração: {product.concentracao}")
    if product.registro_anvisa:
        parts.append(f"Registro ANVISA: {product.registro_anvisa}")
    if product.referencias_bibliograficas:
        parts.append(f"Referências conhecidas: {', '.join(product.referencias_bibliograficas)}")
    return "\n".join(parts)


async def research(product, diagnostico: str, cid: str, template=None) -> ResearchResult:
    """
    Executa pesquisa sobre a patologia e o produto.
    Retorna evidências, referências e lacunas que precisam de input do médico.
    """
    product_context = _build_product_context(product)

    system_prompt = RESEARCHER_SYSTEM.format(product_context=product_context)

    user_message = (
        f"Patologia/Diagnóstico: {diagnostico}\n"
        f"CID: {cid}\n"
        f"Material OPME solicitado: {product.nome}\n"
    )
    if template:
        user_message += f"\nTemplate de referência disponível: {template.nome}\n"
        if template.referencias_padrao:
            user_message += f"Referências padrão do template: {json.dumps(template.referencias_padrao)}\n"

    try:
        import openai
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=3000,
        )

        raw = response.choices[0].message.content
        data = json.loads(raw)

        return ResearchResult(
            evidencias=[
                Evidence(
                    texto=e.get("texto", ""),
                    referencia=e.get("referencia", ""),
                    relevancia=e.get("relevancia", "media"),
                )
                for e in data.get("evidencias", [])
            ],
            referencias=data.get("referencias_bibliograficas", []),
            lacunas=[
                GapQuestion(
                    secao=l.get("secao", ""),
                    pergunta=l.get("pergunta", ""),
                    opcoes=l.get("opcoes", []),
                )
                for l in data.get("lacunas", [])
            ],
            sugestao_tuss=data.get("sugestao_tuss"),
            especialidade_detectada=data.get("especialidade_detectada"),
            raw_response=raw,
        )

    except Exception as e:
        logger.exception("Agente Pesquisador falhou: %s", e)
        return ResearchResult(
            lacunas=[
                GapQuestion(
                    secao="falha_terapeutica",
                    pergunta="Quais tratamentos anteriores foram tentados sem sucesso?",
                    opcoes=[
                        {"id": "A", "texto": "Tratamento medicamentoso sem melhora"},
                        {"id": "B", "texto": "Fisioterapia sem ganho funcional"},
                        {"id": "C", "texto": "Procedimento anterior com complicações"},
                    ],
                ),
                GapQuestion(
                    secao="risco_nao_realizacao",
                    pergunta="Qual o principal risco caso o procedimento não seja realizado?",
                    opcoes=[
                        {"id": "A", "texto": "Progressão da doença com perda funcional"},
                        {"id": "B", "texto": "Dor crônica intratável"},
                        {"id": "C", "texto": "Risco de complicações graves"},
                    ],
                ),
            ],
            raw_response=str(e),
        )
