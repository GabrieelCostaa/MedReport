"""
Fuzzy evaluation utilities for medical report comparison.

Three matching strategies:
  1. Exact match   -- structured fields (ANVISA, CID, TUSS)
  2. Fuzzy match   -- free-text fields (justificativa, diagnóstico)
  3. F1 score      -- list fields (referências, keywords)

Uses rapidfuzz (MIT license, C++ backend, ~100x faster than thefuzz).
"""
import re
from dataclasses import dataclass, field
from rapidfuzz import fuzz, process


# ── 1. Exact Match (structured fields) ───────────────────────────────────

def exact_match_anvisa(generated: str, official: str) -> bool:
    normalize = lambda s: re.sub(r"[^0-9A-Za-z]", "", s).upper()
    return normalize(generated) == normalize(official)


def exact_match_cid(generated: str, official: str) -> bool:
    return generated.strip().upper() == official.strip().upper()


def exact_match_tuss(generated: str, official: str) -> bool:
    normalize = lambda s: re.sub(r"\D", "", s)
    return normalize(generated) == normalize(official)


# ── 2. Fuzzy Match (free-text fields) ────────────────────────────────────

@dataclass
class FuzzyResult:
    score: float       # 0-100
    passed: bool
    method: str
    details: str = ""


def fuzzy_match_text(
    generated: str,
    reference: str,
    threshold: float = 75.0,
    method: str = "token_sort",
) -> FuzzyResult:
    scorers = {
        "ratio": fuzz.ratio,
        "partial_ratio": fuzz.partial_ratio,
        "token_sort": fuzz.token_sort_ratio,
        "token_set": fuzz.token_set_ratio,
    }
    scorer = scorers.get(method, fuzz.token_sort_ratio)
    score = scorer(generated.lower(), reference.lower())
    return FuzzyResult(
        score=score,
        passed=score >= threshold,
        method=method,
        details=f"{method}={score:.1f} (threshold={threshold})",
    )


def fuzzy_match_diagnosis(generated: str, reference: str) -> FuzzyResult:
    return fuzzy_match_text(generated, reference, threshold=70.0, method="token_set")


def fuzzy_match_justificativa(generated: str, golden: str) -> FuzzyResult:
    return fuzzy_match_text(generated, golden, threshold=65.0, method="token_sort")


# ── 3. F1 Score for List Fields ───────────────────────────────────────────

@dataclass
class F1Result:
    precision: float
    recall: float
    f1: float
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)


def f1_references(
    generated_refs: list[str],
    expected_refs: list[str],
    match_threshold: float = 80.0,
) -> F1Result:
    if not expected_refs:
        return F1Result(precision=1.0, recall=1.0, f1=1.0)
    if not generated_refs:
        return F1Result(precision=0.0, recall=0.0, f1=0.0, missing=expected_refs)

    matched = []
    missing = []
    matched_gen_indices = set()

    for exp_ref in expected_refs:
        best = process.extractOne(
            exp_ref, generated_refs, scorer=fuzz.token_sort_ratio,
        )
        if best and best[1] >= match_threshold:
            matched.append(exp_ref)
            matched_gen_indices.add(best[2])
        else:
            missing.append(exp_ref)

    extra = [g for i, g in enumerate(generated_refs) if i not in matched_gen_indices]

    tp = len(matched)
    fp = len(extra)
    fn = len(missing)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return F1Result(precision=precision, recall=recall, f1=f1, matched=matched, missing=missing, extra=extra)


def f1_keywords(text: str, expected_keywords: list[str]) -> F1Result:
    text_lower = text.lower()
    matched = [kw for kw in expected_keywords if kw.lower() in text_lower]
    missing = [kw for kw in expected_keywords if kw.lower() not in text_lower]
    tp = len(matched)
    fn = len(missing)
    precision = 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return F1Result(precision=precision, recall=recall, f1=f1, matched=matched, missing=missing)


# ── 4. Combined Report Evaluation ─────────────────────────────────────────

@dataclass
class ReportEvalResult:
    anvisa_match: bool
    cid_match: bool
    text_similarity: FuzzyResult
    reference_f1: F1Result
    keyword_f1: F1Result
    overall_score: float

    @property
    def passed(self) -> bool:
        return (
            self.anvisa_match
            and self.cid_match
            and self.text_similarity.passed
            and self.reference_f1.recall >= 0.8
            and self.keyword_f1.recall >= 0.8
        )


def evaluate_report(
    generated_text: str,
    golden_text: str,
    generated_refs: list[str],
    expected_refs: list[str],
    expected_keywords: list[str],
    generated_anvisa: str = "",
    official_anvisa: str = "",
    generated_cid: str = "",
    expected_cid: str = "",
) -> ReportEvalResult:
    anvisa_ok = exact_match_anvisa(generated_anvisa, official_anvisa) if official_anvisa else True
    cid_ok = exact_match_cid(generated_cid, expected_cid) if expected_cid else True
    text_sim = fuzzy_match_justificativa(generated_text, golden_text)
    ref_f1 = f1_references(generated_refs, expected_refs)
    kw_f1 = f1_keywords(generated_text, expected_keywords)

    weights = {"anvisa": 0.2, "cid": 0.1, "text": 0.3, "refs": 0.2, "keywords": 0.2}
    overall = (
        weights["anvisa"] * (1.0 if anvisa_ok else 0.0)
        + weights["cid"] * (1.0 if cid_ok else 0.0)
        + weights["text"] * (text_sim.score / 100.0)
        + weights["refs"] * ref_f1.f1
        + weights["keywords"] * kw_f1.f1
    )

    return ReportEvalResult(
        anvisa_match=anvisa_ok, cid_match=cid_ok,
        text_similarity=text_sim, reference_f1=ref_f1,
        keyword_f1=kw_f1, overall_score=overall,
    )
