"""
Testes unitários para ETL do Rol (Anexo I).
Determinísticos e offline — usa fixture Excel em memória.
"""
import io
import pytest

from scripts.etl.download_rol import parse_rol_xlsx


def _create_test_xlsx() -> bytes:
    """Cria um XLSX mínimo em memória para testes."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Procedimentos"

    ws.append(["CÓDIGO", "PROCEDIMENTO", "AMBULATORIAL", "HOSPITALAR", "OBSTÉTRICA", "ODONTOLÓGICA", "DUT", "GRUPO", "SUBGRUPO"])
    ws.append(["30715016", "Implante de barreira anti-aderência", "SIM", "SIM", "", "", "10", "Cirúrgico", "Geral"])
    ws.append(["20104120", "Viscossuplementação articular", "SIM", "", "", "", "", "Terapêutico", "Ortopedia"])
    ws.append(["30727049", "Reconstrução de LCA", "", "SIM", "", "", "45", "Cirúrgico", "Ortopedia"])
    ws.append(["30604020", "Herniorrafia com tela", "", "SIM", "", "", "", "Cirúrgico", "Geral"])
    ws.append(["", "", "", "", "", "", "", "", ""])  # Linha vazia

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestParseRolXlsx:
    @pytest.fixture
    def xlsx_bytes(self):
        return _create_test_xlsx()

    def test_parses_correct_count(self, xlsx_bytes):
        records = parse_rol_xlsx(xlsx_bytes)
        assert len(records) >= 4

    def test_extracts_codigo(self, xlsx_bytes):
        records = parse_rol_xlsx(xlsx_bytes)
        codes = [r["codigo_procedimento"] for r in records]
        assert "30715016" in codes

    def test_extracts_nome(self, xlsx_bytes):
        records = parse_rol_xlsx(xlsx_bytes)
        first = next(r for r in records if r["codigo_procedimento"] == "30715016")
        assert "barreira" in first["nome"].lower() or "Implante" in first["nome"]

    def test_segmentacao_ambulatorial(self, xlsx_bytes):
        records = parse_rol_xlsx(xlsx_bytes)
        proc = next(r for r in records if r["codigo_procedimento"] == "20104120")
        assert proc["segmentacao_ambulatorial"] is True

    def test_segmentacao_hospitalar(self, xlsx_bytes):
        records = parse_rol_xlsx(xlsx_bytes)
        proc = next(r for r in records if r["codigo_procedimento"] == "30727049")
        assert proc["segmentacao_hospitalar"] is True

    def test_dut_detection(self, xlsx_bytes):
        records = parse_rol_xlsx(xlsx_bytes)
        with_dut = next(r for r in records if r["codigo_procedimento"] == "30715016")
        without_dut = next(r for r in records if r["codigo_procedimento"] == "20104120")
        assert with_dut["tem_dut"] is True
        assert with_dut["dut_numero"] == "10"
        assert without_dut["tem_dut"] is False

    def test_skips_empty_rows(self, xlsx_bytes):
        records = parse_rol_xlsx(xlsx_bytes)
        for r in records:
            assert r["codigo_procedimento"] != ""

    def test_preserves_raw_data(self, xlsx_bytes):
        records = parse_rol_xlsx(xlsx_bytes)
        for r in records:
            assert isinstance(r["raw_data"], dict)

    def test_grupo_subgrupo(self, xlsx_bytes):
        records = parse_rol_xlsx(xlsx_bytes)
        proc = next(r for r in records if r["codigo_procedimento"] == "30715016")
        assert proc["grupo"] is not None
