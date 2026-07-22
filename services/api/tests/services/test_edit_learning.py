"""Loop do ReportEdit: parsing de seções, contagem de mudanças e exemplar dinâmico."""
import pytest

from app.services.edit_learning import (
    LOW_EDIT_THRESHOLD,
    _changes_count,
    _parse_sections,
)


class _FakeEdit:
    def __init__(self, diff_json=None):
        self.diff_json = diff_json


SECTIONED_TEXT = """QUADRO CLÍNICO E HISTÓRIA
Paciente com gonartrose grau III (CID M17.1), com degeneração progressiva.

FALHA TERAPÊUTICA PRÉVIA
AINEs e fisioterapia por 12 semanas sem melhora.

JUSTIFICATIVA TÉCNICA E SUPERIORIDADE DO MATERIAL
Ácido hialurônico de alto peso molecular com reticulação tridimensional.

EVIDÊNCIA CIENTÍFICA
Melhora funcional demonstrada (Altman et al., 2015).

RISCO DA NÃO REALIZAÇÃO
Progressão para artroplastia de maior morbidade.

CONCLUSÃO
Solicitamos a liberação do material."""


class TestChangesCount:
    def test_counts_all_diff_types(self):
        edit = _FakeEdit(diff_json={
            "additions": [1, 2], "removals": [1], "replacements": [1, 2, 3],
        })
        assert _changes_count(edit) == 6

    def test_empty_diff(self):
        assert _changes_count(_FakeEdit()) == 0
        assert _changes_count(_FakeEdit(diff_json={})) == 0


class TestParseSections:
    def test_parses_assembled_body(self):
        sections = _parse_sections(SECTIONED_TEXT)
        assert sections is not None
        assert "gonartrose grau III" in sections["quadro_clinico"]
        assert "12 semanas" in sections["falha_terapeutica"]
        assert "Altman" in sections["evidencia_cientifica"]
        assert "liberação" in sections["conclusao"]

    def test_missing_title_returns_none(self):
        """Texto editado sem os títulos não serve de exemplar (quebraria o schema)."""
        assert _parse_sections("Texto corrido sem títulos de seção.") is None

    def test_empty_section_returns_none(self):
        broken = SECTIONED_TEXT.replace(
            "Solicitamos a liberação do material.", ""
        )
        assert _parse_sections(broken) is None


class TestDynamicExamples:
    @pytest.mark.asyncio
    async def test_no_especialidade_returns_empty(self):
        from app.services.edit_learning import get_dynamic_examples
        assert await get_dynamic_examples(None, "") == []

    def test_low_edit_threshold_is_sane(self):
        assert 0 < LOW_EDIT_THRESHOLD < 100
