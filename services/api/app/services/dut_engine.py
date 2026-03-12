"""
Motor DUT-as-Code: Avalia critérios da DUT de forma determinística (DSL)
com fallback para LLM em critérios subjetivos.

Separa dois universos:
- Critérios objetivos (idade, IMC, tempo): Python puro — zero custo, zero latência
- Critérios subjetivos (motivação, condição clínica): delegados ao Auditor Agent
"""
from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class CriterionResult:
    id: str
    tipo: str  # deterministico | subjetivo | exclusao
    resultado: str  # met | unmet | unknown | not_applicable
    valor_esperado: Any = None
    valor_paciente: Any = None
    mensagem: str = ""


@dataclass
class DutEvaluation:
    criteria_met: list[CriterionResult] = field(default_factory=list)
    criteria_unmet: list[CriterionResult] = field(default_factory=list)
    criteria_unknown: list[CriterionResult] = field(default_factory=list)
    criteria_subjective: list[CriterionResult] = field(default_factory=list)
    documents_missing: list[str] = field(default_factory=list)
    modo: str = "rol_dut"  # rol_dut | fora_do_rol | cobertura_direta
    exclusion_triggered: Optional[CriterionResult] = None

    @property
    def all_objective_met(self) -> bool:
        return len(self.criteria_unmet) == 0 and self.exclusion_triggered is None

    @property
    def total_criteria(self) -> int:
        return (len(self.criteria_met) + len(self.criteria_unmet) +
                len(self.criteria_unknown) + len(self.criteria_subjective))

    @property
    def met_percentage(self) -> float:
        total = self.total_criteria
        if total == 0:
            return 0.0
        return len(self.criteria_met) / total * 100


OPERATORS = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
    "!=": operator.ne,
}


def _coerce_numeric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def evaluate_dsl(dsl: dict, patient_data: dict) -> list[CriterionResult]:
    """
    Avalia todos os critérios da DSL contra dados do paciente.
    Critérios determinísticos são avaliados por Python puro.
    Critérios subjetivos são marcados como 'unknown' (precisam de LLM).
    """
    results = []

    for criterion in dsl.get("criterios", []):
        cid = criterion.get("id", "?")
        tipo = criterion.get("tipo", "subjetivo")

        if tipo == "subjetivo" or criterion.get("requer_llm"):
            results.append(CriterionResult(
                id=cid,
                tipo="subjetivo",
                resultado="unknown",
                mensagem=f"Critério subjetivo: {criterion.get('descricao', '')}. Requer análise do Auditor.",
            ))
            continue

        campo = criterion.get("campo_paciente")
        op_str = criterion.get("operador")
        expected = criterion.get("valor")

        if not campo or not op_str:
            results.append(CriterionResult(
                id=cid, tipo=tipo, resultado="unknown",
                mensagem=f"Critério {cid} mal definido (sem campo ou operador)",
            ))
            continue

        patient_val = patient_data.get(campo)

        if patient_val is None:
            results.append(CriterionResult(
                id=cid, tipo=tipo, resultado="unknown",
                valor_esperado=expected,
                mensagem=f"Dado '{campo}' não fornecido pelo médico",
            ))
            continue

        if op_str == "in":
            met = patient_val in (expected if isinstance(expected, list) else [expected])
        elif op_str == "not_in":
            met = patient_val not in (expected if isinstance(expected, list) else [expected])
        elif op_str == "contains":
            met = str(expected).lower() in str(patient_val).lower()
        elif op_str == "between":
            if isinstance(expected, list) and len(expected) == 2:
                pv = _coerce_numeric(patient_val)
                met = pv is not None and expected[0] <= pv <= expected[1]
            else:
                met = False
        elif op_str in OPERATORS:
            pv = _coerce_numeric(patient_val)
            ev = _coerce_numeric(expected)
            if pv is not None and ev is not None:
                met = OPERATORS[op_str](pv, ev)
            else:
                met = str(patient_val).strip().lower() == str(expected).strip().lower()
        else:
            met = False

        results.append(CriterionResult(
            id=cid,
            tipo=tipo,
            resultado="met" if met else "unmet",
            valor_esperado=expected,
            valor_paciente=patient_val,
            mensagem=criterion.get("descricao", ""),
        ))

    for exclusion in dsl.get("exclusoes", []):
        eid = exclusion.get("id", "EX?")
        campo = exclusion.get("campo_paciente")
        op_str = exclusion.get("operador", "==")
        val = exclusion.get("valor")

        if campo and patient_data.get(campo) is not None:
            patient_val = patient_data[campo]
            triggered = str(patient_val).lower() == str(val).lower() if op_str == "==" else False
        else:
            triggered = False

        results.append(CriterionResult(
            id=eid,
            tipo="exclusao",
            resultado="unmet" if triggered else "met",
            valor_esperado=f"NOT {val}",
            valor_paciente=patient_data.get(campo),
            mensagem=exclusion.get("descricao", ""),
        ))

    return results


def build_evaluation(results: list[CriterionResult]) -> DutEvaluation:
    """Agrupa resultados da avaliação DSL em DutEvaluation."""
    evaluation = DutEvaluation()

    for r in results:
        if r.tipo == "exclusao":
            if r.resultado == "unmet":
                evaluation.exclusion_triggered = r
                evaluation.criteria_unmet.append(r)
            continue

        if r.tipo == "subjetivo":
            evaluation.criteria_subjective.append(r)
        elif r.resultado == "met":
            evaluation.criteria_met.append(r)
        elif r.resultado == "unmet":
            evaluation.criteria_unmet.append(r)
        else:
            evaluation.criteria_unknown.append(r)

    return evaluation


class DutEngine:
    """Motor principal de avaliação DUT-as-Code."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_dut_for_procedure(self, procedure_code: str) -> Any | None:
        from app.db.models import DutRule
        result = await self.db.execute(
            select(DutRule).where(DutRule.procedimento_codigo == procedure_code).limit(1)
        )
        return result.scalar_one_or_none()

    async def find_dut_by_number(self, numero_dut: str) -> Any | None:
        from app.db.models import DutRule
        result = await self.db.execute(
            select(DutRule).where(DutRule.numero_dut == numero_dut).limit(1)
        )
        return result.scalar_one_or_none()

    async def evaluate_criteria(self, dut_rule, patient_data: dict) -> DutEvaluation:
        """Avalia critérios da DUT contra dados do paciente."""
        dsl = dut_rule.criterios_dsl
        if not dsl:
            return DutEvaluation(modo="cobertura_direta")

        results = evaluate_dsl(dsl, patient_data)
        evaluation = build_evaluation(results)

        if dut_rule.documentos_exigidos:
            provided = patient_data.get("documentos_fornecidos", [])
            for doc in dut_rule.documentos_exigidos:
                if doc not in provided:
                    evaluation.documents_missing.append(doc)

        return evaluation

    async def get_missing_documents(self, dut_rule, provided_docs: list[str]) -> list[str]:
        required = dut_rule.documentos_exigidos or []
        return [d for d in required if d not in provided_docs]

    async def find_rol_alternatives(self, procedure_code: str) -> list:
        """Busca procedimentos similares no Rol para comparação (modo Fora do Rol)."""
        from app.db.models import RolProcedure
        result = await self.db.execute(
            select(RolProcedure).where(
                RolProcedure.codigo_procedimento != procedure_code
            ).limit(20)
        )
        return result.scalars().all()

    async def determine_compliance_mode(self, procedure_code: str, dut_rule=None) -> str:
        """Determina o modo de compliance: rol_dut, cobertura_direta, ou fora_do_rol."""
        from app.db.models import RolProcedure

        rol_result = await self.db.execute(
            select(RolProcedure).where(
                RolProcedure.codigo_procedimento == procedure_code
            ).limit(1)
        )
        in_rol = rol_result.scalar_one_or_none()

        if not in_rol:
            return "fora_do_rol"

        if dut_rule or (in_rol and in_rol.tem_dut):
            return "rol_dut"

        return "cobertura_direta"

    def generate_suggestions(self, evaluation: DutEvaluation) -> list[str]:
        """Gera sugestões para o médico com base nos critérios não atendidos."""
        suggestions = []

        for c in evaluation.criteria_unmet:
            if c.tipo != "exclusao":
                suggestions.append(
                    f"Critério {c.id} não atendido: {c.mensagem}. "
                    f"Valor esperado: {c.valor_esperado}, valor informado: {c.valor_paciente}."
                )

        for c in evaluation.criteria_unknown:
            suggestions.append(
                f"Dado faltante para critério {c.id}: {c.mensagem}"
            )

        for doc in evaluation.documents_missing:
            suggestions.append(f"Documento/exame necessário não fornecido: {doc}")

        if evaluation.exclusion_triggered:
            suggestions.append(
                f"ALERTA: Exclusão de cobertura ativada — {evaluation.exclusion_triggered.mensagem}"
            )

        return suggestions
