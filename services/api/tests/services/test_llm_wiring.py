"""Fase 0: prova que o compliance chega no prompt e o autofill de especialidade
dispara o few-shot — a fiação que estava morta.

Também cobre o blend de qualidade no approval_score e o factory de mínimos
por evidência.
"""
import pytest

from app.services.approval_score import compute_approval_score
from app.services.agents.schemas import WriterOutput, build_writer_output_model


class TestComplianceReachesPrompts:
    """build_writer_dut_prompt/build_auditor_compliance_instructions eram dead code."""

    @pytest.mark.asyncio
    async def test_writer_receives_compliance_block(self, opus_product, monkeypatch):
        """O bloco <compliance_instructions> precisa entrar no system prompt."""
        from app.services.agents import writer as writer_mod
        from app.services.agents.researcher import ResearchResult

        captured = {}

        class _FakeCompletions:
            async def create(self, **kwargs):
                captured["messages"] = kwargs.get("messages", [])
                raise RuntimeError("stop after capture")

        class _FakeChat:
            completions = _FakeCompletions()

        class _FakeClient:
            def __init__(self, **kw):
                self.chat = _FakeChat()

        import openai
        monkeypatch.setattr(openai, "AsyncOpenAI", _FakeClient)
        monkeypatch.setattr(writer_mod, "INSTRUCTOR_AVAILABLE", False)

        dut_text = "INSTRUÇÃO DE COMPLIANCE (DUT 64): critério idade >= 50 anos"
        await writer_mod.write_justification(
            research=ResearchResult(),
            product=opus_product,
            template=None,
            medico_inputs={"diagnostico": "gonartrose", "cid": "M17.1"},
            compliance_prompt=dut_text,
        )
        system = captured["messages"][0]["content"]
        assert "<compliance_instructions" in system
        assert "DUT 64" in system

    @pytest.mark.asyncio
    async def test_writer_without_compliance_has_no_block(self, opus_product, monkeypatch):
        from app.services.agents import writer as writer_mod
        from app.services.agents.researcher import ResearchResult

        captured = {}

        class _FakeCompletions:
            async def create(self, **kwargs):
                captured["messages"] = kwargs.get("messages", [])
                raise RuntimeError("stop after capture")

        class _FakeChat:
            completions = _FakeCompletions()

        class _FakeClient:
            def __init__(self, **kw):
                self.chat = _FakeChat()

        import openai
        monkeypatch.setattr(openai, "AsyncOpenAI", _FakeClient)
        monkeypatch.setattr(writer_mod, "INSTRUCTOR_AVAILABLE", False)

        await writer_mod.write_justification(
            research=ResearchResult(),
            product=opus_product,
            template=None,
            medico_inputs={"diagnostico": "gonartrose", "cid": "M17.1"},
        )
        system = captured["messages"][0]["content"]
        assert "<compliance_instructions" not in system

    @pytest.mark.asyncio
    async def test_auditor_receives_compliance_block(self, opus_product, monkeypatch):
        from app.services.agents import auditor as auditor_mod
        from app.services.agents.writer import DraftReport

        captured = {}

        class _FakeCompletions:
            async def create(self, **kwargs):
                captured["messages"] = kwargs.get("messages", [])
                raise RuntimeError("stop after capture")

        class _FakeChat:
            completions = _FakeCompletions()

        class _FakeClient:
            def __init__(self, **kw):
                self.chat = _FakeChat()

        import openai
        monkeypatch.setattr(openai, "AsyncOpenAI", _FakeClient)
        monkeypatch.setattr(auditor_mod, "INSTRUCTOR_AVAILABLE", False)

        await auditor_mod.audit(
            DraftReport(justificativa_completa="Texto do laudo."),
            opus_product,
            compliance_instructions="VERIFICAÇÃO DUT OBRIGATÓRIA:\n[FALTA] Critério c2",
        )
        system = captured["messages"][0]["content"]
        assert "<compliance_verification" in system
        assert "[FALTA] Critério c2" in system


class TestEspecialidadeAutofill:
    def test_fewshot_fires_with_detected_specialty(self):
        """Sem especialidade o few-shot não dispara; com a detectada, dispara."""
        from app.services.agents.few_shot_examples import get_few_shot_messages
        assert get_few_shot_messages("") == []
        msgs = get_few_shot_messages("Ortopedia")
        assert len(msgs) >= 2  # par [user, assistant]


class TestApprovalScoreQualityBlend:
    def test_quality_scores_drive_the_20_points(self):
        low = compute_approval_score(
            has_justification=True,
            quality_scores={"faithfulness": 0.2, "relevancy": 0.2, "citation": 0.2},
        )
        high = compute_approval_score(
            has_justification=True,
            quality_scores={"faithfulness": 1.0, "relevancy": 1.0, "citation": 1.0},
        )
        assert high.componentes["qualidade_justificativa"] == 20.0
        assert low.componentes["qualidade_justificativa"] == 4.0
        assert high.score > low.score

    def test_fallback_without_quality_scores_unchanged(self):
        """Sem métricas, o comportamento legado (10 + 10 booleanos) se mantém."""
        s = compute_approval_score(has_justification=True, cid_procedure_consistent=True)
        assert s.componentes["qualidade_justificativa"] == 20.0
        s2 = compute_approval_score(has_justification=False, cid_procedure_consistent=True)
        assert s2.componentes["qualidade_justificativa"] == 10.0

    def test_low_faithfulness_generates_alert(self):
        s = compute_approval_score(
            has_justification=True,
            quality_scores={"faithfulness": 0.5, "relevancy": 0.9, "citation": 0.9},
        )
        assert any("Fidelidade" in a for a in s.alertas)

    def test_no_justification_zeroes_even_with_quality(self):
        s = compute_approval_score(
            has_justification=False,
            quality_scores={"faithfulness": 1.0},
        )
        assert s.componentes["qualidade_justificativa"] == 0.0


class TestEvidenceAwareMinLength:
    def test_rich_evidence_keeps_full_minimums(self):
        model = build_writer_output_model(evidence_count=5)
        assert model is WriterOutput

    def test_scarce_evidence_shrinks_evidencia_section(self):
        model = build_writer_output_model(evidence_count=1)
        field = model.model_fields["evidencia_cientifica"]
        min_len = next(m.min_length for m in field.metadata if hasattr(m, "min_length"))
        assert min_len == 250

    def test_zero_evidence_shrinks_further(self):
        model = build_writer_output_model(evidence_count=0)
        field = model.model_fields["evidencia_cientifica"]
        min_len = next(m.min_length for m in field.metadata if hasattr(m, "min_length"))
        assert min_len == 120

    def test_other_sections_unchanged(self):
        model = build_writer_output_model(evidence_count=0)
        field = model.model_fields["quadro_clinico"]
        min_len = next(m.min_length for m in field.metadata if hasattr(m, "min_length"))
        assert min_len == 600  # não depende do volume de artigos


# ── PR5: prompt sem conteúdo plantado + fallback de few-shot ──────────────

class TestPromptSemConteudoPlantado:
    """O prompt global ensinava mecanismos concretos como exemplo de estilo.
    O modelo não distingue "instrução do sistema" de "fato autorizado" — e
    escrevia 980nm para um produto cuja ficha diz "diodo ou CO2".
    """

    @pytest.mark.parametrize("plantado", [
        "980nm", "1470nm", "48 horas", "IL-1β", "TNF-α", "hialuronidases",
    ])
    def test_afirmacoes_clinicas_especificas_saíram_do_prompt(self, plantado):
        from app.services.agents.prompts import WRITER_SYSTEM, AUDITOR_SYSTEM
        assert plantado not in WRITER_SYSTEM, f"'{plantado}' voltou ao WRITER_SYSTEM"
        assert plantado not in AUDITOR_SYSTEM, f"'{plantado}' voltou ao AUDITOR_SYSTEM"

    def test_metodo_procedural_substituiu_a_afirmacao(self):
        """A profundidade tem de vir de percorrer as propriedades da ficha."""
        from app.services.agents.prompts import WRITER_SYSTEM
        assert "<product_facts>" in WRITER_SYSTEM
        assert "MÉTODO" in WRITER_SYSTEM

    def test_auditor_usa_categorias_nao_valores(self):
        from app.services.agents.prompts import AUDITOR_SYSTEM
        assert "comprimento de onda" in AUDITOR_SYSTEM  # categoria, sem valor
        assert "plausível" in AUDITOR_SYSTEM.lower()    # critério é a ficha


class TestFewShotFallback:
    """Sem exemplo da especialidade, o Redator ficava sem NENHUM modelo de
    profundidade — e a seção longa virava padding genérico."""

    @pytest.mark.parametrize("especialidade", [
        "Hematologia", "Reumatologia", "especialidade-que-nao-existe",
    ])
    def test_especialidade_nao_mapeada_recebe_exemplo(self, especialidade):
        from app.services.agents.few_shot_examples import get_few_shot_messages
        msgs = get_few_shot_messages(especialidade)
        assert len(msgs) == 2, f"{especialidade} ficou sem few-shot"

    def test_especialidade_vazia_continua_sem_exemplo(self):
        """Sem especialidade não há caso definido — não force um exemplo."""
        from app.services.agents.few_shot_examples import get_few_shot_messages
        assert get_few_shot_messages("") == []

    def test_fallback_nao_planta_mecanismo_de_especialidade(self):
        import json
        from app.services.agents.few_shot_examples import EXAMPLES, _FALLBACK_KEY
        conteudo = json.dumps(EXAMPLES[_FALLBACK_KEY], ensure_ascii=False)
        for plantado in ("IL-1β", "980nm", "condrócito", "hialuron", "scaffold", "PEEK"):
            assert plantado not in conteudo, f"fallback planta '{plantado}'"

    def test_fallback_mantem_a_estrutura_de_6_secoes(self):
        from app.services.agents.few_shot_examples import EXAMPLES, _FALLBACK_KEY
        for secao in ("quadro_clinico", "falha_terapeutica", "justificativa_tecnica",
                      "evidencia_cientifica", "risco_nao_realizacao", "conclusao"):
            assert EXAMPLES[_FALLBACK_KEY]["assistant"][secao]


class TestCitacaoExigeAutorEAno:
    """CLASSIC_AUTHORS dava salvo-conduto a sobrenome famoso, sem conferir ano."""

    def test_lista_hardcoded_removida(self):
        """Checa a AUSÊNCIA DA LISTA, não da palavra: o comentário que explica
        por que ela saiu deve poder citar o nome."""
        import re
        import inspect
        from app.services.agents import auditor
        fonte = inspect.getsource(auditor)
        assert not re.search(r"^\s*CLASSIC_AUTHORS\s*=", fonte, re.MULTILINE)
        assert not hasattr(auditor, "CLASSIC_AUTHORS")

    def test_autor_fornecido_com_ano_correto_valida(self):
        from app.services.agents.auditor import _extract_known_sources, _local_verify_references

        class _P:
            referencias_bibliograficas = []
        fontes = _extract_known_sources(_P(), [], [{"autor": "Teixeira", "ano": "2021"}])
        ok, refs = _local_verify_references("Achado relevante (Teixeira et al., 2021).", fontes)
        assert ok and refs

    def test_autor_famoso_nao_fornecido_nao_valida(self):
        from app.services.agents.auditor import _extract_known_sources, _local_verify_references

        class _P:
            referencias_bibliograficas = []
        fontes = _extract_known_sources(_P(), [], [{"autor": "Teixeira", "ano": "2021"}])
        ok, refs = _local_verify_references("Estudos comprovam (Altman et al., 2015).", fontes)
        assert not ok and refs == []

    def test_ano_divergente_nao_conta_como_validada(self):
        from app.services.agents.auditor import _extract_known_sources, _local_verify_references

        class _P:
            referencias_bibliograficas = []
        fontes = _extract_known_sources(_P(), [], [{"autor": "Teixeira", "ano": "2021"}])
        ok, refs = _local_verify_references("Achado (Teixeira et al., 1999).", fontes)
        assert not ok

    def test_referencias_do_produto_entram_com_ano(self):
        from app.services.agents.auditor import _extract_known_sources

        class _P:
            referencias_bibliograficas = ["Altman RD, et al. Semin Arthritis Rheum. 2015;45(2):140-9."]
        fontes = _extract_known_sources(_P(), [], [])
        assert ("altman", "2015") in fontes
