"""
Pydantic models para structured outputs via Instructor.
Forçam schema JSON válido dos agentes Writer e Auditor.
"""
from pydantic import BaseModel, Field
from typing import Optional


# ─── Writer (Agente B) ───────────────────────────────────────────────────────

class WriterOutput(BaseModel):
    """Structured output do Agente Redator."""

    justificativa_completa: str = Field(
        description=(
            "Texto COMPLETO da justificativa técnica médica. MÍNIMO 1500 caracteres. "
            "Inclua TODAS as seções: quadro clínico, falha terapêutica, justificativa técnica, "
            "risco da não realização. NÃO inclua RNs da ANS aqui."
        ),
        min_length=200,
    )
    diagnostico_resumo: str = Field(
        description="Descrição clínica concisa do diagnóstico do paciente",
    )
    falha_terapeutica: str = Field(
        description="Descrição detalhada dos tratamentos conservadores que falharam",
    )
    risco_nao_realizacao: str = Field(
        description="Consequências clínicas da não aprovação do material",
    )
    base_legal: str = Field(
        description=(
            "Citação das RN 424, 428/465 e 395 da ANS + Código de Ética Médica. "
            "Toda fundamentação legal vai EXCLUSIVAMENTE aqui."
        ),
    )
    referencias: list[str] = Field(
        description="Lista de referências bibliográficas citadas no texto (Autor et al., Ano)",
        default_factory=list,
    )


# ─── Auditor (Agente C) ──────────────────────────────────────────────────────

class AuditLogEntry(BaseModel):
    """Uma entrada no log de auditoria."""
    tipo: str = Field(description="Tipo: 'correcao', 'remocao' ou 'validacao'")
    campo: str = Field(description="Campo afetado (ex: 'viscosidade', 'referencia')")
    original: str = Field(default="", description="Valor original no rascunho")
    corrigido: str = Field(default="", description="Valor corrigido")
    motivo: str = Field(default="", description="Explicação de POR QUE a correção foi feita")


class AuditorChecklist(BaseModel):
    """Checklist de 6 itens obrigatórios."""
    diagnostico: bool = Field(description="Diagnóstico presente no texto")
    justificativa_tecnica: bool = Field(description="Justificativa técnica com diferenciais do material")
    falha_terapeutica: bool = Field(description="Falha terapêutica prévia descrita")
    risco_nao_realizacao: bool = Field(description="Risco da não realização descrito")
    base_legal_ans: bool = Field(description="Base legal ANS (RN 395) presente")
    referencia_bibliografica: bool = Field(description="Referência bibliográfica presente")


class AuditorOutput(BaseModel):
    """Structured output do Agente Auditor com Chain-of-Thought."""

    chain_of_thought: str = Field(
        description=(
            "Raciocínio passo a passo da auditoria. "
            "Para CADA dado técnico (viscosidade, peso molecular, concentração, ANVISA): "
            "1) Identifique o valor no rascunho. "
            "2) Compare com o valor oficial. "
            "3) Explique se está correto ou se precisa correção e POR QUÊ. "
            "Para CADA referência: verifique se o autor está na lista de autores conhecidos. "
            "Este campo é para auditoria interna — não aparece no relatório final."
        ),
    )
    texto_corrigido: str = Field(
        description="Texto final da justificativa após todas as correções",
    )
    aprovado: bool = Field(
        description="True se TODOS os 6 itens do checklist estão presentes",
    )
    checklist: AuditorChecklist = Field(
        description="Status de cada um dos 6 itens obrigatórios",
    )
    audit_log: list[AuditLogEntry] = Field(
        description="Log detalhado de todas as correções, remoções e validações realizadas",
        default_factory=list,
    )
    referencias_validadas: list[str] = Field(
        description="Lista de referências que passaram na validação (autor encontrado nas fontes)",
        default_factory=list,
    )
