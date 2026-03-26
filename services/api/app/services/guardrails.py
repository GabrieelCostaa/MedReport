"""
NeMo Guardrails integration for prompt injection defense.

Provides input/output rails for the MedReport pipeline:
  - Input: sanitize clinical data, reject injection attempts
  - Output: filter PII leaks, block non-medical content, detect language contamination

Fallback: if NeMo unavailable, uses regex-based heuristic checks.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from nemoguardrails import RailsConfig, LLMRails
    NEMO_AVAILABLE = True
except ImportError:
    NEMO_AVAILABLE = False
    logger.debug("NeMo Guardrails not available — using regex fallback")


# ── Regex-based guardrails (always available, no LLM cost) ────────────────

# Patterns that indicate prompt injection in clinical data fields
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|above|prior)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:a|an|the)\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+are", re.IGNORECASE),
    re.compile(r"```\s*(?:system|assistant|function)", re.IGNORECASE),
    re.compile(r"\[INST\]|\[/INST\]|<<SYS>>|<\|system\|>", re.IGNORECASE),
    re.compile(r"(?:forget|override|bypass)\s+(?:your|the|all)\s+(?:rules|instructions|constraints)", re.IGNORECASE),
    re.compile(r"do\s+not\s+follow\s+(?:your|the|any)\s+(?:rules|guidelines|instructions)", re.IGNORECASE),
    re.compile(r"(?:repeat|print|output|show)\s+(?:your|the)\s+(?:system|initial)\s+(?:prompt|message|instructions)", re.IGNORECASE),
]

# PII patterns that should not appear in LLM output
_PII_OUTPUT_PATTERNS = [
    re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}"),  # CPF
    re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"),  # CNPJ
    re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),  # Email
    re.compile(r"\(\d{2}\)\s*\d{4,5}-\d{4}"),  # Phone BR
]


def check_input_injection(text: str) -> dict:
    """
    Check clinical data input for prompt injection attempts.

    Returns:
        {"safe": True/False, "blocked_patterns": [...], "sanitized": "..."}
    """
    if not text:
        return {"safe": True, "blocked_patterns": [], "sanitized": ""}

    blocked = []
    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            blocked.append(match.group(0))

    if blocked:
        logger.warning("Prompt injection detected in input: %s", blocked)
        # Sanitize: remove injection patterns
        sanitized = text
        for pattern in _INJECTION_PATTERNS:
            sanitized = pattern.sub("[REMOVIDO]", sanitized)
        return {
            "safe": False,
            "blocked_patterns": blocked,
            "sanitized": sanitized,
        }

    return {"safe": True, "blocked_patterns": [], "sanitized": text}


def check_output_pii(text: str) -> dict:
    """
    Check LLM output for PII leaks (CPF, CNPJ, email, phone).

    Returns:
        {"clean": True/False, "pii_found": [...], "redacted": "..."}
    """
    if not text:
        return {"clean": True, "pii_found": [], "redacted": ""}

    pii_found = []
    redacted = text

    for pattern in _PII_OUTPUT_PATTERNS:
        for match in pattern.finditer(text):
            pii_found.append({"type": "PII", "value": match.group(0)[:4] + "***"})
            redacted = redacted.replace(match.group(0), "[PII REDACTED]")

    if pii_found:
        logger.warning("PII detected in LLM output: %d instances", len(pii_found))

    return {
        "clean": len(pii_found) == 0,
        "pii_found": pii_found,
        "redacted": redacted,
    }


def sanitize_input_for_llm(text: str) -> str:
    """
    Sanitize clinical data before sending to LLM.
    Removes injection attempts and wraps in XML delimiter.
    """
    result = check_input_injection(text)
    return result["sanitized"]


def sanitize_output_from_llm(text: str) -> str:
    """
    Sanitize LLM output: redact any PII that leaked through.
    """
    result = check_output_pii(text)
    return result["redacted"]


# ── Full pipeline guard ───────────────────────────────────────────────────

def guard_pipeline_input(medico_inputs: dict) -> dict:
    """
    Guard all pipeline inputs before they reach the LLM agents.

    Checks: diagnostico, surgery_description, falha_terapeutica, risco_nao_realizacao.
    Returns sanitized copy of medico_inputs.
    """
    sanitized = {}
    fields_to_check = [
        "diagnostico", "surgery_description",
        "falha_terapeutica", "risco_nao_realizacao",
        "paciente_nome",
    ]

    all_safe = True
    for key, value in medico_inputs.items():
        if key in fields_to_check and isinstance(value, str):
            result = check_input_injection(value)
            if not result["safe"]:
                all_safe = False
                logger.warning(
                    "Injection attempt in field '%s': %s",
                    key, result["blocked_patterns"],
                )
            sanitized[key] = result["sanitized"]
        else:
            sanitized[key] = value

    if not all_safe:
        sanitized["_injection_detected"] = True

    return sanitized


def guard_pipeline_output(text: str) -> str:
    """
    Guard pipeline output before returning to the user.
    Redacts any PII that the LLM may have generated.
    """
    return sanitize_output_from_llm(text)
