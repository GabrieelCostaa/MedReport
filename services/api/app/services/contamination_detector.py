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
    """Identidade de um produto para detecção de contaminação cruzada.

    Só campos OFICIAIS entram aqui. `diferenciais_clinicos` foi removido: ele
    pode ter sido escrito pelo próprio LLM (ver product_enrichment.py), então
    usá-lo como impressão digital fazia o detector de contaminação de IA ser
    alimentado por texto de IA. Alimentava apenas o ramo de `alerta`, que o
    pipeline descarta — perda operacional zero, circularidade eliminada.

    `peso_molecular`, `viscosidade` e `concentracao` também saíram: eram
    gravados e NUNCA lidos por check_cross_product_contamination.
    """
    product_id: str
    product_name: str
    registro_anvisa: str
    codigo_tuss: str = ""


def build_fingerprint(product) -> ProductFingerprint:
    return ProductFingerprint(
        product_id=str(getattr(product, "id", "")),
        product_name=getattr(product, "nome", "") or "",
        registro_anvisa=getattr(product, "registro_anvisa", "") or "",
        codigo_tuss=getattr(product, "codigo_tuss_sugerido", "") or "",
    )


def _nome_aparece_no_texto(nome: str, texto_lower: str) -> bool:
    """Match de nome de produto com fronteira de palavra.

    O `in` cru bloqueava laudo legítimo de família de produtos: gerar o laudo
    de "Synvisc-One" cita o nome, que CONTÉM "Synvisc" — e disparava um
    bloqueante acusando contaminação pelo produto irmão.
    """
    if not nome:
        return False
    return re.search(rf"(?<![\w-]){re.escape(nome.lower())}(?![\w-])", texto_lower) is not None


def _registro_aparece_no_texto(registro: str, texto: str) -> bool:
    """Match de registro ANVISA tolerante a formatação, mas não a colisão.

    Dois modos de falha a evitar ao mesmo tempo:

    - FALSO POSITIVO (o comportamento antigo): o texto INTEIRO virava uma
      string de dígitos contígua e a busca era por substring, então datas,
      CIDs e quantidades colavam entre si e casavam com registro alheio.
    - FALSO NEGATIVO: o registro raramente aparece "limpo" no laudo — vem como
      "80.030.810/0056", com espaços, ou colado a um ano ("...0056/2024").

    A regex permite UM separador entre dígitos e exige que o número não esteja
    encostado em outro dígito, o que satisfaz os dois lados.
    """
    limpo = re.sub(r"\D", "", registro or "")
    if len(limpo) < 6:  # curto demais para identificar com segurança
        return False
    padrao = r"(?<!\d)" + r"[.\-/ ]?".join(limpo) + r"(?!\d)"
    return re.search(padrao, texto or "") is not None


def check_cross_product_contamination(
    text: str,
    current_product: ProductFingerprint,
    all_products: list[ProductFingerprint],
) -> list[ContaminationIssue]:
    issues = []
    text_lower = text.lower()
    nome_atual = (current_product.product_name or "").lower()
    registro_atual = re.sub(r"\D", "", current_product.registro_anvisa or "")

    for other in all_products:
        if other.product_id == current_product.product_id:
            continue

        # NOTA: NÃO existe aqui um "skip de família" por substring de nome.
        # Uma versão anterior deste PR tinha um, e ele era pior que inútil:
        # a fronteira de palavra de _nome_aparece_no_texto já resolve o caso
        # ("Synvisc-One" não casa com "Synvisc" e vice-versa), enquanto o skip
        # desligava a comparação inteira — nome E registro — para qualquer par
        # cujo nome fosse substring do outro. Um produto cadastrado como "Kit"
        # apagava a checagem de todos os "Kit *" do catálogo.
        if _nome_aparece_no_texto(other.product_name, text_lower):
            issues.append(ContaminationIssue(
                tipo="cross_product",
                descricao=f"Nome '{other.product_name}' encontrado no relatório de '{current_product.product_name}'",
                trecho=other.product_name,
                severidade="bloqueante",
            ))

        outro_registro = re.sub(r"\D", "", other.registro_anvisa or "")
        if outro_registro and outro_registro != registro_atual:
            if _registro_aparece_no_texto(other.registro_anvisa, text):
                issues.append(ContaminationIssue(
                    tipo="fingerprint",
                    descricao=f"ANVISA {other.registro_anvisa} pertence a '{other.product_name}'",
                    trecho=other.registro_anvisa,
                    severidade="bloqueante",
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
