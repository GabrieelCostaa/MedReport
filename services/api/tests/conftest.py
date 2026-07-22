"""Fixtures compartilhados para todos os testes."""
import os
import uuid
from dataclasses import dataclass
from typing import Optional

import pytest
from dotenv import load_dotenv

load_dotenv()

# Garante SECRET_KEY válida para testes (evita sys.exit no startup check)
if not os.environ.get("SECRET_KEY") or len(os.environ.get("SECRET_KEY", "")) < 32:
    os.environ["SECRET_KEY"] = "chave-de-teste-para-pytest-nao-usar-em-producao-64chars!!"


# ─── Testes que chamam a OpenAI de verdade ──────────────────────────────────
# Antes o guard era `not os.environ.get("OPENAI_API_KEY")`. Como o load_dotenv()
# acima carrega a chave real do .env, ele NUNCA pulava na máquina de quem
# desenvolve: `pytest tests/` disparava o pipeline completo contra a API,
# gastando dinheiro e travando sem timeout. Agora é opt-in explícito:
#   pytest tests/                    → offline, grátis, determinístico
#   RUN_LLM_TESTS=1 pytest tests/    → inclui os testes que gastam
RUN_LLM_TESTS = os.environ.get("RUN_LLM_TESTS", "").lower() in ("1", "true", "yes")
SKIP_LLM = not RUN_LLM_TESTS
SKIP_LLM_REASON = "Teste que chama a OpenAI de verdade — habilite com RUN_LLM_TESTS=1"


# Teto de tempo por teste. Vale sobretudo para RUN_LLM_TESTS=1: uma chamada
# lenta ou throttled da OpenAI pendura o teste indefinidamente (o SDK tem
# timeout próprio alto + retries). Usa signal.alarm da stdlib em vez de
# pytest-timeout para não adicionar dependência de teste ao projeto.
TEST_TIMEOUT_SECONDS = int(os.environ.get("TEST_TIMEOUT_SECONDS", "180" if RUN_LLM_TESTS else "60"))


@pytest.fixture(autouse=True)
def _timeout_por_teste():
    import signal

    if not hasattr(signal, "SIGALRM"):  # Windows
        yield
        return

    def _estourou(signum, frame):
        raise TimeoutError(
            f"Teste excedeu {TEST_TIMEOUT_SECONDS}s — provavelmente travado em rede. "
            "Ajuste com TEST_TIMEOUT_SECONDS."
        )

    anterior = signal.signal(signal.SIGALRM, _estourou)
    signal.alarm(TEST_TIMEOUT_SECONDS)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, anterior)


_EXIT_STATUS = {"code": 0}


def pytest_sessionfinish(session, exitstatus):
    """Guarda o código de saída para o encerramento forçado do unconfigure."""
    _EXIT_STATUS["code"] = int(exitstatus)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    """Encerra o processo à força no fim de tudo (resumo já impresso).

    Os testes rodam inteiros em ~15s, mas o pytest ficava pendurado
    indefinidamente DEPOIS de imprimir o relatório: alguma biblioteca de
    terceiros (bibliotecas de avaliação/telemetria importadas pelos testes)
    deixa uma thread não-daemon parada em accept() de socket, e o interpretador
    espera por ela para sempre. Já vimos a suíte "rodar" por 50 minutos assim.

    Não há como fechar essa thread de fora, então saímos explicitamente com o
    código que o pytest apurou. É feito no `unconfigure` (e não no
    `sessionfinish`) porque o resumo final — "N passed in Xs" — é escrito por
    um hookwrapper do terminal que só retoma DEPOIS dos hooks comuns: sair
    antes disso engoliria o relatório.

    Desative com KEEP_PYTEST_ALIVE=1 se precisar depurar o teardown.
    """
    if os.environ.get("KEEP_PYTEST_ALIVE"):
        return
    import sys
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_EXIT_STATUS["code"])


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
