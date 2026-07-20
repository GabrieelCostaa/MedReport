"""Consulta de risco de glosa por operadora (Painel ANS) e catálogo Tabela 38.

O nome do convênio digitado pelo médico é texto livre ("Unimed", "Bradesco"),
enquanto o Painel da ANS usa razões sociais completas ("Bradesco Saúde S.A.").
O matching tem 4 camadas de defesa:
1. normalização agressiva (acentos + sufixos societários removidos);
2. dicionário de apelidos que médicos realmente digitam (ALIAS_OPERADORAS);
3. empate no fuzzy → ambiguous=True + top-3 candidatos (nunca escolhe às cegas);
4. o registro ANS casado é persistido no Report (auditável e corrigível).

Todo o sinal é INFORMATIVO — nunca altera o score de aprovação.
"""
import logging
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MATCH_THRESHOLD = 80.0
TIE_MARGIN = 1.0          # empate: 2+ registros distintos a <=1 ponto do topo
STALE_SEMESTERS = 4       # dado mais recente com >4 semestres (2 anos) → histórico
SUMMARY_PERIODS = 4       # média dos últimos N semestres disponíveis (2 anos)

# Sufixos/formas societárias que só atrapalham o fuzzy matching.
_CORPORATE_NOISE = (
    "cooperativa de trabalho medico",
    "seguradora especializada em saude",
    "operadora de planos de saude",
    "planos de saude",
    "assistencia medica internacional",
    "assistencia medica",
    "sistema de saude",
    "seguro saude",
    "saude s a",
    " s a ",
    " s/a",
    " sa ",
    " ltda",
    " eireli",
)

# Apelidos que médicos digitam → termo canônico presente na razão social.
# "unimed" sozinho NÃO tem alias de propósito: é federação com dezenas de
# operadoras independentes — deve cair como ambíguo.
ALIAS_OPERADORAS = {
    "bradesco": "bradesco saude",
    "sulamerica": "sul america",
    "sul america": "sul america",
    "amil": "amil",
    "hapvida": "hapvida",
    "notredame": "notre dame intermedica",
    "notre dame": "notre dame intermedica",
    "intermedica": "notre dame intermedica",
    "gndi": "notre dame intermedica",
    "porto seguro": "porto seguro",
    "golden cross": "golden cross",
    "allianz": "allianz",
    "prevent senior": "prevent senior",
    "care plus": "care plus",
    "omint": "omint",
}


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def normalize_search(text: str) -> str:
    """Normalização LEVE p/ armazenamento e busca por substring:
    minúsculas + sem acentos + espaços colapsados (mantém o nome completo).
    Usada pelo ETL ao gravar razao_social_normalized e pelo autocomplete."""
    return " ".join(_strip_accents((text or "").lower()).split())


def normalize_operadora_name(nome: str) -> str:
    """Normaliza para matching: minúsculas, sem acentos, sem ruído societário."""
    text = _strip_accents((nome or "").lower())
    text = "".join(c if c.isalnum() else " " for c in text)
    text = f" {' '.join(text.split())} "
    for noise in _CORPORATE_NOISE:
        text = text.replace(f" {noise.strip()} ", " ")
    return " ".join(text.split())


@dataclass
class OperadoraGlosaSummary:
    registro_ans: str
    razao_social: str
    match_score: float                       # rapidfuzz 0-100
    ambiguous: bool = False
    candidatos: list = field(default_factory=list)   # top-3 quando ambíguo
    porte: str = ""
    modalidade: str = ""
    latest_period: str = ""
    period_range: str = ""                   # "2023-02 a 2024-01"
    n_semestres: int = 0
    medias_recentes: dict = field(default_factory=dict)
    dt_carga: str = ""
    is_stale: bool = False

    def to_dict(self) -> dict:
        return {
            "registro_ans": self.registro_ans,
            "razao_social": self.razao_social,
            "match_score": round(self.match_score, 1),
            "ambiguous": self.ambiguous,
            "candidatos": self.candidatos,
            "porte": self.porte,
            "modalidade": self.modalidade,
            "latest_period": self.latest_period,
            "period_range": self.period_range,
            "n_semestres": self.n_semestres,
            "medias_recentes": {
                k: (round(v, 2) if isinstance(v, float) else v)
                for k, v in self.medias_recentes.items()
            },
            "dt_carga": self.dt_carga,
            "is_stale": self.is_stale,
        }


def find_best_operadora_match(
    nome: str,
    candidates: list[tuple[str, str, str]],
    min_score: float = MATCH_THRESHOLD,
) -> Optional[dict]:
    """Casa o nome digitado contra (registro_ans, razao_social, razao_social_normalized).

    Retorna {"registro_ans", "razao_social", "score", "ambiguous", "candidatos"}
    ou None abaixo do threshold. Função pura (testável sem DB).
    """
    from rapidfuzz import fuzz

    if not nome or not candidates:
        return None

    query = normalize_operadora_name(nome)
    query = ALIAS_OPERADORAS.get(query, query)
    if not query:
        return None

    scored: list[tuple[float, str, str]] = []
    for registro, razao, razao_norm in candidates:
        target = normalize_operadora_name(razao_norm or razao)
        score = fuzz.WRatio(query, target)
        scored.append((score, registro, razao))

    scored.sort(key=lambda t: t[0], reverse=True)
    top_score, top_registro, top_razao = scored[0]
    if top_score < min_score:
        return None

    # Empate: registros DISTINTOS dentro da margem do topo.
    # Filtro anti-falso-empate: o candidato precisa compartilhar ao menos um
    # token real (>=4 chars) com a consulta — evita que o partial-ratio do
    # WRatio em nomes curtos ("Ame" vs "América") crie empates espúrios.
    query_tokens = {t for t in query.split() if len(t) >= 4}
    tied = {}
    for score, registro, razao in scored:
        if top_score - score > TIE_MARGIN or registro in tied:
            continue
        if registro != top_registro and query_tokens:
            target_tokens = set(normalize_operadora_name(razao).split())
            if not (query_tokens & target_tokens):
                continue  # empate espúrio — nenhum token em comum
        tied[registro] = (score, razao)
    ambiguous = len(tied) > 1

    candidatos = [
        {"registro_ans": reg, "razao_social": raz, "score": round(sc, 1)}
        for reg, (sc, raz) in sorted(tied.items(), key=lambda kv: -kv[1][0])[:3]
    ] if ambiguous else []

    return {
        "registro_ans": top_registro,
        "razao_social": top_razao,
        "score": top_score,
        "ambiguous": ambiguous,
        "candidatos": candidatos,
    }


def _fmt_semestre(periodo: str) -> str:
    """"2025-01" → "1º sem/2025" (CD_PERIODO do painel é SEMESTRAL, não mensal)."""
    try:
        ano, sem = periodo.split("-")
        return f"{int(sem)}º sem/{ano}"
    except (ValueError, AttributeError):
        return periodo


def _semestre_index(periodo: str) -> int:
    """Índice absoluto do semestre ("2025-01" → 2025*2 + 0) p/ cálculo de idade."""
    ano, sem = periodo.split("-")
    return int(ano) * 2 + (1 if sem == "02" else 0)


def summarize_indicators(rows: list, now: Optional[datetime] = None) -> dict:
    """Resumo dos SUMMARY_PERIODS semestres distintos mais recentes disponíveis.

    Verificado nos dados reais: CD_PERIODO é SEMESTRE ("2025-01" = 1º semestre
    de 2025), não mês — o painel da ANS é semestral. `rows` = objetos/dicts com
    periodo + colunas de indicador. Função pura.
    """
    def _get(row, key):
        return row.get(key) if isinstance(row, dict) else getattr(row, key, None)

    now = now or datetime.now(timezone.utc)
    columns = (
        "pc_glosa_inicial", "pc_glosa_final", "tempo_medio_pagamento_dias",
        "numero_guias_sem_retorno", "valor_guias_sem_retorno",
    )

    periodos = sorted({_get(r, "periodo") for r in rows if _get(r, "periodo")}, reverse=True)
    recent = set(periodos[:SUMMARY_PERIODS])
    recent_rows = [r for r in rows if _get(r, "periodo") in recent]
    if not recent_rows:
        return {"medias": {}, "latest_period": "", "period_range": "", "n_semestres": 0,
                "is_stale": True, "dt_carga": ""}

    medias = {}
    for col in columns:
        values = [_get(r, col) for r in recent_rows if _get(r, col) is not None]
        medias[col] = (sum(values) / len(values)) if values else None

    latest = periodos[0]
    oldest_recent = min(recent)
    try:
        now_index = now.year * 2 + (1 if now.month > 6 else 0)
        is_stale = (now_index - _semestre_index(latest)) > STALE_SEMESTERS
    except (ValueError, AttributeError):
        is_stale = True

    dt_cargas = [_get(r, "dt_carga") for r in recent_rows if _get(r, "dt_carga")]
    return {
        "medias": medias,
        "latest_period": latest,
        "period_range": f"{_fmt_semestre(oldest_recent)} a {_fmt_semestre(latest)}",
        "n_semestres": len(recent),
        "is_stale": is_stale,
        "dt_carga": max(dt_cargas) if dt_cargas else "",
    }


def build_glosa_alert(summary: OperadoraGlosaSummary) -> str:
    """Texto informativo do alerta. Sempre ecoa razão social + registro casados."""
    if summary.ambiguous:
        nomes = ", ".join(c["razao_social"] for c in summary.candidatos[:3])
        return (
            f"Convênio '{summary.razao_social}' ambíguo no Painel de Glosas ANS — "
            f"múltiplas operadoras correspondem ({nomes}). Especifique a operadora "
            f"(ex.: 'Unimed Campinas') para dados precisos. Informativo — não altera o score."
        )

    pc = summary.medias_recentes.get("pc_glosa_inicial")
    partes = [f"Convênio {summary.razao_social} (ANS {summary.registro_ans})"]
    if pc is not None:
        if summary.is_stale:
            partes.append(
                f"registrou glosa inicial média de {pc:.1f}% nos dados históricos do "
                f"Painel ANS ({summary.period_range})"
            )
        else:
            partes.append(
                f"glosa inicial média de {pc:.1f}% nos últimos {summary.n_semestres} "
                f"semestres disponíveis no Painel ANS ({summary.period_range})"
            )
    tmp = summary.medias_recentes.get("tempo_medio_pagamento_dias")
    if tmp is not None:
        partes.append(f"tempo médio de pagamento de {tmp:.0f} dias")
    partes.append("Dado informativo — não altera o score do relatório.")
    return "; ".join(partes[:-1]) + ". " + partes[-1]


# ─── API assíncrona (DB) ─────────────────────────────────────────────────────

async def get_glosa_motivo(db: AsyncSession, codigo: str):
    from app.db.models import GlosaMotivo
    result = await db.execute(select(GlosaMotivo).where(GlosaMotivo.codigo == codigo.strip()))
    return result.scalar_one_or_none()


async def get_operadora_glosa_summary(db: AsyncSession, nome: str) -> Optional[OperadoraGlosaSummary]:
    from app.db.models import OperadoraGlosaIndicador as OGI

    result = await db.execute(
        select(OGI.registro_ans, OGI.razao_social, OGI.razao_social_normalized).distinct()
    )
    candidates = [(r or "", rz or "", rn or "") for r, rz, rn in result.all()]
    match = find_best_operadora_match(nome, candidates)
    if not match:
        return None

    rows_result = await db.execute(
        select(OGI).where(OGI.registro_ans == match["registro_ans"]).order_by(OGI.periodo.desc())
    )
    rows = list(rows_result.scalars().all())
    stats = summarize_indicators(rows)

    return OperadoraGlosaSummary(
        registro_ans=match["registro_ans"],
        razao_social=match["razao_social"],
        match_score=match["score"],
        ambiguous=match["ambiguous"],
        candidatos=match["candidatos"],
        porte=getattr(rows[0], "porte", "") if rows else "",
        modalidade=getattr(rows[0], "modalidade", "") if rows else "",
        latest_period=stats["latest_period"],
        period_range=stats["period_range"],
        n_semestres=stats["n_semestres"],
        medias_recentes=stats["medias"],
        dt_carga=stats["dt_carga"],
        is_stale=stats["is_stale"],
    )


async def search_operadoras(db: AsyncSession, q: str, limit: int = 15) -> list[dict]:
    """Autocomplete para a UI: distinct operadoras por substring normalizada."""
    from app.db.models import OperadoraGlosaIndicador as OGI

    q_norm = normalize_search(q)
    if not q_norm:
        return []
    result = await db.execute(
        select(OGI.registro_ans, OGI.razao_social, OGI.porte, OGI.modalidade)
        .where(OGI.razao_social_normalized.contains(q_norm))
        .distinct()
        .limit(limit)
    )
    return [
        {"registro_ans": r, "razao_social": rz, "porte": p or "", "modalidade": m or ""}
        for r, rz, p, m in result.all()
    ]
