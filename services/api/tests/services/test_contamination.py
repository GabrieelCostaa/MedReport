"""Tests for contamination detector."""
import pytest
from unittest.mock import MagicMock
from app.services.contamination_detector import (
    check_contamination,
    detect_language_contamination,
    detect_training_leakage,
    check_cross_product_contamination,
    build_fingerprint,
)


def _make_product(name, anvisa, **kwargs):
    p = MagicMock()
    p.id = name.lower().replace(" ", "-")
    p.nome = name
    p.registro_anvisa = anvisa
    p.peso_molecular = kwargs.get("peso_molecular", "")
    p.viscosidade = kwargs.get("viscosidade", "")
    p.concentracao = kwargs.get("concentracao", "")
    p.diferenciais_clinicos = kwargs.get("diferenciais", "")
    return p


class TestCrossProductContamination:
    def test_clean_text(self):
        synvisc = _make_product("Synvisc-One", "80030810056")
        seprafilm = _make_product("Seprafilm", "80030810099")
        text = "Viscossuplementação com Synvisc-One. ANVISA 80030810056."
        fp_current = build_fingerprint(synvisc)
        fp_all = [build_fingerprint(synvisc), build_fingerprint(seprafilm)]
        issues = check_cross_product_contamination(text, fp_current, fp_all)
        assert len(issues) == 0

    def test_wrong_product_name(self):
        synvisc = _make_product("Synvisc-One", "80030810056")
        seprafilm = _make_product("Seprafilm", "80030810099")
        text = "Indica-se Seprafilm para viscossuplementação articular."
        fp_current = build_fingerprint(synvisc)
        fp_all = [build_fingerprint(synvisc), build_fingerprint(seprafilm)]
        issues = check_cross_product_contamination(text, fp_current, fp_all)
        blocking = [i for i in issues if i.severidade == "bloqueante"]
        assert len(blocking) >= 1

    def test_wrong_anvisa(self):
        synvisc = _make_product("Synvisc-One", "80030810056")
        seprafilm = _make_product("Seprafilm", "80030810099")
        text = "Registro ANVISA 80030810099 do produto articular."
        fp_current = build_fingerprint(synvisc)
        fp_all = [build_fingerprint(synvisc), build_fingerprint(seprafilm)]
        issues = check_cross_product_contamination(text, fp_current, fp_all)
        assert any(i.tipo == "fingerprint" for i in issues)


class TestLanguageContamination:
    def test_clean_portuguese(self):
        text = "Paciente apresenta diagnóstico de gonartrose bilateral."
        issues = detect_language_contamination(text)
        assert len(issues) == 0

    def test_english_phrase_detected(self):
        text = "The patient presents with bilateral knee osteoarthritis and furthermore needs surgery."
        issues = detect_language_contamination(text)
        assert any(i.tipo == "language" for i in issues)

    def test_acceptable_english_terms(self):
        text = "Estudo follow-up de 12 meses demonstrou que o scaffold cross-linked manteve integridade in vivo."
        issues = detect_language_contamination(text)
        # Regex-based issues only (acceptable terms should not trigger)
        blocking = [i for i in issues if i.severidade == "bloqueante"]
        assert len(blocking) == 0


class TestTrainingLeakage:
    def test_ai_disclosure(self):
        text = "As an AI language model, I cannot provide medical advice."
        issues = detect_training_leakage(text)
        assert any(i.severidade == "bloqueante" for i in issues)

    def test_model_name_leak(self):
        text = "Conforme recomendação do ChatGPT, o tratamento indicado é..."
        issues = detect_training_leakage(text)
        assert any(i.tipo == "training_leak" for i in issues)

    def test_clean_medical_text(self):
        text = "Conforme meta-análise de Altman et al. (2015), a viscossuplementação demonstrou superioridade."
        issues = detect_training_leakage(text)
        assert len(issues) == 0


class TestFullContaminationCheck:
    def test_full_clean_report(self):
        product = _make_product("Synvisc-One", "80030810056")
        text = "Paciente com gonartrose CID M17.0. Indica-se Synvisc-One. ANVISA 80030810056."
        result = check_contamination(text, product)
        assert result.clean

    def test_full_contaminated_report(self):
        synvisc = _make_product("Synvisc-One", "80030810056")
        seprafilm = _make_product("Seprafilm", "80030810099")
        text = (
            "Indica-se Seprafilm para o joelho. "
            "The patient should receive treatment. "
            "As an AI model, recomendo este produto."
        )
        result = check_contamination(text, synvisc, [synvisc, seprafilm])
        assert not result.clean
        assert len(result.issues) >= 2  # cross-product + training leak

    def test_all_products_enables_cross_product_detection(self):
        """Regressão: sem all_products a detecção cross-produto fica desligada;
        com all_products (caminho novo do pipeline) ela é ativada."""
        synvisc = _make_product("Synvisc-One", "80030810056")
        seprafilm = _make_product("Seprafilm", "80030810099")
        text = "Indica-se Seprafilm para viscossuplementação do joelho."

        sem = check_contamination(text, synvisc)  # all_products=None
        com = check_contamination(text, synvisc, [synvisc, seprafilm])

        _cross = {"cross_product", "fingerprint"}
        cross_sem = [i for i in sem.issues if i.tipo in _cross]
        cross_com = [i for i in com.issues if i.tipo in _cross]
        assert len(cross_sem) == 0
        assert len(cross_com) >= 1


# ── Regressões do PR3: determinismo + falsos positivos ────────────────────

class TestFalsosPositivosDeNome:
    """Match por substring bloqueava laudo legítimo de família de produtos."""

    def test_familia_de_produtos_nao_e_contaminacao(self):
        # Gerar o laudo de "Synvisc-One" cita o nome, que CONTÉM "Synvisc".
        # Antes: bloqueante acusando contaminação pelo produto irmão.
        synvisc_one = _make_product("Synvisc-One", "80030810056")
        synvisc = _make_product("Synvisc", "80030810011")
        text = "Viscossuplementação com Synvisc-One conforme prescrito."
        issues = check_cross_product_contamination(
            text, build_fingerprint(synvisc_one), [build_fingerprint(synvisc)],
        )
        assert [i for i in issues if i.severidade == "bloqueante"] == []

    def test_nome_alheio_de_verdade_ainda_bloqueia(self):
        """A correção não pode cegar o detector para contaminação real."""
        synvisc = _make_product("Synvisc-One", "80030810056")
        seprafilm = _make_product("Seprafilm", "80030810099")
        text = "Barreira anti-aderência Seprafilm aplicada."
        issues = check_cross_product_contamination(
            text, build_fingerprint(synvisc), [build_fingerprint(seprafilm)],
        )
        assert any(i.severidade == "bloqueante" for i in issues)

    def test_nome_como_parte_de_outra_palavra_nao_dispara(self):
        atual = _make_product("Produto A", "80030810056")
        outro = _make_product("Vita", "80030810099")
        text = "O paciente apresenta perda de vitalidade e vitamina D baixa."
        issues = check_cross_product_contamination(
            text, build_fingerprint(atual), [build_fingerprint(outro)],
        )
        assert issues == []


class TestFalsosPositivosDeRegistro:
    def test_colisao_por_concatenacao_de_digitos_nao_dispara(self):
        """O texto inteiro virava uma sopa de dígitos: datas, CIDs e
        quantidades colavam e casavam com registro alheio por substring."""
        atual = _make_product("Produto A", "11112222")
        outro = _make_product("Produto B", "22223333")
        # "1111 2222 3333" concatenado vira "111122223333", que CONTÉM
        # "22223333" — o registro do outro produto.
        text = "Foram usadas 1111 unidades em 2222 e 3333 aplicações."
        issues = check_cross_product_contamination(
            text, build_fingerprint(atual), [build_fingerprint(outro)],
        )
        assert [i for i in issues if i.tipo == "fingerprint"] == []

    def test_registro_alheio_citado_de_verdade_bloqueia(self):
        atual = _make_product("Produto A", "80030810056")
        outro = _make_product("Produto B", "80030810099")
        text = "Material com registro ANVISA 80030810099."
        issues = check_cross_product_contamination(
            text, build_fingerprint(atual), [build_fingerprint(outro)],
        )
        assert any(i.tipo == "fingerprint" for i in issues)

    def test_produtos_que_compartilham_registro_nao_se_acusam(self):
        """Variantes da mesma linha dividem registro — citá-lo é correto."""
        a = _make_product("Linha X 10ml", "80030810056")
        b = _make_product("Linha X 20ml", "80030810056")
        text = "Registro ANVISA 80030810056 conforme bula."
        issues = check_cross_product_contamination(
            text, build_fingerprint(a), [build_fingerprint(b)],
        )
        assert [i for i in issues if i.tipo == "fingerprint"] == []


class TestSemCircularidade:
    def test_campo_gerado_por_ia_nao_entra_no_fingerprint(self):
        """diferenciais_clinicos pode ter sido escrito pelo LLM — usá-lo como
        impressão digital fazia o detector de IA ser alimentado por IA."""
        p = _make_product("Produto A", "80030810056", diferenciais="reticulação polimérica tridimensional")
        fp = build_fingerprint(p)
        assert not hasattr(fp, "unique_terms")
        assert "reticulação" not in str(fp)

    def test_campos_mortos_removidos(self):
        """peso_molecular/viscosidade/concentracao eram gravados e nunca lidos."""
        fp = build_fingerprint(_make_product("Produto A", "80030810056"))
        for morto in ("peso_molecular", "viscosidade", "concentracao"):
            assert not hasattr(fp, morto)


class TestDeterminismo:
    def test_mesma_entrada_mesmo_resultado(self):
        atual = _make_product("Produto A", "80030810056")
        outros = [_make_product(f"Produto {c}", f"8003081{i:04d}") for i, c in enumerate("BCDE")]
        text = "Uso de Produto C conforme indicado, registro 80030810001."
        fps = [build_fingerprint(p) for p in outros]
        r1 = check_cross_product_contamination(text, build_fingerprint(atual), fps)
        r2 = check_cross_product_contamination(text, build_fingerprint(atual), fps)
        assert [(i.tipo, i.trecho) for i in r1] == [(i.tipo, i.trecho) for i in r2]


class TestSemSkipDeFamilia:
    """Regressão: uma versão anterior deste PR tinha um "skip de família" por
    substring de nome. Ele era redundante (a fronteira de palavra já resolve)
    e desligava a comparação INTEIRA — nome e registro — do par."""

    def test_nome_curto_nao_cega_o_catalogo(self):
        # Produto cadastrado como "Kit" fazia todos os "Kit *" serem pulados.
        atual = _make_product("Kit", "80011110000")
        outros = [
            _make_product("Kit EC2 - Linha Opus", "80022220000"),
            _make_product("Kit FO - Laser Cirúrgico", "80033330000"),
        ]
        text = "Aplicado Kit EC2 - Linha Opus no paciente."
        issues = check_cross_product_contamination(
            text, build_fingerprint(atual), [build_fingerprint(p) for p in outros],
        )
        assert any(i.severidade == "bloqueante" for i in issues), \
            "nome alheio citado deve bloquear mesmo com nome atual curto"

    def test_registro_alheio_detectado_mesmo_com_nomes_parecidos(self):
        """O skip antigo engolia junto a checagem de registro ANVISA."""
        atual = _make_product("Linha X", "80011110000")
        outro = _make_product("Linha X Plus", "80022220000")
        text = "Material registro ANVISA 80022220000."
        issues = check_cross_product_contamination(
            text, build_fingerprint(atual), [build_fingerprint(outro)],
        )
        assert any(i.tipo == "fingerprint" for i in issues)


class TestRegistroFormatado:
    """O registro raramente aparece 'limpo' no laudo."""

    @pytest.mark.parametrize("escrito", [
        "80030810099",
        "80.030.810/099",
        "800 308 100 99",
        "registro 80030810099/2024 vigente",
        "80030810099.",
    ])
    def test_formatos_reais_sao_detectados(self, escrito):
        atual = _make_product("Produto A", "80011110000")
        outro = _make_product("Produto B", "80030810099")
        issues = check_cross_product_contamination(
            f"Material com {escrito} conforme bula.",
            build_fingerprint(atual), [build_fingerprint(outro)],
        )
        assert any(i.tipo == "fingerprint" for i in issues), f"não detectou: {escrito}"

    def test_registro_dentro_de_numero_maior_nao_dispara(self):
        """Não pode casar quando é apenas um pedaço de outro número."""
        atual = _make_product("Produto A", "80011110000")
        outro = _make_product("Produto B", "80030810099")
        issues = check_cross_product_contamination(
            "Código interno 9980030810099123 do lote.",
            build_fingerprint(atual), [build_fingerprint(outro)],
        )
        assert [i for i in issues if i.tipo == "fingerprint"] == []


class TestDeterminismoContraOBanco:
    """O não-determinismo real vinha da ORDEM do banco (limit sem ORDER BY),
    que um teste em memória não exercita. Este exercita.
    """

    async def test_ordem_do_catalogo_e_estavel_entre_execucoes(self):
        import uuid
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from app.db.session import Base
        from app.db.models import Product

        engine = create_async_engine(
            "sqlite+aiosqlite:///file:testdb_contam?mode=memory&cache=shared&uri=true"
        )
        SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        try:
            async with SessionLocal() as db:
                for i in range(30):
                    db.add(Product(
                        id=uuid.uuid4(), nome=f"Produto {i:02d}",
                        registro_anvisa=f"800{i:08d}",
                    ))
                await db.commit()

            # Exatamente a query do pipeline (projeção + ORDER BY + cap)
            async def _carrega():
                async with SessionLocal() as db:
                    return (await db.execute(
                        select(Product.id, Product.nome,
                               Product.registro_anvisa, Product.codigo_tuss_sugerido)
                        .order_by(Product.nome, Product.id)
                        .limit(10)
                    )).all()

            a, b = await _carrega(), await _carrega()
            assert [r.nome for r in a] == [r.nome for r in b]

            # E o fingerprint funciona com Row (a query projeta, não traz o ORM)
            fps = [build_fingerprint(r) for r in a]
            assert all(f.product_name for f in fps)
            r1 = check_cross_product_contamination("Uso de Produto 03.", fps[0], fps)
            r2 = check_cross_product_contamination("Uso de Produto 03.", fps[0], fps)
            assert [(i.tipo, i.trecho) for i in r1] == [(i.tipo, i.trecho) for i in r2]
            assert any(i.trecho == "Produto 03" for i in r1)
        finally:
            async with engine.begin() as c:
                await c.run_sync(Base.metadata.drop_all)
            await engine.dispose()
