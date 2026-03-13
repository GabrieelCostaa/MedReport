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


def validate_technical_data(text: str, product) -> ValidationResult:
    """
    Valida dados técnicos no texto contra os dados oficiais do produto.
    Última camada de segurança antes da geração do PDF.

    Returns:
        ValidationResult com lista de issues encontrados.
        Se has_blocking_issues == True, a geração do PDF deve ser bloqueada.
    """
    result = ValidationResult()
    result.entities_found = _extract_all_entities(text)

    result.issues.extend(_check_viscosidade(text, getattr(product, 'viscosidade', None)))
    result.issues.extend(_check_peso_molecular(text, getattr(product, 'peso_molecular', None)))
    result.issues.extend(_check_concentracao(text, getattr(product, 'concentracao', None)))
    result.issues.extend(_check_registro_anvisa(text, getattr(product, 'registro_anvisa', None)))

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
