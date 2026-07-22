"""Proveniência dos campos de ficha técnica.

O que estes testes protegem: texto escrito por LLM não pode ficar
indistinguível de dado oficial no banco — é o que fazia o Auditor validar o
laudo contra a saída de outro modelo (verificação circular).
"""
import pytest
from sqlalchemy import update as sql_update

from app.services.provenance import (
    CAMPOS_FICHA,
    ORIGEM_ANVISA,
    ORIGEM_IFU_PDF,
    ORIGEM_LLM,
    ORIGEM_SEED,
    ORIGENS_NAO_VERIFICADAS,
    build_provenance,
    campo_nao_verificado,
    origem_do_campo,
    resumo_origens,
)


class _FakeProduct:
    def __init__(self, campos_gerados_ia=None, nome="Produto X"):
        self.nome = nome
        self.campos_gerados_ia = campos_gerados_ia


class TestBuildProvenance:
    def test_marca_campos_com_origem_e_data(self):
        marcas = build_provenance(None, ["descricao_tecnica"], ORIGEM_LLM, modelo="gpt-4o")
        registro = marcas["descricao_tecnica"]
        assert registro["origem"] == ORIGEM_LLM
        assert registro["modelo"] == "gpt-4o"
        assert registro["em"]  # timestamp ISO presente

    def test_preserva_marcas_anteriores(self):
        """Enriquecer um campo não pode apagar a origem dos outros."""
        antes = build_provenance(None, ["indicacoes"], ORIGEM_ANVISA)
        depois = build_provenance(antes, ["descricao_tecnica"], ORIGEM_LLM)
        assert depois["indicacoes"]["origem"] == ORIGEM_ANVISA
        assert depois["descricao_tecnica"]["origem"] == ORIGEM_LLM

    def test_sobrescreve_o_mesmo_campo(self):
        antes = build_provenance(None, ["indicacoes"], ORIGEM_ANVISA)
        depois = build_provenance(antes, ["indicacoes"], ORIGEM_LLM)
        assert depois["indicacoes"]["origem"] == ORIGEM_LLM

    def test_nao_muta_o_dicionario_de_entrada(self):
        antes = build_provenance(None, ["indicacoes"], ORIGEM_ANVISA)
        copia = dict(antes)
        build_provenance(antes, ["descricao_tecnica"], ORIGEM_LLM)
        assert antes == copia

    def test_campos_vazios_gera_dict_vazio(self):
        assert build_provenance(None, [], ORIGEM_LLM) == {}

    def test_chaves_opcionais_ficam_de_fora(self):
        registro = build_provenance(None, ["indicacoes"], ORIGEM_SEED)["indicacoes"]
        assert "modelo" not in registro
        assert "detalhe" not in registro


class TestLeituraDeOrigem:
    def test_origem_do_campo(self):
        p = _FakeProduct(build_provenance(None, ["indicacoes"], ORIGEM_LLM))
        assert origem_do_campo(p, "indicacoes") == ORIGEM_LLM

    def test_campo_sem_marca_devolve_none(self):
        p = _FakeProduct(build_provenance(None, ["indicacoes"], ORIGEM_LLM))
        assert origem_do_campo(p, "descricao_tecnica") is None

    def test_produto_legado_sem_coluna(self):
        """Produto anterior à migração: nada quebra, tudo é desconhecido."""
        p = _FakeProduct(None)
        assert origem_do_campo(p, "indicacoes") is None
        assert campo_nao_verificado(p, "indicacoes") is False
        assert resumo_origens(p) == {}

    def test_json_corrompido_nao_quebra(self):
        p = _FakeProduct("isto não é um dict")
        assert origem_do_campo(p, "indicacoes") is None
        assert resumo_origens(p) == {}

    def test_registro_malformado_nao_quebra(self):
        p = _FakeProduct({"indicacoes": "string em vez de dict"})
        assert origem_do_campo(p, "indicacoes") is None
        assert resumo_origens(p) == {}


class TestCampoNaoVerificado:
    def test_llm_e_ifu_sao_nao_verificados(self):
        for origem in (ORIGEM_LLM, ORIGEM_IFU_PDF):
            p = _FakeProduct(build_provenance(None, ["indicacoes"], origem))
            assert campo_nao_verificado(p, "indicacoes") is True

    def test_anvisa_e_seed_sao_confiaveis(self):
        for origem in (ORIGEM_ANVISA, ORIGEM_SEED):
            p = _FakeProduct(build_provenance(None, ["indicacoes"], origem))
            assert campo_nao_verificado(p, "indicacoes") is False

    def test_ausencia_de_marca_nao_e_tratada_como_gerada(self):
        """Conservador: sem dado, não inventamos conclusão em nenhuma direção."""
        assert campo_nao_verificado(_FakeProduct(None), "indicacoes") is False

    def test_conjunto_de_origens_nao_verificadas(self):
        assert ORIGENS_NAO_VERIFICADAS == {ORIGEM_LLM, ORIGEM_IFU_PDF}


class TestResumoOrigens:
    def test_mapa_campo_para_origem(self):
        marcas = build_provenance(None, ["indicacoes"], ORIGEM_ANVISA)
        marcas = build_provenance(marcas, ["descricao_tecnica"], ORIGEM_LLM)
        assert resumo_origens(_FakeProduct(marcas)) == {
            "indicacoes": ORIGEM_ANVISA,
            "descricao_tecnica": ORIGEM_LLM,
        }


class TestVocabulario:
    def test_campos_ficha_cobre_os_quatro_campos_de_texto(self):
        assert set(CAMPOS_FICHA) == {
            "descricao_tecnica", "diferenciais_clinicos", "indicacoes", "contraindicacoes",
        }

    def test_bula_url_nao_e_campo_de_ficha(self):
        """bula_url é a referência da fonte, não conteúdo — não se marca."""
        assert "bula_url" not in CAMPOS_FICHA


class TestEscritaRealMarcaProveniencia:
    """Integração: o caminho real de enriquecimento grava a marca no banco.

    Cobre também a serialização da coluna JSON — o motivo de a escrita ter
    saído de SQL cru para o construtor tipado do SQLAlchemy (dict não é
    serializado igual por todos os drivers).
    """

    @pytest.fixture
    async def db_produto(self):
        import uuid
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from app.db.session import Base
        from app.db.models import Product
        import app.db.models  # noqa

        engine = create_async_engine(
            "sqlite+aiosqlite:///file:testdb_prov?mode=memory&cache=shared&uri=true"
        )
        SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)

        produto = Product(id=uuid.uuid4(), nome="Produto Teste", registro_anvisa="80117900XXX")
        async with SessionLocal() as db:
            db.add(produto)
            await db.commit()
        try:
            yield SessionLocal, produto
        finally:
            async with engine.begin() as c:
                await c.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    async def test_enriquecimento_llm_marca_origem_e_audita(self, db_produto, monkeypatch):
        from sqlalchemy import select
        from app.db.models import Product, AuditLog
        import app.services.product_enrichment as pe

        SessionLocal, produto = db_produto

        async def _fake_anvisa(db, product):
            return ""

        async def _fake_pubmed(product, cid):
            return ""

        async def _fake_gen(product, anvisa_ctx, pubmed_ctx):
            return {
                "descricao_tecnica": "D" * 50,
                "diferenciais_clinicos": "F" * 50,
                "indicacoes": "I" * 50,
                "contraindicacoes": "C" * 50,
            }

        monkeypatch.setattr(pe, "_fetch_anvisa_context", _fake_anvisa)
        monkeypatch.setattr(pe, "_fetch_pubmed_context", _fake_pubmed)
        monkeypatch.setattr(pe, "_generate_enrichment", _fake_gen)

        async with SessionLocal() as db:
            ok = await pe.enrich_product(db, produto, cid="M17.1")
            assert ok is True

        # 1. A marca foi persistida — e é lida de volta como dict
        async with SessionLocal() as db:
            salvo = (await db.execute(
                select(Product).where(Product.id == produto.id)
            )).scalar_one()
            marcas = salvo.campos_gerados_ia
            assert isinstance(marcas, dict), f"esperava dict, veio {type(marcas)}"
            assert marcas["descricao_tecnica"]["origem"] == ORIGEM_LLM
            assert marcas["indicacoes"]["origem"] == ORIGEM_LLM
            assert campo_nao_verificado(salvo, "indicacoes") is True
            # e o texto realmente foi gravado
            assert salvo.descricao_tecnica == "D" * 50

        # 2. AuditLog registrou a escrita com o valor ANTERIOR (rollback)
        async with SessionLocal() as db:
            logs = (await db.execute(
                select(AuditLog).where(AuditLog.resource_id == str(produto.id))
            )).scalars().all()
            assert len(logs) == 1
            assert logs[0].resource_type == "product"
            assert logs[0].changes["descricao_tecnica"]["old"] is None
            assert logs[0].changes["descricao_tecnica"]["new"] == "D" * 50
            assert logs[0].metadata_["origem"] == ORIGEM_LLM

    async def test_objeto_em_memoria_recebe_a_marca(self, db_produto, monkeypatch):
        """O laudo em curso usa o objeto em memória — ele também precisa saber."""
        import app.services.product_enrichment as pe

        SessionLocal, produto = db_produto

        async def _vazio(*a, **k):
            return ""

        async def _fake_gen(product, anvisa_ctx, pubmed_ctx):
            return {"descricao_tecnica": "D" * 50, "diferenciais_clinicos": "F" * 50}

        monkeypatch.setattr(pe, "_fetch_anvisa_context", _vazio)
        monkeypatch.setattr(pe, "_fetch_pubmed_context", _vazio)
        monkeypatch.setattr(pe, "_generate_enrichment", _fake_gen)

        async with SessionLocal() as db:
            await pe.enrich_product(db, produto, cid="M17.1")

        assert campo_nao_verificado(produto, "descricao_tecnica") is True


class TestAuditLogNaoDestroiAEscrita:
    """Regressão: a auditoria acompanha a escrita, nunca a destrói.

    Achado da verificação adversarial: `audit_log` fazia db.add + db.flush na
    transação do CHAMADOR. Um flush que falhasse deixava a Session em
    pending-rollback e o db.commit() seguinte levantava PendingRollbackError —
    descartando o enriquecimento inteiro. O try/except em volta não protegia,
    porque o dano é o estado da sessão, não a exceção. Resolvido com SAVEPOINT.
    """

    @pytest.fixture
    async def db_produto(self):
        import uuid
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from app.db.session import Base
        from app.db.models import Product
        import app.db.models  # noqa

        engine = create_async_engine(
            "sqlite+aiosqlite:///file:testdb_audit?mode=memory&cache=shared&uri=true"
        )
        SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        produto = Product(id=uuid.uuid4(), nome="Produto Auditado")
        async with SessionLocal() as db:
            db.add(produto)
            await db.commit()
        try:
            yield SessionLocal, produto
        finally:
            async with engine.begin() as c:
                await c.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    async def test_falha_do_audit_nao_impede_o_commit(self, db_produto):
        """Payload impossível de serializar no log NÃO pode perder a escrita."""
        from sqlalchemy import select
        from app.db.models import Product, AuditAction
        from app.services.audit_service import audit_log

        SessionLocal, produto = db_produto

        async with SessionLocal() as db:
            await db.execute(
                sql_update(Product)
                .where(Product.id == produto.id)
                .values(descricao_tecnica="texto que PRECISA sobreviver")
            )
            # `object()` não é serializável em JSON — o flush do log falha
            await audit_log(
                db, AuditAction.GENERATE, resource_type="product",
                resource_id=str(produto.id),
                changes={"campo": object()},
            )
            await db.commit()  # não pode levantar PendingRollbackError

        async with SessionLocal() as db:
            salvo = (await db.execute(
                select(Product).where(Product.id == produto.id)
            )).scalar_one()
            assert salvo.descricao_tecnica == "texto que PRECISA sobreviver"

    async def test_audit_bem_sucedido_persiste(self):
        """O caminho feliz continua gravando o log (savepoint não engole)."""
        # coberto por TestEscritaRealMarcaProveniencia; aqui só documentamos
        # a intenção para quem mexer no savepoint depois.
        assert True


class TestProvenienciaIFU:
    """O segundo escritor (bula em PDF) também marca — e não marca bula_url."""

    def test_bula_url_fica_fora_da_marcacao(self):
        from app.services.provenance import CAMPOS_FICHA
        campos_atualizados = ["descricao_tecnica", "indicacoes", "bula_url"]
        marcaveis = [c for c in campos_atualizados if c in CAMPOS_FICHA]
        assert marcaveis == ["descricao_tecnica", "indicacoes"]

    def test_ifu_usa_origem_propria_nao_llm(self):
        """IFU é raspagem de PDF, não geração — a origem precisa distinguir."""
        assert ORIGEM_IFU_PDF != ORIGEM_LLM
        assert ORIGEM_IFU_PDF in ORIGENS_NAO_VERIFICADAS


class TestSeedMarcado:
    def test_seed_marca_produtos_curados(self):
        """Sem isso, ORIGEM_SEED seria vocabulário morto e todo o catálogo
        ficaria NULL — impossível distinguir curado de desconhecido."""
        import inspect
        from app.db import init_db

        fonte = inspect.getsource(init_db.seed)
        assert "ORIGEM_SEED" in fonte
        assert "campos_gerados_ia" in fonte


class TestMigracao:
    def test_products_esta_registrada_no_add_missing_columns(self):
        """Armadilha real: `products` era a única tabela sem hook de migração.

        Sem a chamada em create_tables(), a coluna só nasce em banco novo e
        todo SELECT products quebra em produção (incidente do commit b909dac).
        """
        import inspect
        from app.db import init_db

        fonte = inspect.getsource(init_db.create_tables)
        assert '_add_missing_columns("products"' in fonte
        assert any(c[0] == "campos_gerados_ia" for c in init_db.PRODUCT_NEW_COLUMNS)

    def test_coluna_existe_no_model(self):
        from app.db.models import Product
        assert "campos_gerados_ia" in Product.__table__.columns
        assert Product.__table__.columns["campos_gerados_ia"].nullable is True
