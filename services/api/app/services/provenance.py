"""
Proveniência dos campos de ficha técnica do produto.

PROBLEMA QUE ISTO RESOLVE: `products.descricao_tecnica`, `diferenciais_clinicos`,
`indicacoes` e `contraindicacoes` podem ser preenchidos por três caminhos muito
diferentes — seed curado à mão, parsing de bula em PDF, ou geração por LLM
(`product_enrichment.py`, cujo prompt autoriza "conhecimento médico
estabelecido"). Depois de gravados, os três ficam indistinguíveis, e o Redator e
o Auditor recebem todos rotulados como "Ficha oficial do produto — verdades
absolutas".

Isso cria verificação circular: um modelo escreve, o banco apaga a origem, outro
modelo valida contra aquilo. Dois modelos concordando não são duas evidências —
o segundo apenas herdou a premissa do primeiro.

Este módulo NÃO muda nenhum comportamento de geração. Ele só marca a origem,
para que a decisão de como tratar cada origem possa ser tomada depois, com dado
na mão. Ausência de marca (`NULL`) significa DESCONHECIDO/legado — nunca
interprete como "revisado por humano".
"""
import logging
from datetime import datetime, timezone
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# Vocabulário de origem. Alinhado ao que o projeto já usa em outros pontos
# (AnvisaResult.fonte, source="europepmc_pt" nas evidências).
ORIGEM_LLM = "llm"            # gerado por modelo de linguagem
ORIGEM_IFU_PDF = "ifu_pdf"    # extraído de bula em PDF (determinístico, mas não verificado)
ORIGEM_ANVISA = "anvisa"      # copiado de registro oficial da ANVISA
ORIGEM_SEED = "seed"          # curado à mão no seed do projeto

# Origens que NÃO podem ser tratadas como verdade oficial na verificação
# factual — é sobre isso que o consumo da marca vai decidir (PR seguinte).
ORIGENS_NAO_VERIFICADAS = frozenset({ORIGEM_LLM, ORIGEM_IFU_PDF})

# Campos de ficha técnica que aceitam marcação de origem.
CAMPOS_FICHA = ("descricao_tecnica", "diferenciais_clinicos", "indicacoes", "contraindicacoes")


def build_provenance(
    atual: Optional[dict],
    campos: Iterable[str],
    origem: str,
    modelo: Optional[str] = None,
    detalhe: Optional[str] = None,
) -> dict:
    """Mescla a marca de origem dos `campos` sobre o dicionário `atual`.

    Formato por campo: {"origem": ..., "em": <iso8601>, "modelo": ..., "detalhe": ...}
    Só as chaves preenchidas entram, para o JSON não virar ruído.
    """
    marcado = dict(atual or {})
    agora = datetime.now(timezone.utc).isoformat()
    for campo in campos:
        registro = {"origem": origem, "em": agora}
        if modelo:
            registro["modelo"] = modelo
        if detalhe:
            registro["detalhe"] = detalhe
        marcado[campo] = registro
    return marcado


def origem_do_campo(product, campo: str) -> Optional[str]:
    """Origem registrada de um campo, ou None se desconhecida/legada."""
    marcas = getattr(product, "campos_gerados_ia", None)
    if not isinstance(marcas, dict):
        return None
    registro = marcas.get(campo)
    if isinstance(registro, dict):
        return registro.get("origem")
    return None


def campo_nao_verificado(product, campo: str) -> bool:
    """True quando o campo veio de LLM ou de bula raspada.

    Conservador de propósito: campo sem marca devolve False (não sabemos que é
    gerado; assumir que é seria mudar comportamento com base em ausência de
    dado). Quem quiser saber "não temos certeza que é oficial" deve checar
    `origem_do_campo(...) is None` explicitamente.
    """
    return origem_do_campo(product, campo) in ORIGENS_NAO_VERIFICADAS


def resumo_origens(product) -> dict[str, str]:
    """Mapa campo → origem, só com o que está marcado. Útil em log e API."""
    marcas = getattr(product, "campos_gerados_ia", None)
    if not isinstance(marcas, dict):
        return {}
    return {
        campo: reg.get("origem", "")
        for campo, reg in marcas.items()
        if isinstance(reg, dict) and reg.get("origem")
    }
