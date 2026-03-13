"""Fixtures compartilhados para todos os testes."""
import uuid
from dataclasses import dataclass
from typing import Optional

import pytest
from dotenv import load_dotenv

load_dotenv()


@dataclass
class MockProduct:
    """Produto mock para testes sem banco de dados."""
    id: uuid.UUID = None
    nome: str = "Kit EC2 - Linha Opus"
    linha: str = "Opus"
    descricao_tecnica: str = "Sistema de viscossuplementação à base de ácido hialurônico"
    diferenciais_clinicos: str = "Alto peso molecular (6.000 kDa), aplicação única"
    indicacoes: str = "Osteoartrite de joelho graus II e III"
    contraindicacoes: str = "Infecção articular ativa"
    viscosidade: str = "80.000 - 120.000 mPa.s"
    peso_molecular: str = "6.000 kDa"
    concentracao: str = "10 mg/mL de hialuronato de sódio"
    registro_anvisa: str = "80117900YYY"
    codigo_tuss_sugerido: str = "20104120"
    bula_url: str = ""
    referencias_bibliograficas: list = None

    def __post_init__(self):
        if self.id is None:
            self.id = uuid.uuid4()
        if self.referencias_bibliograficas is None:
            self.referencias_bibliograficas = [
                "Altman RD, et al. Semin Arthritis Rheum. 2015;45(2):140-9.",
                "Bellamy N, et al. Cochrane Database Syst Rev. 2006;(2):CD005321.",
            ]


@dataclass
class MockProductAdhesion:
    """Produto Adhesion STP+ mock."""
    id: uuid.UUID = None
    nome: str = "Adhesion STP+"
    linha: str = "Adhesion"
    descricao_tecnica: str = "Barreira anti-aderência biorreabsorvível"
    diferenciais_clinicos: str = "Prevenção de aderências pós-cirúrgicas"
    indicacoes: str = "Cirurgias abdominais"
    contraindicacoes: str = "Hipersensibilidade"
    viscosidade: str = "10.000 - 29.000 mPa.s"
    peso_molecular: str = "Não aplicável (barreira anti-aderência)"
    concentracao: str = "CMC sódica + ácido hialurônico em proporção proprietária"
    registro_anvisa: str = "80117900XXX"
    codigo_tuss_sugerido: str = "30715016"
    bula_url: str = ""
    referencias_bibliograficas: list = None

    def __post_init__(self):
        if self.id is None:
            self.id = uuid.uuid4()
        if self.referencias_bibliograficas is None:
            self.referencias_bibliograficas = [
                "Diamond MP, et al. Fertil Steril. 1996;66(6):904-10.",
            ]


@dataclass
class MockReport:
    """Report mock para testes de checklist."""
    id: uuid.UUID = None
    diagnosis: str = ""
    justificativa_ia: str = ""
    falha_terapeutica: str = ""
    risco_nao_realizacao: str = ""
    base_legal_ans: str = ""
    referencias_bib: list = None

    def __post_init__(self):
        if self.id is None:
            self.id = uuid.uuid4()


@dataclass
class MockTemplate:
    """Template mock."""
    id: uuid.UUID = None
    nome: str = "Template Viscossuplementação"
    especialidade: str = "Ortopedia"
    produto_id: uuid.UUID = None
    tom_de_voz: str = "Científico, formal e assertivo"
    template_corpo: str = "O paciente {paciente_nome}..."
    bases_legais: list = None
    referencias_padrao: list = None
    exemplos_aprovados: list = None

    def __post_init__(self):
        if self.id is None:
            self.id = uuid.uuid4()
        if self.bases_legais is None:
            self.bases_legais = ["RN 395", "RN 424"]
        if self.referencias_padrao is None:
            self.referencias_padrao = ["Altman RD, et al. 2015"]


@pytest.fixture
def opus_product():
    return MockProduct()


@pytest.fixture
def adhesion_product():
    return MockProductAdhesion()


@pytest.fixture
def complete_report():
    """Relatório completo que deve passar no checklist."""
    return MockReport(
        diagnosis="Gonartrose bilateral CID M17.0, grau III Kellgren-Lawrence",
        justificativa_ia=(
            "Paciente Ana C., 62 anos, com diagnóstico de gonartrose bilateral (CID M17.0), "
            "classificada como grau III pela escala de Kellgren-Lawrence, apresenta dor articular "
            "crônica com limitação funcional significativa que compromete as atividades diárias. "
            "Após insucesso com tratamento conservador incluindo analgésicos e fisioterapia por "
            "6 meses sem melhora funcional, indica-se viscossuplementação com Kit EC2 - Linha Opus, "
            "ácido hialurônico de alto peso molecular (6.000 kDa) com concentração de 10 mg/mL. "
            "Conforme a RN 395 da ANS, em caso de divergência quanto à indicação do material, "
            "a operadora deverá apresentar justificativa técnica por escrito."
        ),
        falha_terapeutica="Insucesso com analgésicos, AINEs por 6 meses e fisioterapia sem ganho de ADM",
        risco_nao_realizacao="Progressão da degeneração articular com perda funcional irreversível",
        base_legal_ans="RN 395, RN 424, RN 465 da ANS",
        referencias_bib=[
            "Altman RD, et al. Semin Arthritis Rheum. 2015;45(2):140-9.",
            "Bellamy N, et al. Cochrane Database Syst Rev. 2006;(2):CD005321.",
        ],
    )


@pytest.fixture
def incomplete_report():
    """Relatório incompleto que deve falhar no checklist."""
    return MockReport(
        diagnosis="Dor no joelho",
        justificativa_ia="Texto curto",
        falha_terapeutica="",
        risco_nao_realizacao="",
        base_legal_ans="",
        referencias_bib=[],
    )


@pytest.fixture
def template():
    return MockTemplate()
