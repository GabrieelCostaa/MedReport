"""
Fecha o loop do ReportEdit: as edições do médico (o sinal de qualidade mais
direto que temos — quanto ele precisou consertar) deixam de ser write-only.

Dois usos:
1. KPI de edição (`get_edit_stats`): quanto os médicos corrigem, por
   especialidade e por desfecho — se laudos muito editados glosam mais, o
   número prova onde a geração está falhando.
2. Few-shot dinâmico (`get_dynamic_examples`): o `edited_text` de um laudo
   APROVADO e POUCO editado é ouro — texto validado por médico E operadora.
   Vira exemplar extra do Redator (atrás de DYNAMIC_FEWSHOT_ENABLED).
"""
import json
import logging
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Report, ReportEdit

logger = logging.getLogger(__name__)

# Poucas edições = o médico validou o texto quase como veio
LOW_EDIT_THRESHOLD = 15
# Cap de tamanho do exemplar dinâmico injetado no prompt (chars)
EXEMPLAR_CAP_CHARS = 6000


def _changes_count(edit: ReportEdit) -> int:
    d = edit.diff_json or {}
    return (
        len(d.get("additions", []))
        + len(d.get("removals", []))
        + len(d.get("replacements", []))
    )


async def get_edit_stats(db: AsyncSession, user_id) -> dict:
    """Agrega as edições do médico por especialidade e desfecho do laudo."""
    rows = (await db.execute(
        select(ReportEdit, Report)
        .join(Report, ReportEdit.report_id == Report.id)
        .where(ReportEdit.user_id == user_id)
    )).all()

    total = len(rows)
    por_especialidade: dict[str, dict] = {}
    por_desfecho: dict[str, dict] = {}
    tipos: dict[str, int] = {}

    for edit, report in rows:
        n = _changes_count(edit)
        esp = edit.especialidade or report.especialidade or "—"
        e = por_especialidade.setdefault(esp, {"edicoes": 0, "mudancas_total": 0})
        e["edicoes"] += 1
        e["mudancas_total"] += n

        out = getattr(report, "outcome", None) or "pendente"
        o = por_desfecho.setdefault(out, {"edicoes": 0, "mudancas_total": 0})
        o["edicoes"] += 1
        o["mudancas_total"] += n

        if edit.edit_type:
            tipos[edit.edit_type] = tipos.get(edit.edit_type, 0) + 1

    def _fmt(groups: dict[str, dict]) -> list[dict]:
        return [
            {
                "chave": k,
                "edicoes": g["edicoes"],
                "media_mudancas": round(g["mudancas_total"] / g["edicoes"], 1) if g["edicoes"] else 0,
            }
            for k, g in sorted(groups.items(), key=lambda kv: -kv[1]["edicoes"])
        ]

    return {
        "total_edicoes": total,
        "por_especialidade": _fmt(por_especialidade),
        "por_desfecho": _fmt(por_desfecho),
        "por_tipo": [
            {"tipo": t, "n": n} for t, n in sorted(tipos.items(), key=lambda kv: -kv[1])
        ],
    }


def _parse_sections(texto: str) -> Optional[dict]:
    """Reconstrói as 6 seções a partir do corpo montado (títulos em CAPS).

    O few-shot do Redator precisa ser JSON no schema WriterOutput; um exemplar
    em texto corrido ensinaria o modelo a quebrar o formato. Se o texto editado
    não preservou os títulos, não serve como exemplar → None.
    """
    from app.services.agents.writer import _SECTION_TITLES

    positions = []
    for key, titulo in _SECTION_TITLES:
        m = re.search(re.escape(titulo), texto)
        if not m:
            return None
        positions.append((m.start(), m.end(), key))
    positions.sort()

    sections = {}
    for i, (start, end, key) in enumerate(positions):
        content_end = positions[i + 1][0] if i + 1 < len(positions) else len(texto)
        sections[key] = texto[end:content_end].strip()
    if not all(sections.values()):
        return None
    return sections


async def get_dynamic_examples(
    db: AsyncSession,
    especialidade: str,
    limit: int = 1,
) -> list[dict]:
    """Exemplar dinâmico: laudo APROVADO na operadora + pouco editado pelo médico.

    Retorna mensagens [user, assistant] no mesmo formato do few-shot estático
    (assistant = JSON no schema WriterOutput). Lista vazia se não houver
    candidato bom — o few-shot estático continua valendo.
    """
    if not especialidade:
        return []
    try:
        rows = (await db.execute(
            select(ReportEdit, Report)
            .join(Report, ReportEdit.report_id == Report.id)
            .where(
                Report.outcome == "aprovado",
                ReportEdit.especialidade.ilike(f"%{especialidade}%"),
            )
            .order_by(ReportEdit.created_at.desc())
            .limit(20)
        )).all()
    except Exception as e:
        logger.debug("Few-shot dinâmico indisponível: %s", e)
        return []

    messages: list[dict] = []
    for edit, report in rows:
        if len(messages) // 2 >= limit:
            break
        if _changes_count(edit) > LOW_EDIT_THRESHOLD:
            continue
        texto = (edit.edited_text or "")[:EXEMPLAR_CAP_CHARS]
        sections = _parse_sections(texto)
        if not sections:
            continue

        assistant = dict(sections)
        assistant["diagnostico_resumo"] = (report.diagnosis or "")[:200]
        assistant["base_legal"] = report.base_legal_ans or ""
        assistant["referencias"] = report.referencias_bib or []

        user = (
            f"Diagnóstico: {report.diagnosis or ''}\n"
            f"CID: {report.cid or ''}\n"
            f"Material: {report.materials or ''}\n"
        )
        messages.append({"role": "user", "content": user})
        messages.append({"role": "assistant", "content": json.dumps(assistant, ensure_ascii=False)})
        logger.info(
            "Few-shot dinâmico: exemplar aprovado+pouco editado (report=%s, especialidade=%s)",
            report.id, especialidade,
        )

    return messages
