"""
Testes unitários para ETL da TUSS 19.
Determinísticos e offline — sem acesso à rede.
"""
import pytest
from scripts.etl.download_tuss import (
    parse_tuss_csv_content,
    normalize_text,
    extract_table_19_from_zip,
)

FIXTURE_CSV = """CD_PROCEDIMENTO;DS_PROCEDIMENTO;GRUPO;SUBGRUPO
30715016;Barreira anti-aderencia biorreabsorvivel;Materiais;Cirurgico
20104120;Acido hialuronico intra-articular 6000kDa;Materiais;Ortopedia
30727049;Parafuso de interferencia bioabsorvivel PLLA;Implantes;Ortopedia
30604020;Tela de polipropileno macroporosa;Materiais;Herniorrafia
99999999;Produto teste com acentuação;Grupo Teste;Sub Teste
"""

FIXTURE_CSV_ALT = """CODIGO;DESCRICAO;GRUPO
10101010;Consulta em consultorio;Procedimentos
20202020;Hemograma completo;Laboratorial
"""


class TestNormalizeText:
    def test_basic(self):
        assert normalize_text("  ÁCIDO HIALURÔNICO  ") == "ácido hialurônico"

    def test_multiple_spaces(self):
        assert normalize_text("a  b   c") == "a b c"

    def test_empty(self):
        assert normalize_text("") == ""

    def test_none_like(self):
        assert normalize_text("None") == "none"


class TestParseTussCsv:
    def test_parses_standard_format(self):
        records = parse_tuss_csv_content(FIXTURE_CSV)
        assert len(records) == 5

    def test_extracts_codigo(self):
        records = parse_tuss_csv_content(FIXTURE_CSV)
        codes = [r["codigo_tuss"] for r in records]
        assert "30715016" in codes
        assert "20104120" in codes

    def test_extracts_nome(self):
        records = parse_tuss_csv_content(FIXTURE_CSV)
        first = next(r for r in records if r["codigo_tuss"] == "30715016")
        assert "Barreira" in first["nome"]

    def test_normalizes_display(self):
        records = parse_tuss_csv_content(FIXTURE_CSV)
        first = records[0]
        assert first["display_normalized"] == normalize_text(first["nome"])

    def test_preserves_raw_data(self):
        records = parse_tuss_csv_content(FIXTURE_CSV)
        for r in records:
            assert isinstance(r["raw_data"], dict)
            assert len(r["raw_data"]) > 0

    def test_handles_grupo_subgrupo(self):
        records = parse_tuss_csv_content(FIXTURE_CSV)
        first = records[0]
        assert first["grupo"] == "Materiais"
        assert first["subgrupo"] == "Cirurgico"

    def test_skips_empty_rows(self):
        csv_with_empty = """CD_PROCEDIMENTO;DS_PROCEDIMENTO;GRUPO
;;\n10101010;Teste;Grupo"""
        records = parse_tuss_csv_content(csv_with_empty)
        assert len(records) == 1

    def test_alternative_column_names(self):
        records = parse_tuss_csv_content(FIXTURE_CSV_ALT)
        assert len(records) == 2
        assert records[0]["codigo_tuss"] == "10101010"

    def test_idempotency_no_duplicates(self):
        records1 = parse_tuss_csv_content(FIXTURE_CSV)
        records2 = parse_tuss_csv_content(FIXTURE_CSV)
        codes1 = set(r["codigo_tuss"] for r in records1)
        codes2 = set(r["codigo_tuss"] for r in records2)
        assert codes1 == codes2

    def test_all_records_have_required_fields(self):
        records = parse_tuss_csv_content(FIXTURE_CSV)
        for r in records:
            assert r["codigo_tuss"]
            assert r["nome"]
            assert r["display_normalized"]
            assert r["ativo"] is True


class TestExtractFromZip:
    def test_empty_zip_returns_empty(self):
        import io, zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", "no csv here")
        records = extract_table_19_from_zip(buf.getvalue())
        assert records == []

    def test_zip_with_csv(self):
        import io, zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("tabela_19.csv", FIXTURE_CSV)
        records = extract_table_19_from_zip(buf.getvalue())
        assert len(records) == 5
