"""
Testes unitários para o checker Anvisa.
Determinísticos e offline — testa parsing sem rede.
"""
import pytest
from datetime import datetime

from scripts.etl.check_anvisa import parse_anvisa_response


class TestParseAnvisaResponse:
    def test_none_input(self):
        result = parse_anvisa_response(None)
        assert result["status"] == "desconhecido"

    def test_empty_dict(self):
        result = parse_anvisa_response({})
        assert result["status"] == "desconhecido"

    def test_ativo_status(self):
        data = {
            "registro": "80117900123",
            "nomeProduto": "Kit EC2",
            "razaoSocial": "Empresa Teste",
            "situacao": "Válido",
            "dataValidade": "31/12/2030",
            "classeRisco": "III",
        }
        result = parse_anvisa_response(data)
        assert result["status"] == "ativo"
        assert result["registro"] == "80117900123"
        assert result["nome_comercial"] == "Kit EC2"
        assert result["data_validade"] is not None

    def test_vencido_by_situacao(self):
        data = {"situacao": "Vencido", "registro": "123"}
        result = parse_anvisa_response(data)
        assert result["status"] == "vencido"

    def test_vencido_by_date(self):
        data = {
            "situacao": "Válido",
            "dataValidade": "01/01/2020",
            "registro": "123",
        }
        result = parse_anvisa_response(data)
        assert result["status"] == "vencido"

    def test_suspenso_status(self):
        data = {"situacao": "Suspenso", "registro": "123"}
        result = parse_anvisa_response(data)
        assert result["status"] == "suspenso"

    def test_cancelado_status(self):
        data = {"situacao": "Cancelado", "registro": "123"}
        result = parse_anvisa_response(data)
        assert result["status"] == "cancelado"

    def test_alternative_field_names(self):
        data = {
            "numeroRegistro": "999",
            "nomeComercial": "Produto X",
            "fabricante": "Fab Y",
            "situacaoRegistro": "Vigente",
            "dataVencimento": "2028-06-15",
        }
        result = parse_anvisa_response(data)
        assert result["registro"] == "999"
        assert result["nome_comercial"] == "Produto X"
        assert result["fabricante"] == "Fab Y"
        assert result["status"] == "ativo"

    def test_preserves_raw_json(self):
        data = {"registro": "123", "situacao": "Válido", "extra_field": "value"}
        result = parse_anvisa_response(data)
        assert result["dados_json"] == data

    def test_iso_date_format(self):
        data = {"registro": "123", "situacao": "Válido", "dataValidade": "2030-12-31"}
        result = parse_anvisa_response(data)
        assert result["data_validade"].year == 2030
