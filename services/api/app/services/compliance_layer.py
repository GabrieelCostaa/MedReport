"""
Camada de Compliance ANS integrada ao pipeline.

Orquestra DutEngine, TussValidator e ApprovalScore para validação
regulatória completa antes e depois da geração do relatório.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dut_engine import DutEngine, DutEvaluation
from app.services.tuss_validator import TussValidator, TussValidation, TissValidation, AnvisaStatusResult
from app.services.approval_score import ApprovalScore, compute_approval_score

logger = logging.getLogger(__name__)


@dataclass
class ComplianceContext:
    """Contexto de compliance passado ao Writer e Auditor."""
    mode: str = "cobertura_direta"  # rol_dut | fora_do_rol | cobertura_direta
    dut_rule: object = None
    dut_evaluation: Optional[DutEvaluation] = None
    dut_criteria_text: str = ""
    dut_suggestions: list[str] = field(default_factory=list)
    tuss_validation: Optional[TussValidation] = None
    tiss_validation: Optional[TissValidation] = None
    anvisa_status: Optional[AnvisaStatusResult] = None
    approval_score: Optional[ApprovalScore] = None
    rol_alternatives: list = field(default_factory=list)
    stf_checklist: Optional[dict] = None


@dataclass
class StfChecklist:
    """Checklist dos 5 critérios cumulativos do STF (ADI 7.265, 2025)."""
    prescricao_medica: dict = field(default_factory=lambda: {
        "atendido": False, "tipo": "automatizavel", "evidencia": None
    })
    sem_negativa_ans: dict = field(default_factory=lambda: {
        "atendido": False, "tipo": "declaratorio",
        "evidencia": None,
        "alerta": "Campo declaratório — não verificável automaticamente. "
                  "Não existe fonte machine-readable para status de propostas na ANS.",
    })
    sem_alternativa_rol: dict = field(default_factory=lambda: {
        "atendido": False, "tipo": "automatizavel", "evidencia": None,
        "alternativas_analisadas": [],
    })
    evidencia_cientifica: dict = field(default_factory=lambda: {
        "atendido": False, "tipo": "automatizavel", "evidencia": None, "nivel": None,
    })
    registro_anvisa: dict = field(default_factory=lambda: {
        "atendido": False, "tipo": "automatizavel", "evidencia": None,
    })

    def to_dict(self) -> dict:
        return {
            "1_prescricao_medica": self.prescricao_medica,
            "2_sem_negativa_ans": self.sem_negativa_ans,
            "3_sem_alternativa_rol": self.sem_alternativa_rol,
            "4_evidencia_cientifica": self.evidencia_cientifica,
            "5_registro_anvisa": self.registro_anvisa,
        }

    @property
    def all_met(self) -> bool:
        return all([
            self.prescricao_medica["atendido"],
            self.sem_negativa_ans["atendido"],
            self.sem_alternativa_rol["atendido"],
            self.evidencia_cientifica["atendido"],
            self.registro_anvisa["atendido"],
        ])


async def build_compliance_context(
    db: AsyncSession,
    procedure_code: str,
    patient_data: dict,
    produto_registro_anvisa: str = "",
    medico_crm: str = "",
    declaracao_ans: bool = False,
    evidence_count: int = 0,
    evidence_levels: list[str] | None = None,
    on_progress=None,
) -> ComplianceContext:
    """
    Constrói contexto de compliance completo para o pipeline.
    Chamado pelo Researcher Agent antes de passar ao Writer.
    """
    ctx = ComplianceContext()
    engine = DutEngine(db)
    validator = TussValidator(db)

    async def _emit(msg: str):
        if on_progress:
            await on_progress("compliance", msg)

    # 1. Determinar modo de compliance
    await _emit("Verificando cobertura do procedimento no Rol da ANS...")
    dut_rule = await engine.find_dut_for_procedure(procedure_code)
    ctx.mode = await engine.determine_compliance_mode(procedure_code, dut_rule)
    ctx.dut_rule = dut_rule

    if ctx.mode == "rol_dut":
        await _emit(f"DUT encontrada para procedimento — modo Rol/DUT ativado")
    elif ctx.mode == "fora_do_rol":
        await _emit("Procedimento não encontrado no Rol — modo Fora do Rol ativado")
    else:
        await _emit("Procedimento no Rol sem DUT condicionante — cobertura direta")

    # 2. Avaliar DUT se aplicável
    if dut_rule and dut_rule.criterios_dsl:
        await _emit(f"Avaliando critérios da DUT {dut_rule.numero_dut}...")
        ctx.dut_evaluation = await engine.evaluate_criteria(dut_rule, patient_data)
        ctx.dut_suggestions = engine.generate_suggestions(ctx.dut_evaluation)

        if dut_rule.criterios_texto:
            ctx.dut_criteria_text = dut_rule.criterios_texto[:2000]

        met = len(ctx.dut_evaluation.criteria_met)
        total = ctx.dut_evaluation.total_criteria
        await _emit(f"DUT: {met}/{total} critérios atendidos")

        if ctx.dut_suggestions:
            await _emit(f"{len(ctx.dut_suggestions)} sugestão(ões) para o médico")

    # 3. Validar TUSS
    if procedure_code:
        await _emit("Validando código TUSS contra base oficial...")
        ctx.tuss_validation = await validator.validate_opme_code(procedure_code)
        if ctx.tuss_validation.valido:
            await _emit(f"TUSS {procedure_code} válido: {ctx.tuss_validation.nome}")
        else:
            await _emit(f"ALERTA: {ctx.tuss_validation.mensagem}")

    # 3b. Validar TISS — determinar campo correto baseado no tipo de código
    if procedure_code and ctx.tuss_validation:
        await _emit("Validando campo TISS para solicitação de OPME...")
        # Detect if this is a material (Table 19) or procedure (Table 22) code
        tiss_campo = "Mat/Med"
        if "Tabela 22" in (ctx.tuss_validation.mensagem or ""):
            tiss_campo = "Procedimento"
        ctx.tiss_validation = await validator.validate_tiss_field(
            tipo_guia="SP/SADT",
            campo=tiss_campo,
            codigo=procedure_code,
        )
        if ctx.tiss_validation.permitido:
            await _emit(f"TISS OK: campo {tiss_campo} ({ctx.tiss_validation.mensagem})")
        else:
            await _emit(f"ALERTA TISS: {ctx.tiss_validation.mensagem}")

    # 4. Verificar Anvisa
    if produto_registro_anvisa:
        await _emit("Verificando registro Anvisa...")
        ctx.anvisa_status = await validator.check_anvisa_status(produto_registro_anvisa)
        if ctx.anvisa_status.alerta:
            await _emit(f"ALERTA ANVISA: {ctx.anvisa_status.alerta}")
        else:
            await _emit(f"Anvisa: registro {produto_registro_anvisa} — {ctx.anvisa_status.status}")

    # 5. Modo Fora do Rol: checklist STF
    if ctx.mode == "fora_do_rol":
        await _emit("Construindo checklist STF (ADI 7.265)...")
        ctx.stf_checklist = _build_stf_checklist(
            medico_crm=medico_crm,
            declaracao_ans=declaracao_ans,
            rol_alternatives=await engine.find_rol_alternatives(procedure_code),
            evidence_count=evidence_count,
            evidence_levels=evidence_levels,
            anvisa_status=ctx.anvisa_status,
        )
        ctx.rol_alternatives = ctx.stf_checklist.get("alternativas", [])

    # 6. Calcular score
    await _emit("Calculando completude documental estimada...")
    ctx.approval_score = compute_approval_score(
        dut_evaluation=ctx.dut_evaluation,
        tuss_validation=ctx.tuss_validation,
        tiss_validation=ctx.tiss_validation,
        anvisa_status=ctx.anvisa_status,
        evidence_count=evidence_count,
        evidence_levels=evidence_levels,
        has_justification=False,
        cid_procedure_consistent=True,
    )
    await _emit(
        f"Score de completude: {ctx.approval_score.score}/100 ({ctx.approval_score.nivel})"
    )

    return ctx


def _build_stf_checklist(
    medico_crm: str = "",
    declaracao_ans: bool = False,
    rol_alternatives: list = None,
    evidence_count: int = 0,
    evidence_levels: list[str] | None = None,
    anvisa_status: AnvisaStatusResult | None = None,
) -> dict:
    """Constrói checklist STF (ADI 7.265)."""
    checklist = StfChecklist()

    # 1. Prescrição médica
    if medico_crm:
        checklist.prescricao_medica["atendido"] = True
        checklist.prescricao_medica["evidencia"] = f"CRM: {medico_crm}"

    # 2. Sem negativa ANS (declaratório)
    if declaracao_ans:
        checklist.sem_negativa_ans["atendido"] = True
        checklist.sem_negativa_ans["evidencia"] = "Declaração do médico"

    # 3. Sem alternativa no Rol
    alternatives = rol_alternatives or []
    if not alternatives:
        checklist.sem_alternativa_rol["atendido"] = True
        checklist.sem_alternativa_rol["evidencia"] = "Nenhuma alternativa encontrada no Rol"
    else:
        checklist.sem_alternativa_rol["alternativas_analisadas"] = [
            {"codigo": getattr(a, "codigo_procedimento", ""), "nome": getattr(a, "nome", "")}
            for a in alternatives[:5]
        ]

    # 4. Evidência científica
    levels = evidence_levels or []
    high_level = any(
        l.lower() in ("meta-analise", "meta_analise", "rct", "ecr", "ensaio_clinico", "revisao-sistematica")
        for l in levels
    )
    if evidence_count > 0 and high_level:
        checklist.evidencia_cientifica["atendido"] = True
        checklist.evidencia_cientifica["evidencia"] = f"{evidence_count} referências, nível alto"
        checklist.evidencia_cientifica["nivel"] = "alto"
    elif evidence_count > 0:
        checklist.evidencia_cientifica["atendido"] = True
        checklist.evidencia_cientifica["evidencia"] = f"{evidence_count} referências"
        checklist.evidencia_cientifica["nivel"] = "medio"

    # 5. Registro Anvisa
    if anvisa_status and anvisa_status.status == "ativo":
        checklist.registro_anvisa["atendido"] = True
        checklist.registro_anvisa["evidencia"] = f"Registro {anvisa_status.registro} ativo"
    elif anvisa_status:
        checklist.registro_anvisa["evidencia"] = f"Registro {anvisa_status.registro}: {anvisa_status.status}"

    return {
        "checklist": checklist.to_dict(),
        "all_met": checklist.all_met,
        "alternativas": [
            {"codigo": getattr(a, "codigo_procedimento", ""), "nome": getattr(a, "nome", "")}
            for a in (alternatives or [])[:5]
        ],
    }


def build_writer_dut_prompt(ctx: ComplianceContext) -> str:
    """Gera instrução adicional para o Writer baseada no contexto de compliance."""
    if ctx.mode == "cobertura_direta":
        return ""

    parts = []

    if ctx.mode == "rol_dut" and ctx.dut_rule:
        parts.append(
            f"\n\nINSTRUÇÃO DE COMPLIANCE (DUT {ctx.dut_rule.numero_dut}):\n"
            f"Este procedimento possui Diretriz de Utilização condicionante. "
            f"O texto DEVE demonstrar aderência a CADA critério da DUT.\n"
        )
        if ctx.dut_criteria_text:
            parts.append(f"Texto oficial da DUT:\n{ctx.dut_criteria_text}\n")

        if ctx.dut_evaluation:
            if ctx.dut_evaluation.criteria_met:
                parts.append("Critérios JÁ atendidos pelo paciente:")
                for c in ctx.dut_evaluation.criteria_met:
                    parts.append(f"  - {c.id}: {c.mensagem} (valor: {c.valor_paciente})")

            if ctx.dut_evaluation.criteria_unmet:
                parts.append("\nCritérios NÃO atendidos (abordar com cuidado):")
                for c in ctx.dut_evaluation.criteria_unmet:
                    parts.append(f"  - {c.id}: {c.mensagem}")

    elif ctx.mode == "fora_do_rol":
        parts.append(
            "\n\nINSTRUÇÃO DE COMPLIANCE (MODO FORA DO ROL):\n"
            "Este procedimento/material NÃO está no Rol da ANS. "
            "O texto deve ser estruturado como argumentação técnica para cobertura excepcional.\n\n"
            "Base legal: Lei 14.454/2022, STF ADI 7.265 (2025).\n"
            "Critérios cumulativos do STF que devem ser demonstrados:\n"
            "1. Prescrição por médico assistente\n"
            "2. Inexistência de negativa expressa pela ANS\n"
            "3. Inexistência de alternativa terapêutica adequada no Rol\n"
            "4. Evidência científica de alto nível\n"
            "5. Registro ativo na Anvisa\n\n"
            "IMPORTANTE: Demonstre por que alternativas do Rol NÃO atendem este paciente.\n"
            "Use linguagem técnico-clínica estruturada, NÃO parecer jurídico.\n"
        )

    return "\n".join(parts)


def build_auditor_compliance_instructions(ctx: ComplianceContext) -> str:
    """Gera instrução adicional para o Auditor baseada no contexto de compliance."""
    parts = []

    if ctx.mode == "rol_dut" and ctx.dut_evaluation:
        parts.append(
            "\nVERIFICAÇÃO DUT OBRIGATÓRIA:\n"
            "Confirme que o texto aborda TODOS os critérios da DUT.\n"
        )
        for c in ctx.dut_evaluation.criteria_met:
            parts.append(f"  [OK] Critério {c.id}: {c.mensagem}")
        for c in ctx.dut_evaluation.criteria_unmet:
            parts.append(f"  [FALTA] Critério {c.id}: {c.mensagem}")
        for c in ctx.dut_evaluation.criteria_unknown:
            parts.append(f"  [?] Critério {c.id}: {c.mensagem}")

    if ctx.anvisa_status and ctx.anvisa_status.alerta:
        parts.append(f"\nALERTA ANVISA: {ctx.anvisa_status.alerta}")

    return "\n".join(parts)
