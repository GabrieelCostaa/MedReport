"""
Testes unitários para DutEngine — avaliação DSL determinística.
Todos determinísticos e offline — sem banco, sem LLM.
"""
import pytest

from app.services.dut_engine import evaluate_dsl, build_evaluation, CriterionResult


VISCOSUP_DSL = {
    "criterios": [
        {
            "id": "A",
            "tipo": "deterministico",
            "campo_paciente": "idade",
            "operador": ">=",
            "valor": 18,
            "descricao": "Paciente com idade >= 18 anos",
        },
        {
            "id": "B",
            "tipo": "deterministico",
            "campo_paciente": "grau_kellgren_lawrence",
            "operador": "in",
            "valor": [2, 3],
            "descricao": "Gonartrose grau II ou III",
        },
        {
            "id": "C",
            "tipo": "deterministico",
            "campo_paciente": "tempo_tratamento_conservador_meses",
            "operador": ">=",
            "valor": 6,
            "descricao": "Falha conservadora >= 6 meses",
        },
        {
            "id": "D",
            "tipo": "subjetivo",
            "descricao": "Limitação funcional significativa",
            "requer_llm": True,
        },
    ],
    "exclusoes": [
        {
            "id": "EX1",
            "tipo": "exclusao",
            "campo_paciente": "finalidade",
            "operador": "==",
            "valor": "estetico",
            "descricao": "Exclui-se uso estético",
            "origem": "nota_rodape",
        },
    ],
    "logica": "A AND B AND C AND NOT EX1",
}

BARIATRICA_DSL = {
    "criterios": [
        {
            "id": "A",
            "tipo": "deterministico",
            "campo_paciente": "imc",
            "operador": ">=",
            "valor": 40,
            "descricao": "IMC >= 40 kg/m2",
        },
        {
            "id": "B",
            "tipo": "deterministico",
            "campo_paciente": "idade",
            "operador": "between",
            "valor": [18, 65],
            "descricao": "Idade entre 18 e 65 anos",
        },
    ],
    "exclusoes": [],
    "logica": "A AND B",
}


class TestEvaluateDsl:
    def test_all_met(self):
        patient = {
            "idade": 55,
            "grau_kellgren_lawrence": 3,
            "tempo_tratamento_conservador_meses": 12,
            "finalidade": "terapeutico",
        }
        results = evaluate_dsl(VISCOSUP_DSL, patient)
        eval_ = build_evaluation(results)
        assert len(eval_.criteria_met) >= 3
        assert len(eval_.criteria_unmet) == 0
        assert eval_.exclusion_triggered is None

    def test_age_unmet(self):
        patient = {
            "idade": 16,
            "grau_kellgren_lawrence": 2,
            "tempo_tratamento_conservador_meses": 8,
            "finalidade": "terapeutico",
        }
        results = evaluate_dsl(VISCOSUP_DSL, patient)
        eval_ = build_evaluation(results)
        unmet_ids = [c.id for c in eval_.criteria_unmet]
        assert "A" in unmet_ids

    def test_exclusion_triggered(self):
        patient = {
            "idade": 30,
            "grau_kellgren_lawrence": 2,
            "tempo_tratamento_conservador_meses": 8,
            "finalidade": "estetico",
        }
        results = evaluate_dsl(VISCOSUP_DSL, patient)
        eval_ = build_evaluation(results)
        assert eval_.exclusion_triggered is not None

    def test_subjective_marked_unknown(self):
        patient = {
            "idade": 30,
            "grau_kellgren_lawrence": 2,
            "tempo_tratamento_conservador_meses": 8,
        }
        results = evaluate_dsl(VISCOSUP_DSL, patient)
        eval_ = build_evaluation(results)
        assert len(eval_.criteria_subjective) == 1
        assert eval_.criteria_subjective[0].tipo == "subjetivo"

    def test_missing_data_unknown(self):
        patient = {"idade": 30}
        results = evaluate_dsl(VISCOSUP_DSL, patient)
        eval_ = build_evaluation(results)
        assert len(eval_.criteria_unknown) >= 1

    def test_between_operator(self):
        patient = {"imc": 45, "idade": 35}
        results = evaluate_dsl(BARIATRICA_DSL, patient)
        eval_ = build_evaluation(results)
        assert len(eval_.criteria_met) == 2

    def test_between_out_of_range(self):
        patient = {"imc": 45, "idade": 70}
        results = evaluate_dsl(BARIATRICA_DSL, patient)
        eval_ = build_evaluation(results)
        unmet_ids = [c.id for c in eval_.criteria_unmet]
        assert "B" in unmet_ids

    def test_met_percentage(self):
        patient = {
            "idade": 55,
            "grau_kellgren_lawrence": 3,
            "tempo_tratamento_conservador_meses": 12,
            "finalidade": "terapeutico",
        }
        results = evaluate_dsl(VISCOSUP_DSL, patient)
        eval_ = build_evaluation(results)
        assert eval_.met_percentage > 50

    def test_all_objective_met(self):
        patient = {
            "idade": 55,
            "grau_kellgren_lawrence": 3,
            "tempo_tratamento_conservador_meses": 12,
            "finalidade": "terapeutico",
        }
        results = evaluate_dsl(VISCOSUP_DSL, patient)
        eval_ = build_evaluation(results)
        assert eval_.all_objective_met is True

    def test_not_met_when_exclusion(self):
        patient = {
            "idade": 55,
            "grau_kellgren_lawrence": 3,
            "tempo_tratamento_conservador_meses": 12,
            "finalidade": "estetico",
        }
        results = evaluate_dsl(VISCOSUP_DSL, patient)
        eval_ = build_evaluation(results)
        assert eval_.all_objective_met is False

    def test_empty_dsl(self):
        results = evaluate_dsl({}, {})
        assert results == []


class TestMonotonicity:
    """Score não deve cair quando mais dados completos são fornecidos."""

    def test_more_data_same_or_higher_met(self):
        minimal = {"idade": 55}
        full = {
            "idade": 55,
            "grau_kellgren_lawrence": 3,
            "tempo_tratamento_conservador_meses": 12,
            "finalidade": "terapeutico",
        }
        r_min = evaluate_dsl(VISCOSUP_DSL, minimal)
        r_full = evaluate_dsl(VISCOSUP_DSL, full)

        e_min = build_evaluation(r_min)
        e_full = build_evaluation(r_full)

        assert len(e_full.criteria_met) >= len(e_min.criteria_met)


class TestCriterionResult:
    def test_dataclass_fields(self):
        cr = CriterionResult(id="A", tipo="deterministico", resultado="met")
        assert cr.id == "A"
        assert cr.resultado == "met"
        assert cr.valor_esperado is None
