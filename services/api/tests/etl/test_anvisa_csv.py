"""
Testes unitários para o ETL de CSV Anvisa (Dados Abertos).
Determinísticos e offline — testa parsing sem rede.
"""
import pytest
from datetime import datetime, timezone

from scripts.etl.download_anvisa import _parse_validade, _parse_row


class TestParseValidade:
    def test_vigente(self):
        status, dt = _parse_validade("VIGENTE")
        assert status == "ativo"
        assert dt is None

    def test_vigente_lowercase(self):
        status, dt = _parse_validade("vigente")
        assert status == "ativo"
        assert dt is None

    def test_future_date(self):
        status, dt = _parse_validade("31/12/2099")
        assert status == "ativo"
        assert dt is not None
        assert dt.year == 2099

    def test_past_date_is_vencido(self):
        status, dt = _parse_validade("01/01/2020")
        assert status == "vencido"
        assert dt.year == 2020

    def test_iso_date_format(self):
        status, dt = _parse_validade("2099-06-15")
        assert status == "ativo"
        assert dt.month == 6

    def test_cancelado_string(self):
        status, dt = _parse_validade("CANCELADO")
        assert status == "cancelado"

    def test_suspenso_string(self):
        status, dt = _parse_validade("SUSPENSO")
        assert status == "suspenso"

    def test_empty_string(self):
        status, dt = _parse_validade("")
        assert status == "desconhecido"
        assert dt is None

    def test_none_input(self):
        status, dt = _parse_validade(None)
        assert status == "desconhecido"

    def test_timezone_aware(self):
        """Datas parseadas devem ser timezone-aware (UTC)."""
        status, dt = _parse_validade("31/12/2099")
        assert dt.tzinfo is not None


class TestParseRow:
    def test_valid_row(self):
        row = {
            "NUMERO_REGISTRO_CADASTRO": "80145900901",
            "NOME_COMERCIAL": "TELAS PROLENE",
            "DETENTOR_REGISTRO_CADASTRO": "J&J",
            "CLASSE_RISCO": "IV",
            "VALIDADE_REGISTRO_CADASTRO": "VIGENTE",
            "NOME_TECNICO": "Telas Cirúrgicas",
            "NOME_FABRICANTE": "Ethicon",
            "NOME_PAIS_FABRIC": "ESTADOS UNIDOS",
            "CNPJ_DETENTOR_REGISTRO_CADASTRO": "12345678000100",
            "NUMERO_PROCESSO": "250000001234567",
            "DT_PUB_REGISTRO_CADASTRO": "01/01/2010",
            "DT_ATUALIZACAO_DADO": "01/01/2026",
        }
        parsed = _parse_row(row)
        assert parsed is not None
        assert parsed["registro"] == "80145900901"
        assert parsed["nome_comercial"] == "TELAS PROLENE"
        assert parsed["fabricante"] == "J&J"
        assert parsed["classe_risco"] == "IV"
        assert parsed["status"] == "ativo"
        assert isinstance(parsed["dados_json"], dict)

    def test_empty_registro_returns_none(self):
        row = {"NUMERO_REGISTRO_CADASTRO": "", "NOME_COMERCIAL": "Teste"}
        assert _parse_row(row) is None

    def test_missing_registro_returns_none(self):
        row = {"NOME_COMERCIAL": "Teste"}
        assert _parse_row(row) is None

    def test_expired_product(self):
        row = {
            "NUMERO_REGISTRO_CADASTRO": "12345",
            "NOME_COMERCIAL": "Produto Vencido",
            "DETENTOR_REGISTRO_CADASTRO": "Empresa",
            "CLASSE_RISCO": "II",
            "VALIDADE_REGISTRO_CADASTRO": "01/01/2020",
        }
        parsed = _parse_row(row)
        assert parsed["status"] == "vencido"
        assert parsed["data_validade"].year == 2020

    def test_strips_whitespace(self):
        row = {
            "NUMERO_REGISTRO_CADASTRO": "  80145900901  ",
            "NOME_COMERCIAL": "  PROLENE  ",
            "DETENTOR_REGISTRO_CADASTRO": "  J&J  ",
            "CLASSE_RISCO": "  IV  ",
            "VALIDADE_REGISTRO_CADASTRO": "VIGENTE",
        }
        parsed = _parse_row(row)
        assert parsed["registro"] == "80145900901"
        assert parsed["nome_comercial"] == "PROLENE"
        assert parsed["fabricante"] == "J&J"

    def test_empty_optional_fields(self):
        row = {
            "NUMERO_REGISTRO_CADASTRO": "99999",
            "NOME_COMERCIAL": "",
            "DETENTOR_REGISTRO_CADASTRO": "",
            "CLASSE_RISCO": "",
            "VALIDADE_REGISTRO_CADASTRO": "VIGENTE",
        }
        parsed = _parse_row(row)
        assert parsed["nome_comercial"] is None
        assert parsed["fabricante"] is None
        assert parsed["classe_risco"] is None

    def test_dados_json_contains_original(self):
        row = {
            "NUMERO_REGISTRO_CADASTRO": "12345",
            "NOME_COMERCIAL": "Teste",
            "VALIDADE_REGISTRO_CADASTRO": "VIGENTE",
            "EXTRA_FIELD": "extra_value",
        }
        parsed = _parse_row(row)
        assert "EXTRA_FIELD" in parsed["dados_json"]
        assert parsed["dados_json"]["EXTRA_FIELD"] == "extra_value"
