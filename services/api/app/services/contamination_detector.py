"""
Contamination detector for multi-product medical report generation.

Detects when the LLM accidentally mixes data from different products,
uses wrong language, or leaks training data artifacts.

Three detection strategies:
  1. Fingerprint-based: unique identifiers per product
  2. Language contamination: unwanted English in Portuguese output
  3. Training data leakage: LLM artifacts (e.g. "As an AI model...")
"""
import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ContaminationIssue:
    tipo: str        # "cross_product" | "language" | "training_leak" | "fingerprint"
    descricao: str
    trecho: str
    severidade: str  # "bloqueante" | "alerta"


@dataclass
class ContaminationResult:
    clean: bool = True
    issues: list[ContaminationIssue] = field(default_factory=list)

    @property
    def has_blocking(self) -> bool:
        return any(i.severidade == "bloqueante" for i in self.issues)


# ── 1. Fingerprint-based Detection ───────────────────────────────────────

@dataclass
class ProductFingerprint:
    product_id: str
    product_name: str
    registro_anvisa: str
    peso_molecular: str
    viscosidade: str
    concentracao: str
    unique_terms: list[str] = field(default_factory=list)


def build_fingerprint(product) -> ProductFingerprint:
    unique = []
    nome = getattr(product, "nome", "") or ""
    if nome:
        unique.append(nome)
    diferenciais = getattr(product, "diferenciais_clinicos", "") or ""
    if diferenciais:
        terms = [t.strip() for t in diferenciais.split(",") if len(t.strip()) > 5]
        unique.extend(terms[:3])

    return ProductFingerprint(
        product_id=str(getattr(product, "id", "")),
        product_name=nome,
        registro_anvisa=getattr(product, "registro_anvisa", "") or "",
        peso_molecular=getattr(product, "peso_molecular", "") or "",
        viscosidade=getattr(product, "viscosidade", "") or "",
        concentracao=getattr(product, "concentracao", "") or "",
        unique_terms=unique,
    )


def check_cross_product_contamination(
    text: str,
    current_product: ProductFingerprint,
    all_products: list[ProductFingerprint],
) -> list[ContaminationIssue]:
    issues = []
    text_lower = text.lower()

    for other in all_products:
        if other.product_id == current_product.product_id:
            continue

        if other.product_name and other.product_name.lower() in text_lower:
            issues.append(ContaminationIssue(
                tipo="cross_product",
                descricao=f"Nome '{other.product_name}' encontrado no relatório de '{current_product.product_name}'",
                trecho=other.product_name,
                severidade="bloqueante",
            ))

        if other.registro_anvisa:
            anvisa_clean = re.sub(r"\D", "", other.registro_anvisa)
            if anvisa_clean and anvisa_clean in re.sub(r"\D", "", text):
                issues.append(ContaminationIssue(
                    tipo="fingerprint",
                    descricao=f"ANVISA {other.registro_anvisa} pertence a '{other.product_name}'",
                    trecho=other.registro_anvisa,
                    severidade="bloqueante",
                ))

        for term in other.unique_terms:
            if len(term) >= 6 and term.lower() in text_lower:
                if term.lower() not in " ".join(current_product.unique_terms).lower():
                    issues.append(ContaminationIssue(
                        tipo="cross_product",
                        descricao=f"Termo '{term}' é exclusivo de '{other.product_name}'",
                        trecho=term,
                        severidade="alerta",
                    ))

    return issues


# ── 2. Language Contamination ─────────────────────────────────────────────

_ENGLISH_ONLY_PHRASES = [
    r"\bthe patient\b",
    r"\btreatment failure\b",
    r"\bhigh molecular weight\b",
    r"\bsurgical procedure\b",
    r"\bfurthermore\b",
    r"\bmoreover\b",
    r"\bin conclusion\b",
    r"\btherefore\b",
    r"\bhowever\b",
    r"\bnevertheless\b",
    r"\baccording to\b",
    r"\bbased on the evidence\b",
    r"\bclinical trial[s]?\b",
    r"\brandomized controlled\b",
]

_ACCEPTABLE_ENGLISH = {
    "cross-linked", "crosslinked", "stent", "stents", "scaffold",
    "mesh", "bypass", "shunt", "et al", "in vitro", "in vivo",
    "in situ", "score", "follow-up", "follow up", "gold standard",
}


def detect_language_contamination(text: str) -> list[ContaminationIssue]:
    issues = []

    for pattern in _ENGLISH_ONLY_PHRASES:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            fragment = m.group(0)
            if fragment.lower() not in _ACCEPTABLE_ENGLISH:
                issues.append(ContaminationIssue(
                    tipo="language",
                    descricao=f"Trecho em inglês detectado: '{fragment}'",
                    trecho=fragment,
                    severidade="alerta",
                ))

    # Per-sentence detection with lingua (if available)
    try:
        from lingua import Language, LanguageDetectorBuilder
        detector = LanguageDetectorBuilder.from_languages(
            Language.PORTUGUESE, Language.ENGLISH
        ).with_minimum_relative_distance(0.25).build()

        sentences = re.split(r"[.!?]\s+", text)
        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 30 or re.match(r"^[A-Z][a-z]+ et al", sent):
                continue
            lang = detector.detect_language_of(sent)
            if lang == Language.ENGLISH:
                confidence = detector.compute_language_confidence(sent, Language.ENGLISH)
                if confidence > 0.7:
                    issues.append(ContaminationIssue(
                        tipo="language",
                        descricao=f"Frase inteira em inglês (confiança: {confidence:.0%})",
                        trecho=sent[:100] + ("..." if len(sent) > 100 else ""),
                        severidade="bloqueante",
                    ))
    except ImportError:
        pass

    return issues


# ── 3. Training Data Leakage ─────────────────────────────────────────────

_LEAKAGE_PATTERNS = [
    (r"As an AI (?:language )?model", "bloqueante"),
    (r"I (?:cannot|can't|don't) (?:provide|give|offer)", "bloqueante"),
    (r"(?:ChatGPT|GPT-4|Claude|Gemini|OpenAI|Anthropic)", "bloqueante"),
    (r"It is (?:important|worth|noteworthy) to (?:note|mention|highlight) that", "alerta"),
    (r"(?:is a|was a|refers to a) (?:type|form|kind) of", "alerta"),
]


def detect_training_leakage(text: str) -> list[ContaminationIssue]:
    issues = []
    for pattern, severity in _LEAKAGE_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            issues.append(ContaminationIssue(
                tipo="training_leak",
                descricao=f"Padrão de treinamento detectado: '{m.group(0)}'",
                trecho=m.group(0),
                severidade=severity,
            ))
    return issues


# ── Full Check ────────────────────────────────────────────────────────────

def check_contamination(
    text: str,
    current_product,
    all_products: list = None,
) -> ContaminationResult:
    result = ContaminationResult()
    current_fp = build_fingerprint(current_product)

    if all_products:
        other_fps = [build_fingerprint(p) for p in all_products]
        result.issues.extend(check_cross_product_contamination(text, current_fp, other_fps))

    result.issues.extend(detect_language_contamination(text))
    result.issues.extend(detect_training_leakage(text))

    result.clean = not result.has_blocking
    return result
