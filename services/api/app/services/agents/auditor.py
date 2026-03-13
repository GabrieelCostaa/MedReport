"""
Agente C: O Auditor (The Verifier - "Double Check").
Confronta rascunho com dados oficiais do produto e valida checklist.
"""
import json
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings
from .prompts import AUDITOR_SYSTEM
from .writer import DraftReport
from .token_tracker import TokenUsage, extract_usage

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    tipo: str  # correcao | remocao | validacao
    campo: str
    original: str = ""
    corrigido: str = ""
    motivo: str = ""


@dataclass
class AuditResult:
    texto_corrigido: str = ""
    aprovado: bool = False
    checklist: dict = field(default_factory=dict)
    audit_log: list[AuditEntry] = field(default_factory=list)
    referencias_validadas: list[str] = field(default_factory=list)
    raw_response: Optional[str] = None
    token_usage: Optional[TokenUsage] = None

    def to_dict(self) -> dict:
        return {
            "texto_corrigido": self.texto_corrigido,
            "aprovado": self.aprovado,
            "checklist": self.checklist,
            "audit_log": [
                {"tipo": a.tipo, "campo": a.campo, "original": a.original,
                 "corrigido": a.corrigido, "motivo": a.motivo}
                for a in self.audit_log
            ],
            "referencias_validadas": self.referencias_validadas,
        }


def _build_product_facts(product) -> str:
    facts = {}
    if product.viscosidade:
        facts["viscosidade"] = product.viscosidade
    if product.peso_molecular:
        facts["peso_molecular"] = product.peso_molecular
    if product.concentracao:
        facts["concentracao"] = product.concentracao
    if product.registro_anvisa:
        facts["registro_anvisa"] = product.registro_anvisa
    if product.nome:
        facts["nome_oficial"] = product.nome
    if product.diferenciais_clinicos:
        facts["diferenciais_oficiais"] = product.diferenciais_clinicos
    return json.dumps(facts, ensure_ascii=False, indent=2)


def _extract_known_authors(product, clinical_evidences: list = None) -> str:
    """Extrai sobrenomes de autores de todas as fontes conhecidas do produto."""
    authors = set()

    refs = getattr(product, 'referencias_bibliograficas', None) or []
    for ref in refs:
        parts = ref.split(",")[0].split("(")[0].strip()
        surname = parts.split(" et al")[0].split(" ")[0].strip()
        if len(surname) > 2:
            authors.add(surname)

    for ev in (clinical_evidences or []):
        autor = ev if isinstance(ev, str) else ev.get("autor", "")
        surname = autor.split(",")[0].split(" et al")[0].split(" ")[0].strip()
        if len(surname) > 2:
            authors.add(surname)

    CLASSIC_AUTHORS = [
        "Altman", "Bannuru", "Bellamy", "Dahl", "Diamond",
        "Becker", "Tezel", "Metcalfe", "Janda", "Levy",
        "Rahaman", "LeGeros", "Basilio",
    ]
    authors.update(CLASSIC_AUTHORS)

    if not authors:
        return "Nenhum autor conhecido registrado."
    return ", ".join(sorted(authors))


def _local_verify_references(text: str, known_authors_set: set) -> tuple[bool, list[str]]:
    """Verificação local: extrai sobrenomes do texto e confere contra autores conhecidos."""
    ref_pattern = re.compile(
        r"([A-Z][a-záéíóúàãõâêô]+)\s+(?:et\s+al\.?|e\s+\w+)?\s*[,(]?\s*(\d{4})",
        re.UNICODE,
    )
    found_refs = []
    for m in ref_pattern.finditer(text):
        surname = m.group(1)
        year = m.group(2)
        if any(surname.lower() == ka.lower() for ka in known_authors_set):
            found_refs.append(f"{surname} et al., {year}")

    has_refs = len(found_refs) > 0
    return has_refs, found_refs


async def audit(draft: DraftReport, product, clinical_evidences: list = None) -> AuditResult:
    """
    Audita o rascunho confrontando com dados oficiais do produto.
    Corrige dados técnicos incorretos e valida checklist de 6 itens.
    """
    product_facts = _build_product_facts(product)
    known_authors = _extract_known_authors(product, clinical_evidences)

    known_authors_set = {a.strip() for a in known_authors.split(",") if len(a.strip()) > 2}

    # Include base_legal in the draft text so the auditor can see it
    draft_text_for_audit = draft.justificativa_completa or ""
    if draft.base_legal:
        draft_text_for_audit += f"\n\n[CAMPO SEPARADO — BASE LEGAL]\n{draft.base_legal}"

    system_prompt = AUDITOR_SYSTEM.format(
        product_facts=product_facts,
        draft_text=draft_text_for_audit,
        known_authors=known_authors,
    )

    user_message = (
        "Realize a auditoria completa do rascunho acima. "
        "Confronte com os dados oficiais do produto. "
        "Corrija qualquer dado técnico divergente. "
        "Verifique o checklist de 6 itens obrigatórios."
    )

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
            temperature=0.1,
            max_tokens=5000,
        )

        raw = response.choices[0].message.content
        usage = extract_usage(response, "Auditor")
        data = json.loads(raw)

        checklist = data.get("checklist", {})
        aprovado = data.get("aprovado", False)

        audit_log_entries = []
        for entry in data.get("audit_log", []):
            if entry.get("tipo") == "remocao" and "referencia" in entry.get("campo", "").lower():
                original = entry.get("original", "")
                if any(a.lower() in original.lower() for a in known_authors_set if len(a) > 2):
                    audit_log_entries.append(AuditEntry(
                        tipo="validacao",
                        campo=entry.get("campo", ""),
                        original=original,
                        corrigido=original,
                        motivo=f"Referência preservada: autor encontrado na lista de autores conhecidos.",
                    ))
                    continue
            audit_log_entries.append(AuditEntry(
                tipo=entry.get("tipo", "validacao"),
                campo=entry.get("campo", ""),
                original=entry.get("original", ""),
                corrigido=entry.get("corrigido", ""),
                motivo=entry.get("motivo", ""),
            ))

        texto_corrigido = data.get("texto_corrigido", draft.justificativa_completa)
        refs_validadas = data.get("referencias_validadas", [])

        # Fix: base_legal in separate field should satisfy checklist item 5
        if not checklist.get("base_legal_ans", False) and draft.base_legal:
            base_legal_lower = draft.base_legal.lower()
            if any(term in base_legal_lower for term in ("rn 395", "rn 424", "rn 428", "rn 465", "resolução normativa", "ans")):
                checklist["base_legal_ans"] = True
                audit_log_entries.append(AuditEntry(
                    tipo="validacao",
                    campo="base_legal_ans",
                    original="",
                    corrigido="Base legal presente no campo separado",
                    motivo="Fundamentação legal detectada no campo base_legal (separado da justificativa, conforme template).",
                ))

        has_local_refs, local_refs = _local_verify_references(texto_corrigido, known_authors_set)
        if has_local_refs and not checklist.get("referencia_bibliografica", False):
            checklist["referencia_bibliografica"] = True
            for lr in local_refs:
                if lr not in refs_validadas:
                    refs_validadas.append(lr)
            audit_log_entries.append(AuditEntry(
                tipo="validacao",
                campo="referencia_bibliografica",
                original="",
                corrigido=", ".join(local_refs),
                motivo="Referências detectadas localmente por match de sobrenome no texto.",
            ))

        if not aprovado:
            aprovado = all(checklist.values()) if checklist else False

        # Deterministic post-processing: strip RN mentions from body
        # when base_legal exists as separate field (prevents PDF duplication)
        if draft.base_legal:
            texto_corrigido = _strip_legal_from_body(texto_corrigido)

        # Deterministic anti-hallucination: remove fabricated monetary values
        texto_corrigido, money_entries = _strip_fabricated_costs(
            texto_corrigido, clinical_evidences or []
        )
        audit_log_entries.extend(money_entries)

        # Deterministic: check CID presence in text
        cid_entries = _check_cid_in_text(texto_corrigido)
        audit_log_entries.extend(cid_entries)

        return AuditResult(
            texto_corrigido=texto_corrigido,
            aprovado=aprovado,
            checklist=checklist,
            audit_log=audit_log_entries,
            referencias_validadas=refs_validadas,
            raw_response=raw,
            token_usage=usage,
        )

    except Exception as e:
        logger.exception("Agente Auditor falhou: %s", e)
        checklist = _local_checklist(draft)
        return AuditResult(
            texto_corrigido=draft.justificativa_completa,
            aprovado=all(checklist.values()),
            checklist=checklist,
            audit_log=[
                AuditEntry(
                    tipo="validacao",
                    campo="geral",
                    motivo=f"Auditoria automática (LLM indisponível): {e}",
                )
            ],
            referencias_validadas=draft.referencias,
            raw_response=str(e),
        )


def _strip_fabricated_costs(text: str, evidences: list) -> tuple[str, list[AuditEntry]]:
    """Remove valores monetários fabricados (R$X.XXX) que não venham das evidências.

    Verifica se os valores R$ encontrados no texto existem em alguma evidência.
    Se não, remove a frase inteira contendo o valor e registra no audit_log.
    """
    entries = []
    if not text:
        return text, entries

    # Extrair valores monetários das evidências (fontes válidas)
    evidence_text = " ".join(
        ev.get("snippet", "") + " " + ev.get("texto", "")
        for ev in evidences
        if isinstance(ev, dict)
    )
    evidence_money = set(re.findall(r"R\$[\d.,]+", evidence_text))

    # Encontrar valores monetários no texto gerado
    money_pattern = re.compile(r"R\$\s*[\d.,]+(?:\s*(?:a|e|até)\s*R\$\s*[\d.,]+)?")
    matches = list(money_pattern.finditer(text))

    if not matches:
        return text, entries

    # Verificar quais valores NÃO vêm das evidências
    fabricated_sentences = set()
    for match in matches:
        value_str = match.group(0)
        # Extrair valores individuais
        individual_values = re.findall(r"R\$\s*[\d.,]+", value_str)
        has_evidence = any(
            v.replace(" ", "") in {e.replace(" ", "") for e in evidence_money}
            for v in individual_values
        )
        if not has_evidence:
            # Encontrar a frase que contém este valor
            start = text.rfind(".", 0, match.start())
            end = text.find(".", match.end())
            if start == -1:
                start = 0
            else:
                start += 1
            if end == -1:
                end = len(text)
            else:
                end += 1
            sentence = text[start:end].strip()
            if sentence:
                fabricated_sentences.add(sentence)
                entries.append(AuditEntry(
                    tipo="remocao",
                    campo="custo_fabricado",
                    original=sentence,
                    corrigido="",
                    motivo=f"Valor monetário '{value_str}' sem evidência científica — removido para evitar alucinação.",
                ))

    # Remover frases fabricadas
    for sentence in fabricated_sentences:
        text = text.replace(sentence, "")

    # Limpar espaços duplos e linhas vazias
    text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)
    text = re.sub(r"  +", " ", text)

    return text.strip(), entries


def _check_cid_in_text(text: str) -> list[AuditEntry]:
    """Verifica se algum código CID-10 aparece no texto."""
    entries = []
    if not text:
        return entries

    cid_pattern = re.compile(r"CID[\s-]*[A-Z]\d{2,3}(?:\.\d)?", re.IGNORECASE)
    if not cid_pattern.search(text):
        entries.append(AuditEntry(
            tipo="correcao",
            campo="cid_ausente",
            original="",
            corrigido="",
            motivo="CID-10 não encontrado no texto da justificativa. Convênios exigem CID explícito.",
        ))

    return entries


def _strip_legal_from_body(text: str) -> str:
    """Remove sentenças com RNs da ANS do corpo da justificativa.

    Quando base_legal existe como campo separado, menções a RNs no corpo
    causam duplicação no PDF. Esta função remove deterministicamente
    sentenças que mencionem RNs da ANS.
    """
    if not text:
        return text

    # Also strip the auditor's appended "[CAMPO SEPARADO" block if present
    marker = "\n\n[CAMPO SEPARADO"
    if marker in text:
        text = text[:text.index(marker)]

    rn_pattern = re.compile(
        r"(?:rn\s*\d{3}|resolução\s+normativa|código\s+de\s+ética\s+médica)",
        re.IGNORECASE,
    )

    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        # Split line into sentences and filter
        sentences = re.split(r"(?<=[.!?])\s+", line)
        kept = [s for s in sentences if not rn_pattern.search(s)]
        cleaned = " ".join(kept).strip()
        if cleaned:
            cleaned_lines.append(cleaned)

    return "\n".join(cleaned_lines)


def _local_checklist(draft: DraftReport) -> dict:
    """Checklist local sem LLM."""
    text = (draft.justificativa_completa or "").lower()
    base_legal_text = (draft.base_legal or "").lower()
    combined_legal = text + " " + base_legal_text
    return {
        "diagnostico": bool(draft.diagnostico_resumo),
        "justificativa_tecnica": len(text) > 100,
        "falha_terapeutica": bool(draft.falha_terapeutica),
        "risco_nao_realizacao": bool(draft.risco_nao_realizacao),
        "base_legal_ans": any(term in combined_legal for term in ("rn 395", "rn 424", "rn 428", "rn 465", "ans")),
        "referencia_bibliografica": len(draft.referencias) > 0,
    }
