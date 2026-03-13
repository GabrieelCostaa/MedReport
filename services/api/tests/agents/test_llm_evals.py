"""
LLM Evals: Golden Dataset e testes de alucinação.

Estes testes verificam que o pipeline multi-agente:
1. Gera textos com qualidade similar aos relatórios aprovados (Golden Dataset)
2. Detecta e bloqueia dados técnicos inventados (Teste de Alucinação)
3. Valida que referências bibliográficas são preservadas

Requerem OPENAI_API_KEY configurada. Pular se não disponível.
"""
import os
import sys
import pytest
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from tests.conftest import MockProduct, MockProductAdhesion, MockTemplate

SKIP_LLM = not os.environ.get("OPENAI_API_KEY")
skip_reason = "OPENAI_API_KEY não configurada"

# Golden Dataset: relatórios que já foram aprovados
GOLDEN_REPORTS = {
    "opus_viscossuplementacao": {
        "diagnostico": "Gonartrose bilateral CID M17.0, grau III Kellgren-Lawrence",
        "cid": "M17.0",
        "expected_keywords": [
            "viscossuplementação",
            "6.000",
            "peso molecular",
        ],
        "expected_references": ["Altman", "Bellamy"],
        "forbidden_claims": [
            "cura definitiva",
            "regenera cartilagem",
        ],
    },
    "adhesion_anti_aderencia": {
        "diagnostico": "Bridas peritoneais recidivantes CID K66.0",
        "cid": "K66.0",
        "expected_keywords": [
            "aderência",
            "barreira",
            "biorreabsorvível",
        ],
        "expected_references": ["Diamond"],
        "forbidden_claims": [
            "elimina 100%",
            "garantia de sucesso",
        ],
    },
}


@pytest.fixture
def opus_template():
    return MockTemplate(
        nome="Template Viscossuplementação",
        especialidade="Ortopedia",
        tom_de_voz="Científico, formal e assertivo",
        bases_legais=["RN 395", "RN 424"],
        referencias_padrao=["Altman RD, et al. 2015"],
        exemplos_aprovados=[
            "Paciente com diagnóstico de gonartrose bilateral (CID M17.0), "
            "grau III de Kellgren-Lawrence. Após insucesso com tratamento conservador, "
            "indica-se viscossuplementação com ácido hialurônico de alto peso molecular "
            "(6.000 kDa). Conforme RN 395 da ANS."
        ],
    )


class TestGoldenDatasetSimilarity:
    """Testa similaridade entre relatórios gerados e aprovados."""

    @pytest.mark.skipif(SKIP_LLM, reason=skip_reason)
    @pytest.mark.asyncio
    async def test_opus_contains_expected_keywords(self, opus_product, opus_template):
        """Relatório para Opus deve conter termos técnicos esperados."""
        from app.services.agents.researcher import research
        from app.services.agents.writer import write_justification

        golden = GOLDEN_REPORTS["opus_viscossuplementacao"]

        research_result = await research(
            opus_product, golden["diagnostico"], golden["cid"], opus_template
        )

        medico_inputs = {
            "diagnostico": golden["diagnostico"],
            "cid": golden["cid"],
            "surgery_description": "Viscossuplementação articular",
            "falha_terapeutica": "Analgésicos e fisioterapia por 6 meses sem melhora",
            "risco_nao_realizacao": "Progressão degenerativa com necessidade de artroplastia",
        }

        draft = await write_justification(
            research=research_result,
            product=opus_product,
            template=opus_template,
            medico_inputs=medico_inputs,
        )

        text = draft.justificativa_completa.lower()
        for keyword in golden["expected_keywords"]:
            assert keyword.lower() in text, f"Keyword '{keyword}' não encontrada no relatório gerado"

    @pytest.mark.skipif(SKIP_LLM, reason=skip_reason)
    @pytest.mark.asyncio
    async def test_opus_preserves_references(self, opus_product, opus_template):
        """Relatório deve preservar referências do Golden Set."""
        from app.services.agents.researcher import research
        from app.services.agents.writer import write_justification

        golden = GOLDEN_REPORTS["opus_viscossuplementacao"]

        research_result = await research(
            opus_product, golden["diagnostico"], golden["cid"], opus_template
        )

        draft = await write_justification(
            research=research_result,
            product=opus_product,
            template=opus_template,
            medico_inputs={
                "diagnostico": golden["diagnostico"],
                "cid": golden["cid"],
                "falha_terapeutica": "Fisioterapia sem resultado",
                "risco_nao_realizacao": "Progressão da doença",
            },
        )

        all_refs = " ".join(draft.referencias).lower()
        full_text = (draft.justificativa_completa + " " + all_refs).lower()

        for ref_author in golden["expected_references"]:
            assert ref_author.lower() in full_text, (
                f"Referência '{ref_author}' não encontrada no relatório gerado"
            )

    @pytest.mark.skipif(SKIP_LLM, reason=skip_reason)
    @pytest.mark.asyncio
    async def test_no_forbidden_claims(self, opus_product, opus_template):
        """Relatório NÃO deve conter alegações proibidas."""
        from app.services.agents.researcher import research
        from app.services.agents.writer import write_justification

        golden = GOLDEN_REPORTS["opus_viscossuplementacao"]

        research_result = await research(
            opus_product, golden["diagnostico"], golden["cid"], opus_template
        )

        draft = await write_justification(
            research=research_result,
            product=opus_product,
            template=opus_template,
            medico_inputs={
                "diagnostico": golden["diagnostico"],
                "cid": golden["cid"],
                "falha_terapeutica": "Tratamento conservador falhou",
                "risco_nao_realizacao": "Piora funcional",
            },
        )

        text = draft.justificativa_completa.lower()
        for claim in golden["forbidden_claims"]:
            assert claim.lower() not in text, (
                f"Alegação proibida '{claim}' encontrada no relatório!"
            )


class TestHallucinationDetection:
    """
    Teste de alucinação técnica: o teste MAIS IMPORTANTE.
    Verifica que o Auditor + Validador detectam dados inventados.
    """

    @pytest.mark.skipif(SKIP_LLM, reason=skip_reason)
    @pytest.mark.asyncio
    async def test_auditor_corrects_wrong_molecular_weight(self, opus_product):
        """
        ATAQUE: Forçar peso molecular errado.
        DEFESA: Auditor deve corrigir ou validador deve bloquear.
        """
        from app.services.agents.writer import DraftReport
        from app.services.agents.auditor import audit
        from app.services.agents.validator import validate_technical_data

        fake_draft = DraftReport(
            justificativa_completa=(
                "Indica-se viscossuplementação com ácido hialurônico de "
                "peso molecular de 500 kDa e viscosidade de 200 mPa.s. "
                "Este material é superior em todos os aspectos."
            ),
            diagnostico_resumo="Gonartrose M17.0",
            falha_terapeutica="Tratamento medicamentoso falhou",
            risco_nao_realizacao="Progressão da doença",
            base_legal="RN 395",
            referencias=["Altman 2015"],
        )

        audit_result = await audit(fake_draft, opus_product)

        llm_caught = any(
            "peso" in entry.campo.lower() or "molecular" in entry.campo.lower()
            for entry in audit_result.audit_log
            if entry.tipo in ("correcao", "remocao")
        )

        validation = validate_technical_data(
            audit_result.texto_corrigido, opus_product
        )

        assert llm_caught or not validation.aprovado, (
            "FALHA CRÍTICA: Peso molecular falso (500 kDa vs 6.000 kDa) "
            "passou pelo Auditor E pelo Validador Hard-Coded!"
        )

    @pytest.mark.skipif(SKIP_LLM, reason=skip_reason)
    @pytest.mark.asyncio
    async def test_auditor_preserves_correct_data(self, opus_product):
        """Dados CORRETOS não devem ser alterados pelo Auditor."""
        from app.services.agents.writer import DraftReport
        from app.services.agents.auditor import audit

        correct_draft = DraftReport(
            justificativa_completa=(
                "Indica-se viscossuplementação com ácido hialurônico de alto peso molecular "
                "(6.000 kDa) e concentração de 10 mg/mL, com viscosidade de 100.000 mPa.s. "
                "Conforme a RN 395 da ANS, a operadora deverá apresentar justificativa técnica."
            ),
            diagnostico_resumo="Gonartrose bilateral M17.0",
            falha_terapeutica="Fisioterapia e analgésicos sem melhora",
            risco_nao_realizacao="Evolução para artroplastia",
            base_legal="RN 395 da ANS",
            referencias=["Altman RD, et al. 2015", "Bellamy N, et al. 2006"],
        )

        audit_result = await audit(correct_draft, opus_product)

        assert "6.000" in audit_result.texto_corrigido or "6000" in audit_result.texto_corrigido

    def test_validator_catches_hallucinated_viscosity_without_llm(self, opus_product):
        """Validador hard-coded detecta viscosidade inventada sem precisar de LLM."""
        from app.services.agents.validator import validate_technical_data

        text = "Produto com viscosidade de 5 mPa.s ideal para uso articular."
        result = validate_technical_data(text, opus_product)
        assert not result.aprovado
        assert any(i.campo == "viscosidade" for i in result.issues)

    def test_validator_catches_hallucinated_concentration_without_llm(self, opus_product):
        """Validador hard-coded detecta concentração inventada sem precisar de LLM."""
        from app.services.agents.validator import validate_technical_data

        text = "Solução com concentração de 50 mg/mL de hialuronato."
        result = validate_technical_data(text, opus_product)
        assert not result.aprovado
        assert any(i.campo == "concentracao" for i in result.issues)


class TestSemanticChecks:
    """Verificações semânticas do conteúdo gerado."""

    @pytest.mark.skipif(SKIP_LLM, reason=skip_reason)
    @pytest.mark.asyncio
    async def test_generated_text_is_formal(self, opus_product, opus_template):
        """Texto gerado deve ter tom formal (sem gírias, sem 1a pessoa)."""
        from app.services.agents.researcher import research
        from app.services.agents.writer import write_justification

        research_result = await research(
            opus_product, "Gonartrose M17.0", "M17.0", opus_template
        )

        draft = await write_justification(
            research=research_result,
            product=opus_product,
            template=opus_template,
            medico_inputs={
                "diagnostico": "Gonartrose M17.0",
                "cid": "M17.0",
                "falha_terapeutica": "Analgésicos sem melhora",
                "risco_nao_realizacao": "Progressão",
            },
        )

        text = draft.justificativa_completa
        informal_markers = ["eu acho", "na minha opinião", "tipo assim", "é legal", "super bom"]
        for marker in informal_markers:
            assert marker not in text.lower(), f"Tom informal detectado: '{marker}'"

    @pytest.mark.skipif(SKIP_LLM, reason=skip_reason)
    @pytest.mark.asyncio
    async def test_contains_ans_reference(self, opus_product, opus_template):
        """Todo relatório DEVE mencionar RN 395 da ANS."""
        from app.services.agents.researcher import research
        from app.services.agents.writer import write_justification

        research_result = await research(
            opus_product, "Gonartrose M17.0", "M17.0", opus_template
        )

        draft = await write_justification(
            research=research_result,
            product=opus_product,
            template=opus_template,
            medico_inputs={
                "diagnostico": "Gonartrose M17.0",
                "cid": "M17.0",
                "falha_terapeutica": "Tratamento conservador falhou",
                "risco_nao_realizacao": "Piora clínica",
            },
        )

        # RNs should be in base_legal (separate field) or body
        combined = (
            (draft.base_legal or "") + " " + (draft.justificativa_completa or "")
        ).lower()
        has_rn = any(term in combined for term in [
            "rn 395", "rn 424", "rn 465",
            "resolução normativa", "ans",
        ])
        assert has_rn, (
            "Relatório não contém nenhuma referência regulatória ANS "
            "(nem no corpo nem na base_legal)!"
        )
