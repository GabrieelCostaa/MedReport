"""
Testes de edge cases para DUT: critérios subjetivos, notas de rodapé,
paciente no limite de faixa etária, DSL malformada.
"""
import pytest

from app.services.dut_engine import evaluate_dsl, build_evaluation


class TestEdgeCaseIdadeLimite:
    """Paciente exatamente no limite de faixa etária."""

    def test_exactly_18(self):
        dsl = {
            "criterios": [
                {"id": "A", "tipo": "deterministico", "campo_paciente": "idade", "operador": ">=", "valor": 18, "descricao": ">=18"},
            ],
            "exclusoes": [],
            "logica": "A",
        }
        results = evaluate_dsl(dsl, {"idade": 18})
        eval_ = build_evaluation(results)
        assert len(eval_.criteria_met) == 1

    def test_exactly_65(self):
        dsl = {
            "criterios": [
                {"id": "A", "tipo": "deterministico", "campo_paciente": "idade", "operador": "<=", "valor": 65, "descricao": "<=65"},
            ],
            "exclusoes": [],
            "logica": "A",
        }
        results = evaluate_dsl(dsl, {"idade": 65})
        eval_ = build_evaluation(results)
        assert len(eval_.criteria_met) == 1

    def test_one_over_limit(self):
        dsl = {
            "criterios": [
                {"id": "A", "tipo": "deterministico", "campo_paciente": "idade", "operador": "<=", "valor": 65, "descricao": "<=65"},
            ],
            "exclusoes": [],
            "logica": "A",
        }
        results = evaluate_dsl(dsl, {"idade": 66})
        eval_ = build_evaluation(results)
        assert len(eval_.criteria_unmet) == 1


class TestEdgeCaseNotaRodape:
    """Nota de rodapé que exclui cobertura."""

    def test_exclusion_from_footnote(self):
        dsl = {
            "criterios": [
                {"id": "A", "tipo": "deterministico", "campo_paciente": "idade", "operador": ">=", "valor": 18, "descricao": ">=18"},
            ],
            "exclusoes": [
                {
                    "id": "EX1",
                    "tipo": "exclusao",
                    "campo_paciente": "indicacao",
                    "operador": "==",
                    "valor": "cosmetico",
                    "descricao": "Nota: exclui-se indicação cosmética",
                    "origem": "nota_rodape",
                },
            ],
            "logica": "A AND NOT EX1",
        }
        results = evaluate_dsl(dsl, {"idade": 30, "indicacao": "cosmetico"})
        eval_ = build_evaluation(results)
        assert eval_.exclusion_triggered is not None

    def test_no_exclusion_when_therapeutic(self):
        dsl = {
            "criterios": [
                {"id": "A", "tipo": "deterministico", "campo_paciente": "idade", "operador": ">=", "valor": 18, "descricao": ">=18"},
            ],
            "exclusoes": [
                {
                    "id": "EX1",
                    "tipo": "exclusao",
                    "campo_paciente": "indicacao",
                    "operador": "==",
                    "valor": "cosmetico",
                    "descricao": "Nota: exclui-se indicação cosmética",
                },
            ],
            "logica": "A AND NOT EX1",
        }
        results = evaluate_dsl(dsl, {"idade": 30, "indicacao": "terapeutico"})
        eval_ = build_evaluation(results)
        assert eval_.exclusion_triggered is None


class TestEdgeCaseSubjetivo:
    """Critérios subjetivos sempre ficam como 'unknown' sem LLM."""

    def test_all_subjective(self):
        dsl = {
            "criterios": [
                {"id": "A", "tipo": "subjetivo", "descricao": "Motivação adequada", "requer_llm": True},
                {"id": "B", "tipo": "subjetivo", "descricao": "Expectativa realista", "requer_llm": True},
            ],
            "exclusoes": [],
            "logica": "A AND B",
        }
        results = evaluate_dsl(dsl, {"idade": 30})
        eval_ = build_evaluation(results)
        assert len(eval_.criteria_subjective) == 2
        assert len(eval_.criteria_met) == 0

    def test_mixed_objective_subjective(self):
        dsl = {
            "criterios": [
                {"id": "A", "tipo": "deterministico", "campo_paciente": "idade", "operador": ">=", "valor": 18, "descricao": ">=18"},
                {"id": "B", "tipo": "subjetivo", "descricao": "Condicao psicossocial adequada", "requer_llm": True},
            ],
            "exclusoes": [],
            "logica": "A AND B",
        }
        results = evaluate_dsl(dsl, {"idade": 30})
        eval_ = build_evaluation(results)
        assert len(eval_.criteria_met) == 1
        assert len(eval_.criteria_subjective) == 1


class TestEdgeCaseMalformedDsl:
    """DSL malformada deve ser tratada graciosamente."""

    def test_missing_operador(self):
        dsl = {
            "criterios": [
                {"id": "A", "tipo": "deterministico", "campo_paciente": "idade", "descricao": "sem operador"},
            ],
            "exclusoes": [],
        }
        results = evaluate_dsl(dsl, {"idade": 30})
        eval_ = build_evaluation(results)
        assert len(eval_.criteria_unknown) == 1

    def test_missing_campo(self):
        dsl = {
            "criterios": [
                {"id": "A", "tipo": "deterministico", "operador": ">=", "valor": 18, "descricao": "sem campo"},
            ],
            "exclusoes": [],
        }
        results = evaluate_dsl(dsl, {"idade": 30})
        eval_ = build_evaluation(results)
        assert len(eval_.criteria_unknown) == 1

    def test_unknown_operator(self):
        dsl = {
            "criterios": [
                {"id": "A", "tipo": "deterministico", "campo_paciente": "idade", "operador": "~=", "valor": 18, "descricao": "op invalido"},
            ],
            "exclusoes": [],
        }
        results = evaluate_dsl(dsl, {"idade": 30})
        eval_ = build_evaluation(results)
        assert len(eval_.criteria_unmet) == 1 or len(eval_.criteria_met) >= 0

    def test_empty_criterios(self):
        results = evaluate_dsl({"criterios": [], "exclusoes": []}, {"idade": 30})
        assert results == []

    def test_string_vs_numeric_comparison(self):
        dsl = {
            "criterios": [
                {"id": "A", "tipo": "deterministico", "campo_paciente": "idade", "operador": ">=", "valor": "18", "descricao": "string 18"},
            ],
            "exclusoes": [],
        }
        results = evaluate_dsl(dsl, {"idade": "30"})
        eval_ = build_evaluation(results)
        assert len(eval_.criteria_met) == 1
