"""
Pydantic models para structured outputs via Instructor.
Forçam schema JSON válido dos agentes Writer e Auditor.
"""
from pydantic import BaseModel, Field
from typing import Optional


# ─── Writer (Agente B) ───────────────────────────────────────────────────────

class WriterOutput(BaseModel):
    """Structured output do Agente Redator.

    O relatório é escrito em SEÇÕES independentes com mínimos por seção — o
    Instructor (max_retries) força a regeneração de qualquer seção curta demais.
    O corpo final `justificativa_completa` é MONTADO em código a partir destas
    seções (writer.py), não gerado separadamente.
    Alvo do corpo (soma das seções): 3.000 a 4.500 caracteres.
    """

    quadro_clinico: str = Field(
        description=(
            "SEÇÃO 1 — Quadro clínico e história: patologia, estadiamento/gravidade, "
            "CID-10 do paciente citado no texto, e a cascata de degeneração fisiopatológica. "
            "MÍNIMO 600 caracteres. NÃO inclua RNs da ANS."
        ),
        min_length=600,
    )
    falha_terapeutica: str = Field(
        description=(
            "SEÇÃO 2 — Falha terapêutica prévia: tratamentos conservadores exauridos, "
            "COM datas/duração (ex: 'AINEs e fisioterapia por 12 semanas, de jan a abr/2025'). "
            "MÍNIMO 400 caracteres."
        ),
        min_length=400,
    )
    justificativa_tecnica: str = Field(
        description=(
            "SEÇÃO 3 — Justificativa técnica e superioridade: mecanismo de ação APROFUNDADO, "
            "diferenciais vs. alternativas genéricas, dados técnicos oficiais do produto. "
            "MÍNIMO 800 caracteres. NÃO inclua RNs da ANS."
        ),
        min_length=800,
    )
    evidencia_cientifica: str = Field(
        description=(
            "SEÇÃO 4 — Evidência científica: síntese das evidências fornecidas, "
            "CADA afirmação com citação (Autor et al., Ano). Cite TODAS as evidências recebidas. "
            "MÍNIMO 500 caracteres."
        ),
        min_length=500,
    )
    risco_nao_realizacao: str = Field(
        description=(
            "SEÇÃO 5 — Risco da não realização: progressão da doença, perda funcional, "
            "necessidade futura de procedimento de maior porte. Sem argumento financeiro. "
            "MÍNIMO 400 caracteres."
        ),
        min_length=400,
    )
    conclusao: str = Field(
        description=(
            "SEÇÃO 6 — Conclusão e pedido formal: parágrafo de encerramento pedindo a liberação. "
            "MÍNIMO 200 caracteres."
        ),
        min_length=200,
    )
    diagnostico_resumo: str = Field(
        description="Descrição clínica concisa do diagnóstico do paciente (1-2 frases)",
    )
    base_legal: str = Field(
        description=(
            "Citação das RN 424, 428/465 e 395 da ANS + Código de Ética Médica. "
            "Toda fundamentação legal vai EXCLUSIVAMENTE aqui, NUNCA nas seções acima."
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
