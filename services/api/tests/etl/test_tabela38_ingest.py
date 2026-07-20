"""Testes offline do extrator/parser da TISS Tabela 38 (motivos de glosa)."""
import io

import openpyxl

from scripts.etl.extract_tabela38 import parse_tabela38_sheet, find_terminologias_xlsx
from scripts.etl.ingest_tabela38 import parse_tabela38_csv


def _create_tab38_xlsx(trailing_empty: int = 0) -> bytes:
    """Espelha a estrutura real: linhas de lixo, título, header na linha 6, dados."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Tab 38"
    ws.append([None, None, None, None, None])
    ws.append([None, None, None, None, None])
    ws.append([None, None, None, None, None])
    ws.append(["Tabela 38 - Terminologia de mensagens (glosas, negativas e ...)", None, None, None, None])
    ws.append([None, None, None, None, None])
    ws.append(["Código do Termo", "Termo", "Data de início de vigência",
               "Data de fim de vigência", "Data de fim de implantação"])
    ws.append(["1001", "NÚMERO DA CARTEIRA INVÁLIDO", "2006-11-16 00:00:00", None, None])
    ws.append(["1801", "PROCEDIMENTO INVÁLIDO", "2006-11-16 00:00:00", None, None])
    ws.append(["1003", "MOTIVO ENCERRADO", "2006-11-16 00:00:00", "2020-06-30 00:00:00", None])
    ws.append([None, "nota de rodapé sem código", None, None, None])  # parcial → pulada
    for _ in range(trailing_empty):
        ws.append([None, None, None, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestParseTabela38Sheet:
    def test_header_autodetect_and_count(self):
        records = parse_tabela38_sheet(_create_tab38_xlsx())
        assert len(records) == 3
        assert records[0]["codigo"] == "1001"
        assert records[1]["descricao"] == "PROCEDIMENTO INVÁLIDO"

    def test_datetime_truncated_to_date(self):
        records = parse_tabela38_sheet(_create_tab38_xlsx())
        assert records[0]["vigencia_inicio"] == "2006-11-16"
        assert records[2]["vigencia_fim"] == "2020-06-30"

    def test_stops_on_trailing_empty_rows(self):
        """A dimensão mentirosa do read-only não pode virar loop de 1M linhas."""
        records = parse_tabela38_sheet(_create_tab38_xlsx(trailing_empty=200))
        assert len(records) == 3

    def test_find_xlsx_tolerates_broken_encoding(self):
        names = [
            "Padrao_TISS_X/TUSS - Demais terminologias - VERSÃO 202601.xlsx",
            "Padrao_TISS_X/~$TUSS - Demais terminologias - VERSÃO 202601.xlsx",  # lock
            "Padrao_TISS_X/outro.pdf",
        ]
        assert find_terminologias_xlsx(names) == names[0]


class TestParseTabela38Csv:
    FIXTURE = (
        "codigo;descricao;vigencia_inicio;vigencia_fim\n"
        "1001;NÚMERO DA CARTEIRA INVÁLIDO;2006-11-16;\n"
        "1003;MOTIVO ENCERRADO;2006-11-16;2020-06-30\n"
        ";sem codigo;;\n"
    )

    def test_parse_and_skip_invalid(self):
        records = parse_tabela38_csv(self.FIXTURE)
        assert len(records) == 2

    def test_ativo_computed_from_vigencia(self):
        records = parse_tabela38_csv(self.FIXTURE)
        by_code = {r["codigo"]: r for r in records}
        assert by_code["1001"]["ativo"] is True       # sem vigencia_fim
        assert by_code["1003"]["ativo"] is False      # vigência encerrada em 2020

    def test_normalized_and_raw_data(self):
        records = parse_tabela38_csv(self.FIXTURE)
        assert records[0]["descricao_normalized"] == "número da carteira inválido"
        assert isinstance(records[0]["raw_data"], dict)
