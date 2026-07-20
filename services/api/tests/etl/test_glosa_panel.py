"""Testes offline do parser do Painel de Glosas ANS (PDA-057).

O header da fixture reproduz o REAL — incluindo o typo oficial da ANS
("PC_GLOSA_INCIAL"), que é exatamente o motivo de a coluna de valor ser
detectada por exclusão e nunca por nome.
"""
import pytest

from scripts.etl.download_glosa_panel import (
    ContractError,
    merge_indicator_records,
    parse_decimal,
    parse_glosa_csv,
)

HEADER = (
    '"REGISTRO_OPERADORA";"NM_RAZAO_SOCIAL_OPERADORA";"DE_PORTE_OPERADORA";'
    '"NM_SEGMENTACAO_OPERADORA";"NM_MODALIDADE_OPERADORA";"PC_GLOSA_INCIAL";'
    '"CD_PERIODO";"CD_INDICADOR";"DT_CARGA"'
)

CSV_INICIAL = HEADER + "\n" + (
    '"000477";"Sul América Seguradora De Saúde S.A.";"Médio";"Operadora Médico-Hospitalar";'
    '"Seguradora Especializada Em Saúde";17,08;"2019-01";2;"2025-10-15"\n'
    '"000477";"Sul América Seguradora De Saúde S.A.";"Médio";"Operadora Médico-Hospitalar";'
    '"Seguradora Especializada Em Saúde";19,72;"2019-02";2;"2025-10-15"\n'
    '"000515";"Allianz Saúde S/A";"Médio";"Operadora Médico-Hospitalar";'
    '"Seguradora Especializada Em Saúde";8,65;"2019-01";2;"2025-10-15"\n'
    # período inválido → pulada
    '"000515";"Allianz Saúde S/A";"Médio";"x";"y";1,00;"INVALIDO";2;"2025-10-15"\n'
    # sem registro → pulada
    '"";"Sem Registro";"Médio";"x";"y";1,00;"2019-01";2;"2025-10-15"\n'
)

CSV_FINAL = CSV_INICIAL.replace("PC_GLOSA_INCIAL", "PC_GLOSA_FINAL")


class TestParseDecimal:
    def test_comma_decimal(self):
        assert parse_decimal("17,08") == pytest.approx(17.08)

    def test_thousands_and_comma(self):
        assert parse_decimal("1.234,56") == pytest.approx(1234.56)

    def test_empty_and_dash(self):
        assert parse_decimal("") is None
        assert parse_decimal("-") is None

    def test_garbage(self):
        assert parse_decimal("abc") is None


class TestParseGlosaCsv:
    def test_value_column_by_exclusion_despite_typo(self):
        records = parse_glosa_csv(CSV_INICIAL, "pc_glosa_inicial")
        assert len(records) == 3  # 2 inválidas puladas
        assert records[0]["pc_glosa_inicial"] == pytest.approx(17.08)
        assert records[0]["registro_ans"] == "000477"
        assert records[0]["periodo"] == "2019-01"

    def test_normalized_name_stored(self):
        records = parse_glosa_csv(CSV_INICIAL, "pc_glosa_inicial")
        assert records[0]["razao_social_normalized"] == "sul america seguradora de saude s.a."

    def test_contract_error_on_missing_meta(self):
        broken = CSV_INICIAL.replace("REGISTRO_OPERADORA", "REGISTRO_X")
        with pytest.raises(ContractError):
            parse_glosa_csv(broken, "pc_glosa_inicial")

    def test_contract_error_on_two_value_columns(self):
        broken = CSV_INICIAL.replace('"PC_GLOSA_INCIAL"', '"PC_GLOSA_INCIAL";"COLUNA_EXTRA"')
        broken = broken.replace(';17,08;', ';17,08;9,99;').replace(';19,72;', ';19,72;9,99;').replace(';8,65;', ';8,65;9,99;').replace(';1,00;', ';1,00;9,99;')
        with pytest.raises(ContractError):
            parse_glosa_csv(broken, "pc_glosa_inicial")


class TestMerge:
    def test_merge_two_indicators_one_row_per_key(self):
        inicial = parse_glosa_csv(CSV_INICIAL, "pc_glosa_inicial")
        final = parse_glosa_csv(CSV_FINAL, "pc_glosa_final")
        merged = merge_indicator_records({
            "pc_glosa_inicial": inicial,
            "pc_glosa_final": final,
        })
        # 3 chaves distintas: (477, 2019-01), (477, 2019-02), (515, 2019-01)
        assert len(merged) == 3
        by_key = {(m["registro_ans"], m["periodo"]): m for m in merged}
        row = by_key[("000477", "2019-01")]
        assert row["pc_glosa_inicial"] == pytest.approx(17.08)
        assert row["pc_glosa_final"] == pytest.approx(17.08)  # fixture clonada
        # colunas dos outros indicadores existem como None
        assert row["tempo_medio_pagamento_dias"] is None
