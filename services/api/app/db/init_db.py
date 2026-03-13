"""Cria tabelas e insere dados iniciais (seed)."""
import asyncio
import logging
from sqlalchemy import text
from app.db.session import engine, Base, AsyncSessionLocal
from app.db.models import (
    User, TussTerm, UserRole, Product, ReportTemplate,
    TussMaterial, RolVersion, DutVersion, RolProcedure, DutRule,
    AnvisaProduct, TissRule,
)
from app.core.security import get_password_hash

logger = logging.getLogger(__name__)

REPORT_NEW_COLUMNS = [
    ("rol_version_id", "VARCHAR(36)"),
    ("dut_version_id", "VARCHAR(36)"),
    ("tuss_version", "VARCHAR(20)"),
    ("approval_score", "FLOAT"),
    ("approval_score_details", "JSON"),
    ("compliance_mode", "VARCHAR(50)"),
]

CLINICAL_EVIDENCE_NEW_COLUMNS = [
    ("doi", "VARCHAR(255)"),
]


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.begin() as conn:
        for col_name, col_type in REPORT_NEW_COLUMNS:
            try:
                await conn.execute(text(
                    f"ALTER TABLE reports ADD COLUMN {col_name} {col_type}"
                ))
                logger.info("Added column reports.%s", col_name)
            except Exception:
                pass

    async with engine.begin() as conn:
        for col_name, col_type in CLINICAL_EVIDENCE_NEW_COLUMNS:
            try:
                await conn.execute(text(
                    f"ALTER TABLE clinical_evidences ADD COLUMN {col_name} {col_type}"
                ))
                logger.info("Added column clinical_evidences.%s", col_name)
            except Exception:
                pass


PRODUCTS_SEED = [
    {
        "nome": "Adhesion STP+",
        "linha": "Adhesion",
        "descricao_tecnica": (
            "Barreira anti-aderência biorreabsorvível composta por carboximetilcelulose sódica (CMC) "
            "e ácido hialurônico. Forma uma barreira física temporária entre superfícies teciduais "
            "traumatizadas, prevenindo a formação de aderências pós-cirúrgicas."
        ),
        "diferenciais_clinicos": (
            "Prevenção de aderências pós-cirúrgicas com eficácia comprovada em cirurgias abdominais, "
            "pélvicas e ortopédicas. Biorreabsorvível em 7 dias. Não interfere no processo cicatricial. "
            "Reduz necessidade de reoperação por aderência em até 50%."
        ),
        "indicacoes": (
            "Cirurgias abdominais (laparotomias), cirurgias pélvicas, artroplastias, "
            "laminectomias, tenólises, cirurgias ginecológicas."
        ),
        "contraindicacoes": "Hipersensibilidade aos componentes. Infecção ativa no sítio cirúrgico.",
        "viscosidade": "10.000 - 29.000 mPa.s",
        "peso_molecular": "Não aplicável (barreira anti-aderência)",
        "concentracao": "CMC sódica + ácido hialurônico em proporção proprietária",
        "registro_anvisa": "80117900XXX",
        "codigo_tuss_sugerido": "30715016",
        "bula_url": "https://consultas.anvisa.gov.br/#/medicamentos/",
        "referencias_bibliograficas": [
            "Diamond MP, et al. Reduction of adhesions after uterine myomectomy by Seprafilm membrane. Fertil Steril. 1996;66(6):904-10.",
            "Becker JM, et al. Prevention of postoperative abdominal adhesions by a sodium hyaluronate-based bioresorbable membrane. J Am Coll Surg. 1996;183(4):297-306.",
            "Dahl JB, et al. Prevention of adhesions in abdominal surgery. Lancet. 2005;365:1187-8.",
        ],
    },
    {
        "nome": "Kit EC2 - Linha Opus",
        "linha": "Opus",
        "descricao_tecnica": (
            "Sistema de viscossuplementação à base de ácido hialurônico de alto peso molecular, "
            "produzido por fermentação bacteriana (Streptococcus equi). Solução viscoelástica "
            "estéril para injeção intra-articular."
        ),
        "diferenciais_clinicos": (
            "Restauração da viscoelasticidade do líquido sinovial. Alívio prolongado de dor em "
            "osteoartrite de joelho. Alto peso molecular (6.000 kDa) proporciona maior tempo de "
            "permanência articular. Aplicação única."
        ),
        "indicacoes": (
            "Osteoartrite de joelho (graus II e III de Kellgren-Lawrence). Tratamento sintomático "
            "de dor articular quando medidas conservadoras falharam."
        ),
        "contraindicacoes": (
            "Infecção articular ativa. Hipersensibilidade a ácido hialurônico. "
            "Distúrbios de coagulação não controlados."
        ),
        "viscosidade": "80.000 - 120.000 mPa.s",
        "peso_molecular": "6.000 kDa",
        "concentracao": "10 mg/mL de hialuronato de sódio",
        "registro_anvisa": "80117900YYY",
        "codigo_tuss_sugerido": "20104120",
        "bula_url": "https://consultas.anvisa.gov.br/#/medicamentos/",
        "referencias_bibliograficas": [
            "Altman RD, et al. Hyaluronic acid injections for knee osteoarthritis. Semin Arthritis Rheum. 2015;45(2):140-9.",
            "Bellamy N, et al. Viscosupplementation for the treatment of osteoarthritis of the knee. Cochrane Database Syst Rev. 2006;(2):CD005321.",
            "Bannuru RR, et al. Therapeutic trajectory of hyaluronic acid versus corticosteroids. Arthritis Rheum. 2009;61(12):1704-11.",
        ],
    },
    {
        "nome": "Parafuso de Interferência Bioabsorvível",
        "linha": "Opus Fix",
        "descricao_tecnica": (
            "Parafuso de interferência fabricado em PLLA (ácido poli-L-láctico) para fixação de "
            "enxertos em reconstruções ligamentares. Bioabsorvível em 24-48 meses."
        ),
        "diferenciais_clinicos": (
            "Fixação segura de enxertos tendíneos em túnel ósseo. Elimina necessidade de remoção "
            "posterior (bioabsorvível). Não gera artefato em ressonância magnética. "
            "Osteointegração progressiva."
        ),
        "indicacoes": (
            "Reconstrução de LCA (ligamento cruzado anterior). Reconstrução de LCP. "
            "Reparos de menisco. Fixação de tendões."
        ),
        "contraindicacoes": "Infecção ativa. Qualidade óssea inadequada (osteoporose severa).",
        "viscosidade": "Não aplicável (dispositivo sólido)",
        "peso_molecular": "Não aplicável (polímero PLLA)",
        "concentracao": "Não aplicável",
        "registro_anvisa": "80117900ZZZ",
        "codigo_tuss_sugerido": "30727049",
        "bula_url": "https://consultas.anvisa.gov.br/#/medicamentos/",
        "referencias_bibliograficas": [
            "Drogset JO, et al. Bioabsorbable vs metallic interference screws for ACL reconstruction. Am J Sports Med. 2006;34(8):1333-8.",
            "Konan S, Haddad FS. A clinical review of bioabsorbable interference screws. J Bone Joint Surg Br. 2009;91(5):574-80.",
        ],
    },
    {
        "nome": "Tela de Polipropileno Macroporosa",
        "linha": "Opus Mesh",
        "descricao_tecnica": (
            "Tela cirúrgica de polipropileno monofilamentar, macroporosa (poro > 75 μm), "
            "para reforço de tecidos moles em herniorrafias. Peso leve (< 50 g/m²)."
        ),
        "diferenciais_clinicos": (
            "Macroporosidade permite melhor integração tecidual e menor resposta inflamatória. "
            "Peso leve reduz sensação de corpo estranho. Resistência mecânica adequada para "
            "reparos inguinais, incisionais e paraestomais."
        ),
        "indicacoes": "Herniorrafias inguinais, incisionais, umbilicais e paraestomais.",
        "contraindicacoes": "Infecção ativa no sítio de implante. Contato direto com vísceras (sem peritoneização).",
        "viscosidade": "Não aplicável (dispositivo sólido)",
        "peso_molecular": "Não aplicável",
        "concentracao": "Não aplicável",
        "registro_anvisa": "80117900WWW",
        "codigo_tuss_sugerido": "30604020",
        "bula_url": "https://consultas.anvisa.gov.br/#/medicamentos/",
        "referencias_bibliograficas": [
            "Lichtenstein IL, et al. The tension-free hernioplasty. Am J Surg. 1989;157(2):188-93.",
            "EU Hernia Trialists Collaboration. Mesh compared with non-mesh methods. Br J Surg. 2000;87(7):854-9.",
        ],
    },
]

TEMPLATES_SEED = [
    {
        "nome": "Template Adhesion STP+ - Cirurgia Abdominal",
        "especialidade": "Cirurgia Geral",
        "produto_nome": "Adhesion STP+",
        "tom_de_voz": (
            "Tom científico, formal e assertivo. Texto corrido (não em tópicos). "
            "Integrar patologia do paciente com diferenciais físico-químicos do material. "
            "Referenciar literatura como parte natural do texto."
        ),
        "template_corpo": (
            "O paciente {paciente_nome}, portador de {diagnostico} (CID {cid}), será submetido "
            "a {procedimento}, procedimento que envolve extensa manipulação de tecidos abdominais "
            "com elevado risco de formação de aderências pós-operatórias. A literatura demonstra que "
            "aderências ocorrem em até 93% dos pacientes submetidos a cirurgias abdominais abertas "
            "(Diamond, 1996), podendo resultar em obstrução intestinal, dor crônica e infertilidade.\n\n"
            "Para prevenção desta complicação, solicita-se a utilização de {produto}, barreira "
            "anti-aderência biorreabsorvível cuja eficácia é amplamente documentada na literatura "
            "científica. O produto atua como barreira física temporária entre superfícies peritoneais "
            "traumatizadas, sendo completamente reabsorvido em aproximadamente 7 dias.\n\n"
            "Ressalta-se que o paciente já apresentou {falha_terapeutica}, o que reforça a necessidade "
            "de medidas preventivas adicionais. A não utilização do material implica em {risco_nao_realizacao}.\n\n"
            "Conforme a RN 395 da ANS, em caso de divergência quanto à indicação do material, a operadora "
            "deverá apresentar justificativa técnica por escrito, fundamentada em evidências científicas."
        ),
        "bases_legais": ["RN 395", "RN 424", "RN 428", "RN 465"],
        "referencias_padrao": [
            "Diamond MP, et al. Fertil Steril. 1996;66(6):904-10.",
            "Becker JM, et al. J Am Coll Surg. 1996;183(4):297-306.",
            "Dahl JB, et al. Lancet. 2005;365:1187-8.",
        ],
        "exemplos_aprovados": [
            "Paciente Maria S., 52 anos, portadora de bridas peritoneais recidivantes (CID K66.0), será submetida a lise de aderências por videolaparoscopia. Trata-se de paciente com histórico de três cirurgias abdominais prévias, com quadro de obstrução intestinal parcial recorrente atribuída à formação de aderências pós-operatórias. A literatura demonstra que aderências peritoneais ocorrem em até 93% dos pacientes submetidos a cirurgias abdominais abertas (Diamond, 1996). Para prevenção de recidiva, solicita-se a utilização de Adhesion STP+, barreira anti-aderência biorreabsorvível composta por CMC sódica e ácido hialurônico, com viscosidade de 10.000 a 29.000 mPa.s, cuja eficácia na redução de aderências pós-cirúrgicas é comprovada em ensaios clínicos randomizados (Becker et al., 1996). Conforme a RN 395 da ANS, em caso de divergência quanto à indicação do material, a operadora deverá apresentar justificativa técnica por escrito, fundamentada em evidências científicas.",
            "O paciente João P., 68 anos, será submetido a colectomia direita por neoplasia de cólon (CID C18.2). Devido ao extenso campo operatório e manipulação de alças intestinais, há elevado risco de formação de aderências que podem resultar em obstrução intestinal pós-operatória. Solicita-se Adhesion STP+ para interposição entre superfícies peritoneais traumatizadas. O produto é biorreabsorvível em 7 dias e não interfere no processo cicatricial, conforme demonstrado por Dahl et al. (Lancet, 2005).",
        ],
    },
    {
        "nome": "Template Viscossuplementação - Ortopedia",
        "especialidade": "Ortopedia",
        "produto_nome": "Kit EC2 - Linha Opus",
        "tom_de_voz": (
            "Tom científico, formal e assertivo. Demonstrar progressão da doença e falha "
            "de tratamentos conservadores. Justificar superioridade do alto peso molecular."
        ),
        "template_corpo": (
            "O paciente {paciente_nome}, com diagnóstico de {diagnostico} (CID {cid}), apresenta "
            "quadro clínico compatível com osteoartrite de joelho, classificada como grau {grau_kl} "
            "pela escala de Kellgren-Lawrence, com dor articular significativa e limitação funcional "
            "que compromete as atividades diárias.\n\n"
            "Após insucesso com tratamento conservador ({falha_terapeutica}), indica-se a "
            "viscossuplementação com {produto}, ácido hialurônico de alto peso molecular (6.000 kDa) "
            "que restaura as propriedades viscoelásticas do líquido sinovial. A meta-análise de "
            "Altman et al. (2015) demonstrou eficácia superior da viscossuplementação com ácido "
            "hialurônico de alto peso molecular em comparação a formulações de menor peso molecular.\n\n"
            "A não realização do procedimento implica em {risco_nao_realizacao}, podendo evoluir para "
            "necessidade de procedimento cirúrgico de maior porte (artroplastia).\n\n"
            "Conforme a RN 395 da ANS, em caso de divergência quanto à indicação do material, a operadora "
            "deverá apresentar justificativa técnica por escrito, fundamentada em evidências científicas."
        ),
        "bases_legais": ["RN 395", "RN 424", "RN 465"],
        "referencias_padrao": [
            "Altman RD, et al. Semin Arthritis Rheum. 2015;45(2):140-9.",
            "Bellamy N, et al. Cochrane Database Syst Rev. 2006;(2):CD005321.",
            "Bannuru RR, et al. Arthritis Rheum. 2009;61(12):1704-11.",
        ],
        "exemplos_aprovados": [
            "Paciente Ana C., 62 anos, com diagnóstico de gonartrose bilateral (CID M17.0), grau III de Kellgren-Lawrence, apresenta dor articular crônica com limitação funcional significativa. Após insucesso com tratamento conservador incluindo analgésicos, anti-inflamatórios não esteroidais por 6 meses e programa de fisioterapia sem ganho de amplitude de movimento, indica-se viscossuplementação com Kit EC2 - Linha Opus, ácido hialurônico de alto peso molecular (6.000 kDa) e concentração de 10 mg/mL. A meta-análise de Altman et al. (2015) demonstrou eficácia superior da viscossuplementação com ácido hialurônico de alto peso molecular. A não realização do procedimento implica em progressão da degeneração articular com perda funcional irreversível, podendo evoluir para necessidade de artroplastia total. Conforme a RN 395 da ANS, em caso de divergência, a operadora deverá apresentar justificativa técnica por escrito.",
        ],
    },
]


TISS_RULES_SEED = [
    # Guia SP/SADT — materiais OPME vão no campo Mat/Med
    {
        "tipo_guia": "SP/SADT",
        "campo": "Mat/Med",
        "regra": "permitido",
        "tabela_tuss_aplicavel": "19",
        "descricao": "Materiais OPME (Tabela 19) devem ser solicitados no campo Materiais/Medicamentos da guia SP/SADT.",
        "versao_tiss": "4.01.00",
    },
    {
        "tipo_guia": "SP/SADT",
        "campo": "Procedimento",
        "regra": "permitido",
        "tabela_tuss_aplicavel": "22",
        "descricao": "Procedimentos (Tabela 22) devem ser informados no campo Procedimento da guia SP/SADT.",
        "versao_tiss": "4.01.00",
    },
    {
        "tipo_guia": "SP/SADT",
        "campo": "Honorarios",
        "regra": "proibido",
        "tabela_tuss_aplicavel": "19",
        "descricao": "GLOSA: Materiais OPME (Tabela 19) NÃO podem ser lançados como Honorários. Devem ir no Anexo OPME ou Mat/Med.",
        "versao_tiss": "4.01.00",
    },
    # Guia de Internação — materiais OPME vão no anexo OPME
    {
        "tipo_guia": "Internação",
        "campo": "OPME",
        "regra": "permitido",
        "tabela_tuss_aplicavel": "19",
        "descricao": "Materiais OPME (Tabela 19) devem ser solicitados no Anexo de OPME da guia de Internação.",
        "versao_tiss": "4.01.00",
    },
    {
        "tipo_guia": "Internação",
        "campo": "Procedimento",
        "regra": "permitido",
        "tabela_tuss_aplicavel": "22",
        "descricao": "Procedimentos (Tabela 22) devem ser informados no campo Procedimento da guia de Internação.",
        "versao_tiss": "4.01.00",
    },
    {
        "tipo_guia": "Internação",
        "campo": "Honorarios",
        "regra": "proibido",
        "tabela_tuss_aplicavel": "19",
        "descricao": "GLOSA: Materiais OPME (Tabela 19) NÃO podem ser lançados como Honorários em guia de Internação.",
        "versao_tiss": "4.01.00",
    },
    {
        "tipo_guia": "Internação",
        "campo": "Mat/Med",
        "regra": "permitido",
        "tabela_tuss_aplicavel": "19",
        "descricao": "Materiais OPME (Tabela 19) podem ser lançados no campo Mat/Med da guia de Internação.",
        "versao_tiss": "4.01.00",
    },
    # Guia de Honorário Individual — OPME proibido
    {
        "tipo_guia": "Honorário Individual",
        "campo": "Honorarios",
        "regra": "proibido",
        "tabela_tuss_aplicavel": "19",
        "descricao": "GLOSA: Guia de Honorário Individual NÃO pode conter materiais OPME (Tabela 19).",
        "versao_tiss": "4.01.00",
    },
    # Solicitação de OPME — campo correto
    {
        "tipo_guia": "Solicitação OPME",
        "campo": "OPME",
        "regra": "obrigatorio",
        "tabela_tuss_aplicavel": "19",
        "descricao": "Materiais OPME (Tabela 19) são OBRIGATÓRIOS neste formulário de Solicitação de OPME.",
        "versao_tiss": "4.01.00",
    },
]


async def seed():
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select

        r = await db.execute(select(User).where(User.email == "medico@opme.com"))
        if r.scalar_one_or_none():
            return

        user = User(
            email="medico@opme.com",
            hashed_password=get_password_hash("senha123"),
            role=UserRole.medico,
            consent_accepted=False,
        )
        db.add(user)
        await db.flush()

        for code, term in [
            ("30701020", "Radiografia de tórax"),
            ("30901047", "Artroplastia total de joelho"),
            ("30901055", "Artroplastia total de quadril"),
            ("31001010", "Prótese de quadril"),
            ("31001029", "Prótese de joelho"),
            ("30715016", "Implante de barreira anti-aderência"),
            ("20104120", "Viscossuplementação articular"),
            ("30727049", "Reconstrução de ligamento cruzado anterior"),
            ("30604020", "Herniorrafia com tela"),
        ]:
            t = TussTerm(code=code, term=term, table_source="procedimentos")
            db.add(t)

        product_map = {}
        for pdata in PRODUCTS_SEED:
            p = Product(**pdata)
            db.add(p)
            await db.flush()
            product_map[pdata["nome"]] = p.id

        for tdata in TEMPLATES_SEED:
            produto_nome = tdata.pop("produto_nome")
            t = ReportTemplate(
                produto_id=product_map.get(produto_nome),
                **tdata,
            )
            db.add(t)

        for rdata in TISS_RULES_SEED:
            db.add(TissRule(**rdata))

        await db.commit()


async def main():
    await create_tables()
    await seed()
    print("DB initialized and seeded.")


if __name__ == "__main__":
    asyncio.run(main())
