"""
Testes unitários para TussValidator.
Sem banco — testa apenas a lógica de validação que não requer DB.
Os testes com banco ficam na suite de integração.

Este arquivo testa principalmente as dataclasses e contratos.
"""
import pytest

from app.services.tuss_validator import TussValidation, TissValidation, AnvisaStatusResult


class TestTussValidation:
    def test_valid_code(self):
        v = TussValidation(
            codigo="30715016",
            valido=True,
            nome="Barreira anti-aderência",
            grupo="Materiais",
            mensagem="OK",
        )
        assert v.valido is True
        assert v.codigo == "30715016"

    def test_invalid_code(self):
        v = TussValidation(
            codigo="99999999",
            valido=False,
            mensagem="Código não encontrado",
        )
        assert v.valido is False


class TestTissValidation:
    def test_permitted(self):
        v = TissValidation(
            tipo_guia="internacao",
            campo="opme",
            codigo="30715016",
            permitido=True,
        )
        assert v.permitido is True

    def test_prohibited_honorarios(self):
        v = TissValidation(
            tipo_guia="internacao",
            campo="honorarios",
            codigo="30715016",
            permitido=False,
            mensagem="TUSS 19 em Honorários é glosa",
        )
        assert v.permitido is False
        assert "glosa" in v.mensagem.lower()


class TestAnvisaStatusResult:
    def test_ativo(self):
        s = AnvisaStatusResult(registro="123", status="ativo")
        assert s.alerta is None

    def test_vencido_com_alerta(self):
        s = AnvisaStatusResult(
            registro="123",
            status="vencido",
            alerta="Registro vencido",
        )
        assert s.alerta is not None

    def test_desconhecido(self):
        s = AnvisaStatusResult(registro="123", status="desconhecido", alerta="Não encontrado")
        assert s.status == "desconhecido"
