"""Verificador de fidelidade: decompose-then-verify em modo flag (nunca altera texto)."""
import pytest

from app.services.agents.faithfulness import (
    FaithfulnessResult,
    ClaimVerdict,
    VERIFIABLE_TYPES,
    NAO_VERIFICAVEIS,
    ORIGENS_ESPERADAS,
    _build_evidence_bundle,
    verify_faithfulness,
)


class TestEvidenceBundle:
    def test_bundle_contains_product_facts(self, opus_product):
        bundle = _build_evidence_bundle(opus_product, [], [])
        assert opus_product.nome in bundle
        assert opus_product.registro_anvisa in bundle
        assert "FICHA OFICIAL DO PRODUTO" in bundle

    def test_bundle_contains_evidences(self, opus_product):
        pubmed = [{
            "autor": "Teixeira", "ano": "2021", "pmid": "12345",
            "snippet": "SVF evitou amputações em 71% dos casos",
            "referencia_completa": "Teixeira et al. J Orthop. 2021.",
        }]
        bundle = _build_evidence_bundle(opus_product, [], pubmed)
        assert "Teixeira" in bundle
        assert "71%" in bundle

    def test_bundle_includes_medico_inputs_but_not_internals(self, opus_product):
        inputs = {"falha_terapeutica": "AINEs por 12 semanas", "_trace": object(), "cid": "M17.1"}
        bundle = _build_evidence_bundle(opus_product, [], [], medico_inputs=inputs)
        assert "AINEs por 12 semanas" in bundle
        assert "_trace" not in bundle


class TestScoreSemantics:
    def test_classificacao_por_origem_esperada(self):
        """Cada afirmação é checada contra a fonte que ela PRECISARIA ter."""
        assert VERIFIABLE_TYPES == {"paciente", "produto", "ciencia", "regra"}
        assert NAO_VERIFICAVEIS == {"medicina_geral", "administrativo"}
        assert set(ORIGENS_ESPERADAS) == VERIFIABLE_TYPES

    def test_afirmacao_sobre_o_paciente_e_verificavel(self):
        """Era o buraco: 'descrição do quadro do paciente' caía em narrativo e
        ganhava passe livre, mesmo inventando dado que o médico não informou."""
        assert "paciente" in VERIFIABLE_TYPES

    def test_score_is_grounded_over_verifiable(self):
        verdicts = [
            ClaimVerdict("71% dos casos (Autor, 2021)", "ciencia", grounded=True),
            ClaimVerdict("90% de sucesso", "ciencia", grounded=False),
            ClaimVerdict("a articulação sinovial é revestida por cartilagem", "medicina_geral", grounded=True),
        ]
        verifiable = [v for v in verdicts if v.tipo in VERIFIABLE_TYPES]
        grounded = [v for v in verifiable if v.grounded]
        assert len(verifiable) == 2
        assert len(grounded) == 1
        # narrativo fica de fora do denominador
        assert len(grounded) / len(verifiable) == 0.5

    def test_empty_result_flags(self):
        r = FaithfulnessResult()
        assert r.flags() == []
        assert r.score is None


class TestFailSoft:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_skipped(self, opus_product, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
        r = await verify_faithfulness("Texto do laudo.", opus_product)
        assert r.error == "skipped"
        assert r.score is None

    @pytest.mark.asyncio
    async def test_empty_text_returns_skipped(self, opus_product):
        r = await verify_faithfulness("", opus_product)
        assert r.error == "skipped"

    @pytest.mark.asyncio
    async def test_llm_error_never_raises(self, opus_product, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-fake-key-for-test")

        import openai

        class _Boom:
            def __init__(self, **kw):
                raise RuntimeError("simulated API failure")

        monkeypatch.setattr(openai, "AsyncOpenAI", _Boom)
        r = await verify_faithfulness("Texto do laudo.", opus_product)
        assert r.score is None
        assert r.error is not None
