"""
Camada 4: Validador Hard-Coded (Python puro, sem IA).

Extrai entidades técnicas do texto via regex e confronta com dados oficiais do produto.
Roda DEPOIS do Agente C (Auditor) como última camada de segurança.
Se detectar discrepância, bloqueia geração do PDF.
"""
import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_LEGAL_CONTEXT = re.compile(
    r"(?:RN|Resolução|Normativa|Lei|Art\.?|art\.?)\s*\d",
    re.IGNORECASE,
)


def _is_legal_context(text: str, match_start: int) -> bool:
    """Verifica se o número encontrado faz parte de um termo normativo (RN 395, Art. 11, etc.)."""
    window = text[max(0, match_start - 20):match_start + 5]
    return bool(_LEGAL_CONTEXT.search(window))


UNIT_PATTERNS = [
    # Viscosidade: mPa.s, Pa.s, cP, pascal
    re.compile(r"(\d[\d.,]*)\s*(mPa\.?s|Pa\.?s|cP|cp|centipoise|pascal)", re.IGNORECASE),
    # Peso molecular: kDa, MDa, Da (uppercase only), Dalton
    re.compile(r"(\d[\d.,]*)\s*(kDa|KDa|MDa|Da(?=[^a-z])|[Dd]altons?|[Mm]ega\s*[Dd]altons?)"),
    # Concentração: mg/mL, g/L, mg/dL (NÃO inclui % aqui -- tratado separadamente)
    re.compile(r"(\d[\d.,]*)\s*(mg/m[lL]|g/[lL]|mg/dL)", re.IGNORECASE),
    # Registro ANVISA: padrão numérico longo
    re.compile(r"(?:ANVISA|registro)\s*[:\s]*(\d{8,15}[A-Z]*)", re.IGNORECASE),
]

RANGE_PATTERN = re.compile(r"(\d[\d.,]*)\s*[-–a]\s*(\d[\d.,]*)\s*(mPa\.?s|Pa\.?s|kDa|MDa|mg/m[lL])", re.IGNORECASE)

# Contextos onde "X%" aparece em estudos científicos, NÃO como concentração do produto
_STATISTICAL_PERCENT_CONTEXT = re.compile(
    r"(?:reduziu|reduz|redução|diminuiu|aumentou|melhora|eficácia|sucesso|taxa|"
    r"comparado|versus|inferior|superior|formação|necessidade|casos|pacientes|"
    r"risco|incidência|prevalência|mortalidade|sobrevida)"
    r".{0,80}?(\d[\d.,]*)\s*%",
    re.IGNORECASE,
)
_STATISTICAL_PERCENT_AFTER = re.compile(
    r"(\d[\d.,]*)\s*%\s*.{0,40}?"
    r"(?:dos pacientes|dos casos|de redução|de melhora|de sucesso|de eficácia|"
    r"de formação|de taxa|menor|maior|de risco)",
    re.IGNORECASE,
)


@dataclass
class ValidationIssue:
    campo: str
    valor_no_texto: str
    valor_oficial: str
    tipo: str  # discrepancia | unidade_errada | dado_nao_verificavel
    severidade: str  # bloqueante | alerta


@dataclass
class ValidationResult:
    aprovado: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    entities_found: list[dict] = field(default_factory=list)

    @property
    def has_blocking_issues(self) -> bool:
        return any(i.severidade == "bloqueante" for i in self.issues)


def _normalize_number(s: str) -> float:
    """Converte string numérica em float, tratando separadores BR/US.
    Em PT-BR: 80.000 = oitenta mil, 6.000 = seis mil (ponto como separador de milhar).
    """
    s = s.strip().replace(" ", "")
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts) == 2 and len(parts[1]) == 3 and parts[1].isdigit():
            s = s.replace(".", "")
        elif len(parts) > 2:
            s = s.replace(".", "", len(parts) - 2)
    try:
        return float(s)
    except ValueError:
        return 0.0


def _extract_number_from_official(official_value: str) -> list[float]:
    """Extrai números de um valor oficial (pode ser range: '10.000 - 29.000 mPa.s')."""
    if not official_value:
        return []
    nums = re.findall(r"(\d[\d.,]+)", official_value)
    return [_normalize_number(n) for n in nums]


def _check_viscosidade(text: str, official: str) -> list[ValidationIssue]:
    issues = []
    if not official or "não aplicável" in official.lower():
        return issues

    official_nums = _extract_number_from_official(official)
    pattern = re.compile(r"(\d[\d.,]*)\s*(mPa\.?s|Pa\.?s|cP|cp|centipoise|pascal)", re.IGNORECASE)
    for match in pattern.finditer(text):
        if _is_legal_context(text, match.start()):
            continue
        found_num = _normalize_number(match.group(1))
        found_unit = match.group(2).lower()

        if found_unit in ("kg", "g", "mg"):
            issues.append(ValidationIssue(
                campo="viscosidade",
                valor_no_texto=match.group(0),
                valor_oficial=official,
                tipo="unidade_errada",
                severidade="bloqueante",
            ))
            continue

        if official_nums:
            in_range = False
            if len(official_nums) >= 2:
                low, high = min(official_nums), max(official_nums)
                if low * 0.8 <= found_num <= high * 1.2:
                    in_range = True
            else:
                if official_nums[0] * 0.8 <= found_num <= official_nums[0] * 1.2:
                    in_range = True

            if not in_range:
                issues.append(ValidationIssue(
                    campo="viscosidade",
                    valor_no_texto=match.group(0),
                    valor_oficial=official,
                    tipo="discrepancia",
                    severidade="bloqueante",
                ))
    return issues


def _check_peso_molecular(text: str, official: str) -> list[ValidationIssue]:
    issues = []
    if not official or "não aplicável" in official.lower():
        return issues

    official_nums = _extract_number_from_official(official)
    pattern = re.compile(r"(\d[\d.,]*)\s*(kDa|KDa|MDa|Da(?=[^a-z])|[Dd]altons?|[Mm]ega\s*[Dd]altons?)")
    for match in pattern.finditer(text):
        if _is_legal_context(text, match.start()):
            continue
        found_num = _normalize_number(match.group(1))
        found_unit = match.group(2)

        if found_unit.lower() in ("mda", "mega dalton"):
            found_num *= 1000

        if official_nums:
            official_ref = official_nums[0]
            if "kda" in official.lower():
                pass
            elif "mda" in official.lower():
                official_ref *= 1000

            if not (official_ref * 0.8 <= found_num <= official_ref * 1.2):
                issues.append(ValidationIssue(
                    campo="peso_molecular",
                    valor_no_texto=match.group(0),
                    valor_oficial=official,
                    tipo="discrepancia",
                    severidade="bloqueante",
                ))
    return issues


def _is_statistical_percent(text: str, match_start: int, match_str: str) -> bool:
    """Detecta se um valor com % aparece em contexto de estudo científico, não como concentração."""
    window_before = text[max(0, match_start - 100):match_start + len(match_str)]
    window_after = text[match_start:min(len(text), match_start + len(match_str) + 60)]

    if _STATISTICAL_PERCENT_CONTEXT.search(window_before):
        return True
    if _STATISTICAL_PERCENT_AFTER.search(window_after):
        return True
    return False


def _check_concentracao(text: str, official: str) -> list[ValidationIssue]:
    issues = []
    if not official or "não aplicável" in official.lower():
        return issues

    official_nums = _extract_number_from_official(official)
    official_unit = ""
    if "mg/ml" in official.lower():
        official_unit = "mg/ml"
    elif "g/l" in official.lower():
        official_unit = "g/l"
    elif "%" in official:
        official_unit = "%"

    pattern_units = re.compile(r"(\d[\d.,]*)\s*(mg/m[lL]|g/[lL]|mg/dL)", re.IGNORECASE)
    for match in pattern_units.finditer(text):
        if _is_legal_context(text, match.start()):
            continue
        found_num = _normalize_number(match.group(1))
        if official_nums:
            if not (official_nums[0] * 0.8 <= found_num <= official_nums[0] * 1.2):
                issues.append(ValidationIssue(
                    campo="concentracao",
                    valor_no_texto=match.group(0),
                    valor_oficial=official,
                    tipo="discrepancia",
                    severidade="bloqueante",
                ))

    if official_unit == "%":
        pattern_pct = re.compile(r"(\d[\d.,]*)\s*%")
        for match in pattern_pct.finditer(text):
            if _is_statistical_percent(text, match.start(), match.group(0)):
                continue
            found_num = _normalize_number(match.group(1))
            # For composite concentrations like "HA 60% / β-TCP 40%",
            # accept ANY number that appears in the official value
            if official_nums and any(
                n * 0.8 <= found_num <= n * 1.2 for n in official_nums
            ):
                continue  # Matches one of the official components
            if official_nums and not any(
                n * 0.8 <= found_num <= n * 1.2 for n in official_nums
            ):
                issues.append(ValidationIssue(
                    campo="concentracao",
                    valor_no_texto=match.group(0),
                    valor_oficial=official,
                    tipo="discrepancia",
                    severidade="bloqueante",
                ))
    elif "%" not in official:
        pattern_pct = re.compile(r"(\d[\d.,]*)\s*%")
        for match in pattern_pct.finditer(text):
            if _is_statistical_percent(text, match.start(), match.group(0)):
                continue
            issues.append(ValidationIssue(
                campo="concentracao",
                valor_no_texto=match.group(0),
                valor_oficial=official,
                tipo="discrepancia",
                severidade="alerta",
            ))

    return issues


def _check_registro_anvisa(text: str, official: str) -> list[ValidationIssue]:
    issues = []
    if not official:
        return issues

    pattern = re.compile(r"(?:ANVISA|registro)\s*[:\s]*(\d{8,15}[A-Z]*)", re.IGNORECASE)
    for match in pattern.finditer(text):
        found_reg = match.group(1)
        official_clean = re.sub(r"[^0-9A-Za-z]", "", official)
        found_clean = re.sub(r"[^0-9A-Za-z]", "", found_reg)
        if found_clean != official_clean:
            issues.append(ValidationIssue(
                campo="registro_anvisa",
                valor_no_texto=match.group(0),
                valor_oficial=official,
                tipo="discrepancia",
                severidade="bloqueante",
            ))
    return issues


def _extract_all_entities(text: str) -> list[dict]:
    """Extrai todas as entidades técnicas encontradas no texto."""
    entities = []
    for pattern in UNIT_PATTERNS:
        for match in pattern.finditer(text):
            entities.append({
                "match": match.group(0),
                "valor": match.group(1),
                "unidade": match.group(2) if match.lastindex >= 2 else "",
                "posicao": match.start(),
            })
    for match in RANGE_PATTERN.finditer(text):
        entities.append({
            "match": match.group(0),
            "valor_min": match.group(1),
            "valor_max": match.group(2),
            "unidade": match.group(3),
            "posicao": match.start(),
        })
    return entities


# ---------------------------------------------------------------------------
# Clinical safety checks (Bug fixes from adversarial testing)
# ---------------------------------------------------------------------------

# CID prefix → expected product category keywords
_CID_PRODUCT_MAP = {
    "M17": ["joelho", "articular", "viscossuplementação", "hialurônico", "artroscop"],
    "M16": ["quadril", "articular", "prótese", "artroplastia"],
    "K40": ["hérnia", "inguinal", "tela", "herniorrafia"],
    "K41": ["hérnia", "femoral", "tela", "herniorrafia"],
    "K42": ["hérnia", "umbilical", "tela", "herniorrafia"],
    "K43": ["hérnia", "incisional", "tela", "herniorrafia"],
    "K66": ["aderência", "peritone", "anti-aderên", "barreira"],
    "M23": ["joelho", "menisco", "ligament", "artroscop"],
    "M75": ["ombro", "manguito", "rotador"],
    "N48": ["peyronie", "penian", "erétil"],
    "J34": ["nasal", "turbinec", "septo"],
}


def _extract_stems(text: str, min_len: int = 5) -> set[str]:
    """Extrai radicais simplificados (primeiros 5+ chars) para matching morfológico PT-BR."""
    words = re.findall(r"[a-záéíóúàãõâêôü]{4,}", text.lower())
    stems = set()
    for w in words:
        # Use first 5 chars as a rough stem (handles PT-BR inflections)
        if len(w) >= min_len:
            stems.add(w[:min_len])
        stems.add(w)
    return stems


# Medical acronyms and abbreviations → full terms for matching
_MEDICAL_ABBREVIATIONS = {
    "lca": ["ligamento cruzado anterior", "lca"],
    "lcp": ["ligamento cruzado posterior", "lcp"],
    "lce": ["ligamento colateral"],
    "pyr": ["peyronie"],
    "de": ["disfunção erétil", "disfunção"],
    "atj": ["artroplastia total joelho"],
    "atq": ["artroplastia total quadril"],
    "rm": ["ressonância magnética"],
    "tc": ["tomografia"],
    "pde5i": ["inibidor fosfodiesterase", "sildenafil", "tadalafil"],
}


def _check_product_indication(diagnosis: str, product) -> list[ValidationIssue]:
    """Bug #2: Detecta uso off-label — produto não indicado para o diagnóstico."""
    issues = []
    indicacoes = getattr(product, "indicacoes", None)
    descricao = getattr(product, "descricao_tecnica", None) or ""
    if not indicacoes or not diagnosis:
        return issues

    indicacoes_lower = indicacoes.lower()
    diag_lower = diagnosis.lower()

    # Strategy 0: acronym/abbreviation expansion
    diag_tokens = re.findall(r"[A-Za-záéíóúàãõâêôü]+", diagnosis)
    for token in diag_tokens:
        token_lower = token.lower()
        expansions = _MEDICAL_ABBREVIATIONS.get(token_lower, [])
        for expansion in expansions:
            if expansion in indicacoes_lower or expansion in descricao.lower():
                return issues
        # Also match uppercase acronyms directly (e.g., "LCA" in indicações)
        if len(token) >= 2 and token.isupper() and token.lower() in indicacoes_lower:
            return issues

    # Strategy 1: exact word overlap
    diag_words = set(re.findall(r"[a-záéíóúàãõâêôü]{4,}", diag_lower))
    indic_words = set(re.findall(r"[a-záéíóúàãõâêôü]{4,}", indicacoes_lower))
    if diag_words & indic_words:
        return issues  # Direct match found

    # Strategy 2: substring match (e.g., "joelho" in indicações text)
    for kw in diag_words:
        if len(kw) >= 5 and kw in indicacoes_lower:
            return issues

    # Strategy 3: stem overlap (handles PT-BR morphology: incisional/incisionais)
    diag_stems = _extract_stems(diag_lower)
    indic_stems = _extract_stems(indicacoes_lower + " " + descricao.lower())
    if diag_stems & indic_stems:
        return issues  # Stem match found

    # Strategy 4: known medical synonyms / related terms
    _RELATED_TERMS = {
        "hérnia": ["herniorrafia", "hernio", "hernioplast"],
        "aderência": ["aderên", "anti-aderên", "barreira", "peritone", "laparotom", "abdomin"],
        "aderências": ["aderên", "anti-aderên", "barreira", "peritone", "laparotom", "abdomin"],
        "suboclusão": ["aderên", "peritone", "abdomin", "intestin"],
        "gonartrose": ["joelho", "articular", "hialurôn", "viscossup"],
        "osteoartrite": ["articular", "hialurôn", "viscossup", "joelho"],
        "pseudoartrose": ["enxerto", "ósseo", "artrodese"],
        "osteomielite": ["enxerto", "ósseo", "desbridam"],
    }
    for diag_word in diag_words:
        for key, synonyms in _RELATED_TERMS.items():
            if key in diag_word or diag_word in key:
                for syn in synonyms:
                    if syn in indicacoes_lower or syn in descricao.lower():
                        return issues

    # No match found at all — likely off-label
    issues.append(ValidationIssue(
        campo="indicacao_off_label",
        valor_no_texto=diagnosis[:100],
        valor_oficial=indicacoes[:150],
        tipo="off_label",
        severidade="bloqueante",
    ))

    return issues


def _check_contraindicacoes(diagnosis: str, product) -> list[ValidationIssue]:
    """Bug #4: Detecta contraindicações presentes no diagnóstico."""
    issues = []
    contras = getattr(product, "contraindicacoes", None)
    if not contras or not diagnosis:
        return issues

    diag_lower = diagnosis.lower()

    # Split contraindications into individual items
    contra_items = re.split(r"[.;]\s*", contras)
    for item in contra_items:
        item = item.strip()
        if len(item) < 5:
            continue
        # Extract key phrases from each contraindication
        # e.g., "Infecção ativa no sítio cirúrgico" → check "infecção ativa"
        key_phrases = []
        item_lower = item.lower()
        if "infecção ativa" in item_lower:
            key_phrases.append("infecção ativa")
        if "hipersensibilidade" in item_lower:
            key_phrases.append("hipersensibilidade")
        if "coagulopatia" in item_lower:
            key_phrases.append("coagulopatia")
        if "osteoporose severa" in item_lower:
            key_phrases.append("osteoporose severa")

        # Also try matching significant words (4+ chars) from the contraindication
        if not key_phrases:
            contra_words = set(re.findall(r"[a-záéíóúàãõâêô]{5,}", item_lower))
            stopwords = {"componentes", "componente", "direto", "contato", "ativa", "sítio"}
            contra_words -= stopwords
            matches = [w for w in contra_words if w in diag_lower]
            if len(matches) >= 2:
                key_phrases.append(" + ".join(matches))

        for phrase in key_phrases:
            if phrase in diag_lower:
                issues.append(ValidationIssue(
                    campo="contraindicacao",
                    valor_no_texto=phrase,
                    valor_oficial=item.strip(),
                    tipo="contraindicacao_presente",
                    severidade="bloqueante",
                ))

    return issues


def _check_cid_diagnosis_consistency(cid: str, diagnosis: str, product) -> list[ValidationIssue]:
    """Bug #3: Detecta CID incompatível com diagnóstico/produto."""
    issues = []
    if not cid or not diagnosis:
        return issues

    cid_upper = cid.upper().strip()
    cid_prefix = re.match(r"[A-Z]\d{2}", cid_upper)
    if not cid_prefix:
        return issues

    prefix = cid_prefix.group(0)
    indicacoes = (getattr(product, "indicacoes", "") or "").lower()

    # Check if CID prefix maps to a known category
    for known_prefix, expected_keywords in _CID_PRODUCT_MAP.items():
        if prefix == known_prefix:
            # CID matches a known category — check if product indicacoes match
            if any(kw in indicacoes for kw in expected_keywords):
                return issues  # Product matches the CID category — OK

    # Check for clearly wrong CID categories
    # J = Respiratory, applied to orthopedic product
    cid_chapter = cid_upper[0]
    ortho_product = any(kw in indicacoes for kw in ["joelho", "articular", "hialurônico", "ombro", "quadril", "ligament"])
    hernia_product = any(kw in indicacoes for kw in ["hérnia", "herniorrafia", "inguinal"])
    abdominal_product = any(kw in indicacoes for kw in ["abdomin", "peritone", "laparotom"])

    mismatch = False
    if cid_chapter == "J" and (ortho_product or hernia_product):  # Respiratory CID + ortho/hernia product
        mismatch = True
    elif cid_chapter in ("M",) and hernia_product:  # Musculoskeletal CID + hernia product
        mismatch = True
    elif cid_chapter in ("K",) and ortho_product:  # Digestive CID + ortho product
        mismatch = True

    if mismatch:
        issues.append(ValidationIssue(
            campo="cid_inconsistente",
            valor_no_texto=cid,
            valor_oficial=f"CID {cid} incompatível com indicações do produto: {indicacoes[:100]}",
            tipo="cid_produto_incompativel",
            severidade="bloqueante",
        ))

    return issues


def _check_patient_name_conflict(diagnosis: str, patient_name: str) -> list[ValidationIssue]:
    """Bug #5: Detecta nome de outro paciente no diagnóstico (copy/paste)."""
    issues = []
    if not diagnosis or not patient_name:
        return issues

    # Look for "Paciente NOME" pattern in diagnosis that differs from actual patient
    name_in_diag = re.search(
        r"[Pp]aciente\s+([A-ZÀ-Ú][A-ZÀ-Ú\s]{5,})",
        diagnosis,
    )
    if name_in_diag:
        found_name = name_in_diag.group(1).strip()
        patient_upper = patient_name.upper().strip()
        # Compare: if names don't share any word, it's a conflict
        found_words = set(found_name.upper().split())
        patient_words = set(patient_upper.split())
        # Remove common short words (de, da, do, dos)
        stopwords = {"DE", "DA", "DO", "DAS", "DOS"}
        found_words -= stopwords
        patient_words -= stopwords
        if found_words and patient_words and not (found_words & patient_words):
            issues.append(ValidationIssue(
                campo="nome_paciente_conflito",
                valor_no_texto=found_name,
                valor_oficial=patient_name,
                tipo="copypaste_detectado",
                severidade="bloqueante",
            ))

    return issues


def _check_pediatric_warning(diagnosis: str) -> list[ValidationIssue]:
    """Bug #4b: Alerta para pacientes pediátricos."""
    issues = []
    if not diagnosis:
        return issues

    # Match explicit age patterns: "12 anos", "paciente de 12 anos", "12 anos de idade"
    # Exclude duration patterns: "há 2 anos", "por 3 anos", "últimos 5 anos"
    age_patterns = [
        re.compile(r"(?:paciente\s+de|idade\s+de|criança\s+de|menor\s+de|adolescente\s+de)\s+(\d{1,2})\s*anos?", re.IGNORECASE),
        re.compile(r"(\d{1,2})\s*anos?\s+de\s+idade", re.IGNORECASE),
    ]
    # Negative lookbehind: exclude "há X anos", "por X anos", "últimos X anos", "em X anos"
    duration_context = re.compile(r"(?:há|por|últimos?|em|faz|depois\s+de)\s+\d{1,2}\s*anos?", re.IGNORECASE)

    for pattern in age_patterns:
        match = pattern.search(diagnosis)
        if match:
            age = int(match.group(1))
            # Verify it's not a duration context
            window_start = max(0, match.start() - 15)
            window = diagnosis[window_start:match.end()]
            if duration_context.search(window):
                continue
            if age < 18:
                issues.append(ValidationIssue(
                    campo="paciente_pediatrico",
                    valor_no_texto=f"{age} anos",
                    valor_oficial="Paciente menor de 18 anos — verificar indicação pediátrica",
                    tipo="alerta_pediatrico",
                    severidade="alerta",
                ))
                break

    return issues


def _check_diagnosis_quality(diagnosis: str) -> list[ValidationIssue]:
    """Bug #6: Detecta diagnóstico vago ou insuficiente."""
    issues = []
    if not diagnosis:
        issues.append(ValidationIssue(
            campo="diagnostico_vago",
            valor_no_texto="(vazio)",
            valor_oficial="Diagnóstico clínico detalhado obrigatório",
            tipo="diagnostico_ausente",
            severidade="bloqueante",
        ))
        return issues

    # Count meaningful words (excluding very short ones)
    words = [w for w in diagnosis.split() if len(w) > 2]
    if len(words) < 5:
        issues.append(ValidationIssue(
            campo="diagnostico_vago",
            valor_no_texto=diagnosis[:100],
            valor_oficial="Diagnóstico com menos de 5 palavras — insuficiente para justificativa",
            tipo="diagnostico_insuficiente",
            severidade="alerta",
        ))

    return issues


def validate_technical_data(
    text: str,
    product,
    medico_inputs: dict | None = None,
) -> ValidationResult:
    """
    Valida dados técnicos no texto contra os dados oficiais do produto.
    Última camada de segurança antes da geração do PDF.

    Args:
        text: Texto final da justificativa (pós-auditoria).
        product: Objeto Product com dados oficiais.
        medico_inputs: Dados do médico (paciente_nome, cid, diagnostico).

    Returns:
        ValidationResult com lista de issues encontrados.
        Se has_blocking_issues == True, a geração do PDF deve ser bloqueada.
    """
    result = ValidationResult()
    result.entities_found = _extract_all_entities(text)

    # --- Technical spec validation (existing) ---
    result.issues.extend(_check_viscosidade(text, getattr(product, 'viscosidade', None)))
    result.issues.extend(_check_peso_molecular(text, getattr(product, 'peso_molecular', None)))
    result.issues.extend(_check_concentracao(text, getattr(product, 'concentracao', None)))
    result.issues.extend(_check_registro_anvisa(text, getattr(product, 'registro_anvisa', None)))

    # --- Clinical safety validation (new) ---
    if medico_inputs:
        diagnosis = medico_inputs.get("diagnostico", "")
        cid = medico_inputs.get("cid", "")
        patient_name = medico_inputs.get("paciente_nome", "")

        result.issues.extend(_check_product_indication(diagnosis, product))
        result.issues.extend(_check_contraindicacoes(diagnosis, product))
        result.issues.extend(_check_cid_diagnosis_consistency(cid, diagnosis, product))
        result.issues.extend(_check_patient_name_conflict(diagnosis, patient_name))
        result.issues.extend(_check_pediatric_warning(diagnosis))
        result.issues.extend(_check_diagnosis_quality(diagnosis))

    result.aprovado = not result.has_blocking_issues

    if result.issues:
        for issue in result.issues:
            logger.warning(
                "HARD_VALIDATOR [%s] %s: texto='%s' oficial='%s' (%s)",
                issue.severidade.upper(),
                issue.campo,
                issue.valor_no_texto,
                issue.valor_oficial,
                issue.tipo,
            )

    return result
