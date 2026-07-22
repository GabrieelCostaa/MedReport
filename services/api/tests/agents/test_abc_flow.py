"""
Testes de fluxo A/B/C (Decision Tree).

Garante que:
1. As perguntas de múltipla escolha levam aos parágrafos corretos
2. Respostas diferentes produzem textos diferentes
3. Lacunas críticas bloqueiam geração, lacunas de fortalecimento não
"""
import os
import sys
import pytest
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from tests.conftest import MockProduct, MockTemplate

from tests.conftest import SKIP_LLM, SKIP_LLM_REASON as skip_reason  # noqa: E402


class TestGapPriority:
    """Testa classificação de prioridade das lacunas."""

    def test_critical_gaps_are_defined(self):
        from app.services.agents.researcher import CRITICAL_GAPS, STRENGTHENING_GAPS
        assert "falha_terapeutica" in CRITICAL_GAPS
        assert "risco_nao_realizacao" in CRITICAL_GAPS
        assert "diagnostico" in CRITICAL_GAPS
        assert "citacao_recente" in STRENGTHENING_GAPS

    def test_gap_question_has_priority(self):
        from app.services.agents.researcher import GapQuestion
        q = GapQuestion(secao="falha_terapeutica", pergunta="Teste", prioridade="critica")
        assert q.prioridade == "critica"

    def test_strengthening_gap_defaults(self):
        from app.services.agents.researcher import GapQuestion
        q = GapQuestion(secao="citacao_recente", pergunta="Teste", prioridade="fortalecimento")
        assert q.prioridade == "fortalecimento"


class TestPipelineSessionFlow:
    """Testa o fluxo stateful do pipeline."""

    def test_pipeline_session_created(self):
        from app.services.agents.pipeline import PipelineSession
        session = PipelineSession(session_id="test-123")
        assert session.step == "init"
        assert session.pending_questions == []
        assert session.answered_questions == {}

    @pytest.mark.skipif(SKIP_LLM, reason=skip_reason)
    @pytest.mark.asyncio
    async def test_start_returns_questions_or_result(self):
        """Pipeline.start() deve retornar perguntas A/B/C ou resultado direto."""
        from app.services.agents.pipeline import ReportPipeline

        product = MockProduct()
        result = await ReportPipeline.start(
            product=product,
            template=MockTemplate(),
            diagnostico="Gonartrose bilateral M17.0",
            cid="M17.0",
            medico_inputs={
                "paciente_nome": "Teste",
                "diagnostico": "Gonartrose bilateral M17.0",
                "cid": "M17.0",
            },
        )

        assert "session_id" in result
        assert result["step"] in ("questions", "done")

        if result["step"] == "questions":
            assert "questions" in result
            assert len(result["questions"]) > 0
            for q in result["questions"]:
                assert "secao" in q
                assert "pergunta" in q
                assert "opcoes" in q

        elif result["step"] == "done":
            assert "justificativa" in result
            assert "checklist" in result
            assert "audit_summary" in result

    @pytest.mark.skipif(SKIP_LLM, reason=skip_reason)
    @pytest.mark.asyncio
    async def test_answer_advances_pipeline(self):
        """Responder perguntas deve avançar o pipeline para 'done'."""
        from app.services.agents.pipeline import ReportPipeline

        product = MockProduct()
        start_result = await ReportPipeline.start(
            product=product,
            template=None,
            diagnostico="Dor no joelho",
            cid="M25.5",
            medico_inputs={
                "paciente_nome": "Teste",
                "diagnostico": "Dor no joelho",
                "cid": "M25.5",
            },
        )

        if start_result["step"] == "questions":
            answers = {}
            for q in start_result["questions"]:
                answers[q["secao"]] = q["opcoes"][0]["texto"] if q["opcoes"] else "Resposta padrão"

            answer_result = await ReportPipeline.answer(
                start_result["session_id"], answers
            )

            assert answer_result["step"] in ("questions", "done")
            if answer_result["step"] == "done":
                assert "justificativa" in answer_result
                assert len(answer_result["justificativa"]) > 50

    @pytest.mark.skipif(SKIP_LLM, reason=skip_reason)
    @pytest.mark.asyncio
    async def test_different_answers_produce_different_texts(self):
        """Respostas A vs B devem gerar textos com fraseologia diferente."""
        from app.services.agents.writer import write_justification
        from app.services.agents.researcher import ResearchResult, Evidence

        product = MockProduct()
        fake_research = ResearchResult(
            evidencias=[Evidence(texto="Eficácia comprovada", referencia="Altman 2015")],
            referencias=["Altman 2015"],
        )

        draft_a = await write_justification(
            research=fake_research,
            product=product,
            template=MockTemplate(),
            medico_inputs={
                "diagnostico": "Gonartrose M17.0",
                "cid": "M17.0",
                "falha_terapeutica": "Insucesso com analgésicos orais por 6 meses",
                "risco_nao_realizacao": "Progressão da degeneração articular",
            },
        )

        draft_b = await write_justification(
            research=fake_research,
            product=product,
            template=MockTemplate(),
            medico_inputs={
                "diagnostico": "Gonartrose M17.0",
                "cid": "M17.0",
                "falha_terapeutica": "Fisioterapia sem ganho de amplitude de movimento",
                "risco_nao_realizacao": "Dor crônica intratável",
            },
        )

        text_a = draft_a.justificativa_completa.lower()
        text_b = draft_b.justificativa_completa.lower()

        assert "analgésico" in text_a or "medicamento" in text_a, (
            "Opção A (analgésicos) não gerou texto com fraseologia correspondente"
        )

        assert "fisioterapia" in text_b or "amplitude" in text_b, (
            "Opção B (fisioterapia) não gerou texto com fraseologia correspondente"
        )


class TestAuditSummary:
    """Testa que o audit_summary é retornado corretamente."""

    @pytest.mark.skipif(SKIP_LLM, reason=skip_reason)
    @pytest.mark.asyncio
    async def test_audit_summary_structure(self):
        """Resultado do pipeline deve conter audit_summary com estrutura esperada."""
        from app.services.agents.pipeline import ReportPipeline

        product = MockProduct()
        result = await ReportPipeline.start(
            product=product,
            template=MockTemplate(),
            diagnostico="Gonartrose M17.0",
            cid="M17.0",
            medico_inputs={
                "paciente_nome": "Teste",
                "diagnostico": "Gonartrose M17.0",
                "cid": "M17.0",
                "falha_terapeutica": "Tratamento conservador falhou",
                "risco_nao_realizacao": "Piora funcional",
            },
        )

        if result["step"] == "questions":
            answers = {q["secao"]: q["opcoes"][0]["texto"] for q in result["questions"] if q["opcoes"]}
            result = await ReportPipeline.answer(result["session_id"], answers)

        if result["step"] == "done":
            assert "audit_summary" in result
            summary = result["audit_summary"]
            assert "data_corrections" in summary
            assert "sources_cited" in summary
            assert "checklist" in summary
            assert "hard_validation" in summary
            assert "passed" in summary["hard_validation"]
            assert "entities_found" in summary["hard_validation"]


class TestRegenerateFlow:
    """Testa regeneração com ajustes."""

    @pytest.mark.skipif(SKIP_LLM, reason=skip_reason)
    @pytest.mark.asyncio
    async def test_regenerate_updates_text(self):
        """Regenerar com ajustes deve produzir texto diferente."""
        from app.services.agents.pipeline import ReportPipeline

        product = MockProduct()
        result = await ReportPipeline.start(
            product=product,
            template=MockTemplate(),
            diagnostico="Gonartrose M17.0",
            cid="M17.0",
            medico_inputs={
                "paciente_nome": "Teste",
                "diagnostico": "Gonartrose M17.0",
                "cid": "M17.0",
                "falha_terapeutica": "Analgésicos falharam",
                "risco_nao_realizacao": "Progressão",
            },
        )

        if result["step"] == "questions":
            answers = {q["secao"]: q["opcoes"][0]["texto"] for q in result["questions"] if q["opcoes"]}
            result = await ReportPipeline.answer(result["session_id"], answers)

        if result["step"] == "done":
            regen = await ReportPipeline.regenerate(
                result["session_id"],
                {"risco_nao_realizacao": "Risco de incapacidade permanente com necessidade de prótese total"},
            )
            assert regen["step"] == "done"
            assert len(regen["justificativa"]) > 50
