"""Contabilidade de custo das chamadas de LLM.

Contexto: uma auditoria mostrou que o custo reportado ao médico e persistido no
Report podia estar errado em três direções diferentes — superestimado (cache
ignorado), subestimado (retries que falham) ou simplesmente inventado (modelo
fora da tabela caindo no preço do gpt-4o em silêncio).
"""
import pytest

from app.services.agents.token_tracker import (
    PRICING,
    USD_TO_BRL,
    PipelineUsage,
    TokenUsage,
    coletar_uso_auxiliar,
    extract_usage,
    registrar_uso_auxiliar,
    usage_from_exception,
)


class _FakeDetalhePrompt:
    def __init__(self, cached=0):
        self.cached_tokens = cached


class _FakeDetalheCompletion:
    def __init__(self, reasoning=0):
        self.reasoning_tokens = reasoning


class _FakeUsage:
    def __init__(self, prompt=0, completion=0, total=0, cached=None, reasoning=None):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = total or (prompt + completion)
        self.prompt_tokens_details = _FakeDetalhePrompt(cached) if cached is not None else None
        self.completion_tokens_details = _FakeDetalheCompletion(reasoning) if reasoning is not None else None


class _FakeResponse:
    def __init__(self, usage):
        self.usage = usage


class TestPrecoDeCache:
    def test_cache_custa_metade(self):
        """Tokens em cache têm 50% de desconto — ignorá-los SUPERestimava."""
        sem_cache = TokenUsage("A", "gpt-4o", prompt_tokens=1_000_000)
        sem_cache.calculate_cost()
        com_cache = TokenUsage("A", "gpt-4o", prompt_tokens=1_000_000, cached_tokens=1_000_000)
        com_cache.calculate_cost()
        assert sem_cache.cost_usd == pytest.approx(2.50)
        assert com_cache.cost_usd == pytest.approx(1.25)

    def test_cache_parcial(self):
        u = TokenUsage("A", "gpt-4o", prompt_tokens=1_000_000, cached_tokens=400_000)
        u.calculate_cost()
        # 600k a 2.50 + 400k a 1.25
        assert u.cost_usd == pytest.approx(0.6 * 2.50 + 0.4 * 1.25)

    def test_cache_maior_que_prompt_nao_gera_credito(self):
        """Guarda contra dado inconsistente da API virar custo negativo."""
        u = TokenUsage("A", "gpt-4o", prompt_tokens=1000, cached_tokens=999_999)
        u.calculate_cost()
        assert u.cost_usd >= 0

    def test_todos_os_modelos_tem_preco_de_cache(self):
        for modelo, precos in PRICING.items():
            assert "cached_input" in precos, f"{modelo} sem preço de cache"
            assert precos["cached_input"] < precos["input"]


class TestModeloDesconhecido:
    def test_marca_custo_como_nao_confiavel(self):
        """Antes: caía no preço do gpt-4o silenciosamente."""
        u = TokenUsage("A", "modelo-que-nao-existe", prompt_tokens=1000)
        u.calculate_cost()
        assert u.preco_conhecido is False
        assert u.to_dict()["preco_conhecido"] is False

    def test_modelo_conhecido_nao_marca(self):
        u = TokenUsage("A", "gpt-4o-mini", prompt_tokens=1000)
        u.calculate_cost()
        assert u.preco_conhecido is True
        assert "preco_conhecido" not in u.to_dict()

    def test_pipeline_propaga_a_desconfianca(self):
        p = PipelineUsage()
        bom = TokenUsage("A", "gpt-4o", prompt_tokens=10); bom.calculate_cost()
        ruim = TokenUsage("B", "modelo-x", prompt_tokens=10); ruim.calculate_cost()
        p.add(bom)
        assert p.custo_confiavel is True
        p.add(ruim)
        assert p.custo_confiavel is False
        assert p.to_dict()["totals"]["custo_confiavel"] is False


class TestExtractUsage:
    def test_le_cached_e_reasoning(self):
        r = _FakeResponse(_FakeUsage(prompt=1000, completion=500, cached=800, reasoning=100))
        u = extract_usage(r, "Redator", model="gpt-4o")
        assert u.cached_tokens == 800
        assert u.reasoning_tokens == 100
        assert u.to_dict()["cached_tokens"] == 800

    def test_sem_detalhes_nao_quebra(self):
        r = _FakeResponse(_FakeUsage(prompt=100, completion=50))
        r.usage.prompt_tokens_details = None
        r.usage.completion_tokens_details = None
        u = extract_usage(r, "Redator", model="gpt-4o")
        assert u.cached_tokens == 0 and u.prompt_tokens == 100

    def test_resposta_sem_usage(self):
        u = extract_usage(_FakeResponse(None), "Redator", model="gpt-4o")
        assert u.total_tokens == 0 and u.cost_usd == 0

    def test_contrato_quebrado_gera_aviso(self, caplog):
        """Se a API mudar (Responses API usa input_tokens), o zero silencioso
        viraria custo R$0,00 sem erro nenhum."""
        import logging
        with caplog.at_level(logging.WARNING):
            extract_usage(_FakeResponse(_FakeUsage(prompt=0, completion=0)), "X", model="gpt-4o")
        assert any("[CUSTO]" in r.message for r in caplog.records)


class TestCustoDeTentativasQueFalharam:
    def test_recupera_total_usage_da_excecao(self):
        """Instructor guarda o consumo de TODAS as tentativas na exceção."""
        class _RetryExc(Exception):
            def __init__(self):
                self.total_usage = _FakeUsage(prompt=3000, completion=300, total=3300, cached=0)

        u = usage_from_exception(_RetryExc(), "Redator", model="gpt-4o")
        assert u is not None
        assert u.total_tokens == 3300
        assert u.cost_usd > 0
        assert "falhou" in u.agent

    def test_excecao_comum_devolve_none(self):
        assert usage_from_exception(ValueError("erro qualquer"), "Redator") is None

    def test_usage_vazio_devolve_none(self):
        class _Exc(Exception):
            total_usage = _FakeUsage(prompt=0, completion=0, total=0)
        assert usage_from_exception(_Exc(), "Redator") is None


class TestColetorAuxiliar:
    def test_registra_chamadas_dentro_do_contexto(self):
        """Tradutor e filtro PT eram cobrados e não entravam em conta nenhuma."""
        p = PipelineUsage()
        r = _FakeResponse(_FakeUsage(prompt=200, completion=20))
        with coletar_uso_auxiliar(p):
            registrar_uso_auxiliar(r, "Tradutor", "gpt-4o-mini")
        assert len(p.agents) == 1
        assert p.agents[0].agent == "Tradutor"
        assert p.total_cost_usd > 0

    def test_fora_do_contexto_e_no_op(self):
        r = _FakeResponse(_FakeUsage(prompt=200, completion=20))
        registrar_uso_auxiliar(r, "Tradutor", "gpt-4o-mini")  # não deve levantar

    def test_contexto_e_restaurado(self):
        p1, p2 = PipelineUsage(), PipelineUsage()
        r = _FakeResponse(_FakeUsage(prompt=100, completion=10))
        with coletar_uso_auxiliar(p1):
            with coletar_uso_auxiliar(p2):
                registrar_uso_auxiliar(r, "B", "gpt-4o-mini")
            registrar_uso_auxiliar(r, "A", "gpt-4o-mini")
        assert [u.agent for u in p1.agents] == ["A"]
        assert [u.agent for u in p2.agents] == ["B"]

    async def test_tasks_concorrentes_nao_se_misturam(self):
        """ContextVar é por-task: dois laudos simultâneos não somam um no outro."""
        import asyncio
        r = _FakeResponse(_FakeUsage(prompt=100, completion=10))

        async def _laudo(nome, coletor):
            with coletar_uso_auxiliar(coletor):
                await asyncio.sleep(0)
                registrar_uso_auxiliar(r, nome, "gpt-4o-mini")

        a, b = PipelineUsage(), PipelineUsage()
        await asyncio.gather(_laudo("A", a), _laudo("B", b))
        assert [u.agent for u in a.agents] == ["A"]
        assert [u.agent for u in b.agents] == ["B"]


class TestTotais:
    def test_soma_e_conversao(self):
        p = PipelineUsage()
        for _ in range(2):
            u = TokenUsage("A", "gpt-4o", prompt_tokens=1_000_000)
            u.calculate_cost()
            p.add(u)
        assert p.total_cost_usd == pytest.approx(5.00)
        assert p.total_cost_brl == pytest.approx(5.00 * USD_TO_BRL)
        assert p.to_dict()["totals"]["prompt_tokens"] == 2_000_000
