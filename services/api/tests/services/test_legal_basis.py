"""Normas citadas nos laudos: fonte única, normalizador de revogadas e templates."""
import pytest

from app.services.legal_basis import (
    BASE_LEGAL_PADRAO,
    BASES_LEGAIS_VIGENTES,
    DECLARACAO_USO_IA,
    PROMPT_REGRA_BASE_LEGAL,
    find_revoked_citations,
    has_legal_basis,
    modernize_citations,
)


class TestModernizeCitations:
    @pytest.mark.parametrize("texto, esperado", [
        ("Conforme a RN 395 da ANS", "Conforme a RN 623/2024 da ANS"),
        ("com fundamento na RN 395/2016,", "com fundamento na RN 623/2024,"),
        ("nos termos da RN nº 395/16", "nos termos da RN 623/2024"),
        ("Resolução Normativa nº 395 da ANS", "RN 623/2024 da ANS"),
        ("cobertura (RN 428/465)", "cobertura (RN 465/2021)"),
        ("Rol da RN 428/2017", "Rol da RN 465/2021"),
        ("Resolução CFM nº 1.956/2010", "Resolução CFM 2.318/2022"),
        ("conforme CFM 1956", "conforme Resolução CFM 2.318/2022"),
        ("Res. CFM 1.804/2006", "Resolução CFM 2.318/2022"),
    ])
    def test_troca_revogada_pela_vigente(self, texto, esperado):
        corrigido, correcoes = modernize_citations(texto)
        assert corrigido == esperado
        assert len(correcoes) == 1

    @pytest.mark.parametrize("texto", [
        "Nos termos da RN 424/2017 e da RN 465/2021.",
        "RN 623/2024 e Res. CFM 2.318/2022.",
        "registro ANVISA 80395000012",           # número qualquer contendo 395
        "RN 3950 (inexistente, não é a 395)",
        "",
    ])
    def test_nao_mexe_em_norma_vigente_ou_numero_solto(self, texto):
        corrigido, correcoes = modernize_citations(texto)
        assert corrigido == texto
        assert correcoes == []

    def test_none_volta_como_veio(self):
        assert modernize_citations(None) == (None, [])

    def test_idempotente(self):
        uma, _ = modernize_citations("RN 395 e RN 428 e CFM 1.956")
        duas, correcoes = modernize_citations(uma)
        assert duas == uma
        assert correcoes == []


class TestHasLegalBasis:
    def test_reconhece_normas_vigentes(self):
        assert has_legal_basis("Nos termos da RN 623/2024")
        assert has_legal_basis("Res. CFM 2.318/2022")
        assert has_legal_basis("cobertura obrigatória pela ANS")

    def test_revogada_ainda_conta_como_presenca(self):
        # é corrigida pelo normalizador, não reprova o checklist
        assert has_legal_basis("Conforme RN 395")

    def test_modo_estrito_exige_norma(self):
        assert not has_legal_basis("Texto sem menção à ANS", accept_bare_ans=False)
        assert has_legal_basis("RN 623/2024 da ANS", accept_bare_ans=False)

    def test_nao_confunde_palavra_que_contem_ans(self):
        assert not has_legal_basis("paciente com cansaço e transplante prévio")


class TestTextosCanonicos:
    def test_textos_padrao_sem_normas_revogadas(self):
        for texto in (BASE_LEGAL_PADRAO, DECLARACAO_USO_IA, " ".join(BASES_LEGAIS_VIGENTES)):
            assert find_revoked_citations(texto) == []

    def test_base_legal_cita_as_vigentes(self):
        for norma in ("RN 424/2017", "RN 465/2021", "RN 623/2024", "CFM 2.318/2022"):
            assert norma in BASE_LEGAL_PADRAO

    def test_prompt_proibe_revogadas_e_nao_tem_chaves(self):
        # o bloco é concatenado num template .format(): chaves quebrariam o prompt
        assert "{" not in PROMPT_REGRA_BASE_LEGAL and "}" not in PROMPT_REGRA_BASE_LEGAL
        assert "NUNCA CITE" in PROMPT_REGRA_BASE_LEGAL
        assert "RN 623/2024" in PROMPT_REGRA_BASE_LEGAL

    def test_declaracao_ia_cita_cfm_2454(self):
        assert "CFM 2.454/2026" in DECLARACAO_USO_IA


class TestFontesDoPipelineSemRevogadas:
    """Nada que alimenta o LLM pode instruí-lo a citar norma revogada."""

    def test_writer_prompt(self):
        from app.services.agents.prompts import WRITER_SYSTEM
        regra5 = WRITER_SYSTEM.split("REGRA #5")[1].split("REGRA #6")[0]
        # Só pode aparecer na lista de "NUNCA CITE"
        antes_da_proibicao = regra5.split("NORMAS REVOGADAS")[0]
        assert find_revoked_citations(antes_da_proibicao) == []
        assert "RN 623/2024" in regra5

    def test_writer_prompt_ainda_formata(self):
        from app.services.agents.prompts import WRITER_SYSTEM
        import string
        campos = {f for _, f, _, _ in string.Formatter().parse(WRITER_SYSTEM) if f}
        WRITER_SYSTEM.format(**{c: "x" for c in campos})

    def test_few_shots(self):
        from app.services.agents.few_shot_examples import _BASE_LEGAL_PADRAO
        assert _BASE_LEGAL_PADRAO == BASE_LEGAL_PADRAO

    def test_seed_templates(self):
        from app.db.init_db import TEMPLATES_SEED, UROLOGY_TEMPLATES_SEED
        for t in TEMPLATES_SEED + UROLOGY_TEMPLATES_SEED:
            assert find_revoked_citations(t.get("template_corpo") or "") == [], t["nome"]
            for ex in t.get("exemplos_aprovados") or []:
                assert find_revoked_citations(ex) == [], t["nome"]
            assert t["bases_legais"] == BASES_LEGAIS_VIGENTES


@pytest.mark.asyncio
async def test_modernize_report_templates_atualiza_banco_existente(monkeypatch):
    """Templates já gravados em produção (seed antigo com RN 395) são atualizados."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.db.session import Base
    from app.db.models import ReportTemplate
    import app.db.init_db as init_db

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(init_db, "AsyncSessionLocal", Session)

    frase_antiga = init_db._FRASES_NEGATIVA_ANTIGAS[0]
    async with Session() as db:
        db.add(ReportTemplate(
            nome="legado",
            template_corpo="Corpo. " + frase_antiga,
            exemplos_aprovados=["Exemplo. " + init_db._FRASES_NEGATIVA_ANTIGAS[1], "Sem norma."],
            bases_legais=["RN 395", "RN 424", "RN 428", "RN 465"],
        ))
        db.add(ReportTemplate(nome="ja_ok", template_corpo="Nada a mudar.",
                              bases_legais=list(BASES_LEGAIS_VIGENTES)))
        await db.commit()

    assert await init_db.modernize_report_templates() == 1
    assert await init_db.modernize_report_templates() == 0  # idempotente

    async with Session() as db:
        t = (await db.execute(select(ReportTemplate).where(ReportTemplate.nome == "legado"))).scalar_one()
        assert "RN 395" not in t.template_corpo
        assert init_db.TEMPLATE_FRASE_NEGATIVA in t.template_corpo
        assert init_db.TEMPLATE_FRASE_NEGATIVA in t.exemplos_aprovados[0]
        assert t.exemplos_aprovados[1] == "Sem norma."
        # item a item: revogadas viram vigentes, duplicata (RN 465) some, ordem mantida
        assert t.bases_legais == ["RN 623/2024", "RN 424", "RN 465/2021"]
    await engine.dispose()


class TestModernizeBasesLegais:
    def test_preserva_bases_nao_relacionadas(self):
        from app.db.init_db import _modernize_bases_legais
        entrada = ["RN 395", "Lei 9.656/1998", "Código de Ética Médica"]
        assert _modernize_bases_legais(entrada) == [
            "RN 623/2024", "Lei 9.656/1998", "Código de Ética Médica",
        ]

    def test_lista_sem_revogadas_fica_igual(self):
        from app.db.init_db import _modernize_bases_legais
        assert _modernize_bases_legais(list(BASES_LEGAIS_VIGENTES)) == BASES_LEGAIS_VIGENTES

    def test_deduplica_mesma_norma_com_e_sem_ano(self):
        from app.db.init_db import _modernize_bases_legais
        assert _modernize_bases_legais(["RN 428", "RN 465"]) == ["RN 465/2021"]
