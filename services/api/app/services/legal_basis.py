"""
Fonte ÚNICA das normas citadas nos laudos de OPME.

Revisado em 2026-11-09 contra os textos oficiais:
- RN ANS 424/2017 (junta médica) — art. 7º, I: prerrogativa do médico assistente
  de determinar as características (tipo, matéria-prima, dimensões) da OPME
  (confirmado no Parecer Técnico ANS nº 24/GEAS/GGRAS/DIPRO/2021).
- RN ANS 465/2021 e atualizações — Rol de Procedimentos (cobertura obrigatória).
- RN ANS 623/2024 (vigente desde 01/07/2025) — REVOGOU a RN 395/2016. Negativa por
  escrito com motivo e fundamento; prazos de resposta no art. 12; reanálise no art. 16.
- Resolução CFM 2.318/2022 — REVOGOU as Res. CFM 1.804/2006 e 1.956/2010.
  Arts. 2º (características), 3º (justificativa clínica), 4º (sem marca exclusiva),
  6º (parecer do auditor identificado com nome, CRM e doutrina), 8º (três marcas),
  9º (arbitragem por especialista em até 5 dias úteis).
- Resolução CFM 2.454/2026 — uso de IA na medicina (decisão final do médico,
  registro do uso de IA).

Quando uma norma mudar, altere AQUI — prompts, few-shots, fallback do Redator,
checklists e o normalizador abaixo leem deste módulo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

REVISADO_EM = "2026-11-09"

# ── Texto padrão da fundamentação legal ──────────────────────────────────────
BASE_LEGAL_PADRAO = (
    "Nos termos da RN 424/2017 da ANS (art. 7º, I) e da Resolução CFM 2.318/2022 (art. 2º), "
    "cabe ao médico assistente determinar as características (tipo, matéria-prima e dimensões) "
    "das órteses, próteses e materiais especiais necessários ao procedimento, sem exigência de "
    "fornecedor ou marca exclusivos (Res. CFM 2.318/2022, art. 4º). Os procedimentos indicados "
    "integram o Rol de Procedimentos e Eventos em Saúde da ANS (RN 465/2021 e atualizações). "
    "Em caso de negativa, requer-se que seja comunicada por escrito, com indicação do motivo e do "
    "dispositivo legal ou contratual que a fundamenta (RN 623/2024), acompanhada de parecer do "
    "médico auditor identificado com nome, número de CRM e citação expressa da doutrina que a "
    "fundamentou (Res. CFM 2.318/2022, art. 6º). Persistindo divergência técnica quanto ao "
    "material, requer-se a instauração de junta médica (RN 424/2017) ou a arbitragem por médico "
    "especialista prevista no art. 9º da Res. CFM 2.318/2022. Aplica-se ainda o Código de Ética "
    "Médica (Cap. I, item V)."
)

# Declaração de uso de IA no rodapé do PDF/DOCX (Res. CFM 2.454/2026: a IA é apoio,
# a decisão é do médico, e o uso deve ser transparente).
DECLARACAO_USO_IA = (
    "Documento elaborado com apoio de ferramenta de inteligência artificial; conteúdo revisado "
    "e assumido pelo médico assistente, responsável pela indicação clínica (Res. CFM 2.454/2026)."
)

# Lista curta (usada em seeds de templates e metadados)
BASES_LEGAIS_VIGENTES = ["RN 424/2017", "RN 465/2021", "RN 623/2024", "Res. CFM 2.318/2022"]

# Bloco injetado no prompt do Redator (Regra #5)
PROMPT_REGRA_BASE_LEGAL = """As normas devem ser usadas como ARMA, não como citação decorativa. Cite SOMENTE as normas abaixo (vigentes):
- RN 424/2017 da ANS (art. 7º, I) + Res. CFM 2.318/2022 (art. 2º): AUTONOMIA — "cabe ao médico assistente determinar as características (tipo, matéria-prima e dimensões) das OPME necessárias ao procedimento"
- Res. CFM 2.318/2022 (art. 4º e art. 8º): sem marca exclusiva; quando pertinente, indicar ao menos três marcas de fabricantes diferentes regularizadas na Anvisa que atendam às características especificadas
- RN 465/2021 e atualizações: COBERTURA — "os procedimentos indicados integram o Rol de Procedimentos e Eventos em Saúde da ANS"
- RN 623/2024: EXIGÊNCIA — "em caso de negativa, requer-se comunicação por escrito, com o motivo e o dispositivo legal ou contratual que a fundamenta"
- Res. CFM 2.318/2022 (art. 6º): o parecer do médico auditor deve ser identificado (nome e CRM) e citar expressamente a doutrina que fundamentou a negativa
- RN 424/2017 (junta médica) e Res. CFM 2.318/2022 (art. 9º, arbitragem por especialista em até 5 dias úteis): caminho em caso de divergência técnica
- Código de Ética Médica Cap. I, V: "Compete ao médico usar o melhor do progresso científico em benefício do paciente"
NORMAS REVOGADAS — NUNCA CITE: RN 395/2016 (substituída pela RN 623/2024), RN 428/2017 (substituída pela RN 465/2021), Res. CFM 1.956/2010 e 1.804/2006 (substituídas pela Res. CFM 2.318/2022)."""

# Termos que indicam presença de fundamentação legal (checklist item 5)
LEGAL_PRESENCE_TERMS = (
    "rn 424", "rn 465", "rn 623", "cfm 2.318", "cfm nº 2.318", "resolução normativa",
    "resolução cfm",
)
_ANS_WORD = re.compile(r"\bans\b", re.IGNORECASE)


def has_legal_basis(text: str, accept_bare_ans: bool = True) -> bool:
    """True se o texto contém alguma fundamentação legal reconhecível.

    accept_bare_ans=False exige uma norma citada (não basta a palavra "ANS").

    Normas revogadas (ex.: RN 395) também contam como "presença" — elas são
    corrigidas por modernize_citations(), não reprovam o checklist.
    """
    low = (text or "").lower()
    if any(term in low for term in LEGAL_PRESENCE_TERMS):
        return True
    if find_revoked_citations(text or ""):
        return True
    return accept_bare_ans and bool(_ANS_WORD.search(low))


# ── Normalizador de normas revogadas ─────────────────────────────────────────
# O LLM foi treinado com textos antigos e tende a citar a RN 395. A troca é
# determinística e só mexe em normas cujo sucessor trata do MESMO assunto.
_N = r"(?:n[º°o]\.?\s*)?"  # "nº ", "n. ", "no "
_RN = r"(?:RN|Resolu[cç][aã]o\s+Normativa)\s*(?:ANS\s*)?" + _N
_CFM = r"(?:Res(?:olu[cç][aã]o)?\.?\s*)?CFM\s*" + _N

_REVOGADAS: list[tuple[re.Pattern, str, str]] = [
    # "RN 428/465" (forma usada nos prompts antigos) → só a vigente
    (re.compile(_RN + r"428\s*/\s*465(?:\s*/\s*(?:20)?21)?", re.IGNORECASE), "RN 465/2021", "RN 428"),
    (re.compile(_RN + r"395(?:\s*/\s*(?:20)?16)?\b", re.IGNORECASE), "RN 623/2024", "RN 395"),
    (re.compile(_RN + r"428(?:\s*/\s*(?:20)?17)?\b", re.IGNORECASE), "RN 465/2021", "RN 428"),
    (re.compile(_CFM + r"1\.?956(?:\s*/\s*(?:20)?10)?\b", re.IGNORECASE), "Resolução CFM 2.318/2022", "CFM 1.956"),
    (re.compile(_CFM + r"1\.?804(?:\s*/\s*(?:20)?06)?\b", re.IGNORECASE), "Resolução CFM 2.318/2022", "CFM 1.804"),
]


@dataclass
class LegalCorrection:
    norma_revogada: str
    trecho_original: str
    substituida_por: str


def find_revoked_citations(text: str) -> list[LegalCorrection]:
    """Lista citações de normas revogadas no texto (sem alterar)."""
    found: list[LegalCorrection] = []
    for pattern, replacement, label in _REVOGADAS:
        for m in pattern.finditer(text or ""):
            found.append(LegalCorrection(label, m.group(0), replacement))
    return found


def modernize_citations(text: str) -> tuple[str, list[LegalCorrection]]:
    """Substitui citações de normas revogadas pelas vigentes.

    Retorna (texto_corrigido, correções). Texto vazio/None volta como veio.
    """
    if not text:
        return text, []
    corrections: list[LegalCorrection] = []
    out = text
    for pattern, replacement, label in _REVOGADAS:
        def _sub(m: re.Match, _r=replacement, _l=label) -> str:
            corrections.append(LegalCorrection(_l, m.group(0), _r))
            return _r
        out = pattern.sub(_sub, out)
    return out, corrections
