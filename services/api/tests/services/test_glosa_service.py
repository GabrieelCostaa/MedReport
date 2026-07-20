"""Testes das funções puras do glosa_service (matching, resumo, alerta)."""
from datetime import datetime, timezone

from app.services.glosa_service import (
    OperadoraGlosaSummary,
    build_glosa_alert,
    find_best_operadora_match,
    normalize_operadora_name,
    summarize_indicators,
)

CANDIDATES = [
    ("000701", "Unimed Seguros Saúde S/A", "unimed seguros saude s/a"),
    ("335690", "Unimed Campinas - Cooperativa De Trabalho Médico",
     "unimed campinas - cooperativa de trabalho medico"),
    ("312345", "Unimed Belo Horizonte Cooperativa De Trabalho Médico",
     "unimed belo horizonte cooperativa de trabalho medico"),
    ("005711", "Bradesco Saúde S.A.", "bradesco saude s.a."),
    ("000477", "Sul América Seguradora De Saúde S.A.", "sul america seguradora de saude s.a."),
    ("999001", "Ame Planos De Saúde Ltda", "ame planos de saude ltda"),
]


class TestNormalization:
    def test_removes_corporate_noise_and_accents(self):
        assert normalize_operadora_name("Unimed Campinas - Cooperativa De Trabalho Médico") == "unimed campinas"
        assert normalize_operadora_name("Bradesco Saúde S.A.") == "bradesco"


class TestMatch:
    def test_specific_unimed_matches_right_registro(self):
        m = find_best_operadora_match("Unimed Belo Horizonte", CANDIDATES)
        assert m is not None
        assert m["registro_ans"] == "312345"
        assert m["ambiguous"] is False

    def test_bare_unimed_is_ambiguous_with_candidates(self):
        m = find_best_operadora_match("Unimed", CANDIDATES)
        assert m is not None
        assert m["ambiguous"] is True
        assert 2 <= len(m["candidatos"]) <= 3
        assert all("unimed" in c["razao_social"].lower() for c in m["candidatos"])

    def test_alias_bradesco(self):
        m = find_best_operadora_match("bradesco", CANDIDATES)
        assert m is not None
        assert m["registro_ans"] == "005711"

    def test_spurious_tie_filtered_by_shared_token(self):
        """'Ame Planos' não pode entrar como empate de 'Sul América'."""
        m = find_best_operadora_match("SulAmérica", CANDIDATES)
        assert m is not None
        assert m["registro_ans"] == "000477"
        nomes = [c["razao_social"] for c in m["candidatos"]]
        assert all("Ame Planos" not in n for n in nomes)

    def test_garbage_below_threshold(self):
        assert find_best_operadora_match("convenio inexistente xyz", CANDIDATES) is None

    def test_empty_inputs(self):
        assert find_best_operadora_match("", CANDIDATES) is None
        assert find_best_operadora_match("Unimed", []) is None


def _row(periodo, pc_ini=None, tempo=None, dt_carga="2025-10-15"):
    return {
        "periodo": periodo, "pc_glosa_inicial": pc_ini, "pc_glosa_final": None,
        "tempo_medio_pagamento_dias": tempo, "numero_guias_sem_retorno": None,
        "valor_guias_sem_retorno": None, "dt_carga": dt_carga,
    }


class TestSummarize:
    NOW = datetime(2025, 9, 1, tzinfo=timezone.utc)  # 2º semestre/2025

    def test_uses_last_4_semesters_only(self):
        rows = [
            _row("2023-01", pc_ini=50.0),   # fora da janela (5º mais antigo)
            _row("2023-02", pc_ini=10.0),
            _row("2024-01", pc_ini=20.0),
            _row("2024-02", pc_ini=30.0),
            _row("2025-01", pc_ini=40.0),
        ]
        s = summarize_indicators(rows, now=self.NOW)
        assert s["n_semestres"] == 4
        assert s["medias"]["pc_glosa_inicial"] == 25.0  # média de 10/20/30/40
        assert s["latest_period"] == "2025-01"
        assert s["period_range"] == "2º sem/2023 a 1º sem/2025"
        assert s["is_stale"] is False

    def test_nulls_ignored_in_mean(self):
        rows = [_row("2025-01", pc_ini=10.0), _row("2024-02", pc_ini=None, tempo=30.0)]
        s = summarize_indicators(rows, now=self.NOW)
        assert s["medias"]["pc_glosa_inicial"] == 10.0
        assert s["medias"]["tempo_medio_pagamento_dias"] == 30.0

    def test_stale_when_latest_older_than_4_semesters(self):
        rows = [_row("2022-01", pc_ini=15.0)]
        s = summarize_indicators(rows, now=self.NOW)
        assert s["is_stale"] is True

    def test_empty_rows(self):
        s = summarize_indicators([], now=self.NOW)
        assert s["n_semestres"] == 0 and s["is_stale"] is True


class TestAlert:
    def _summary(self, **kw):
        base = dict(
            registro_ans="335690", razao_social="Unimed Campinas", match_score=100.0,
            n_semestres=4, period_range="2º sem/2023 a 1º sem/2025",
            medias_recentes={"pc_glosa_inicial": 0.2, "tempo_medio_pagamento_dias": 33.0},
        )
        base.update(kw)
        return OperadoraGlosaSummary(**base)

    def test_alert_cites_operadora_and_disclaims(self):
        alert = build_glosa_alert(self._summary())
        assert "Unimed Campinas" in alert and "335690" in alert
        assert "semestres" in alert
        assert "não altera o score" in alert

    def test_stale_switches_to_historical_framing(self):
        alert = build_glosa_alert(self._summary(is_stale=True))
        assert "históricos" in alert

    def test_ambiguous_asks_for_specification(self):
        alert = build_glosa_alert(self._summary(
            ambiguous=True,
            candidatos=[{"registro_ans": "1", "razao_social": "Unimed A", "score": 90.0}],
        ))
        assert "ambíguo" in alert and "Especifique" in alert
