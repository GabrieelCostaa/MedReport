"""Cria tabelas e insere dados iniciais (seed)."""
import asyncio
import logging
from sqlalchemy import text
from app.db.session import engine, Base, AsyncSessionLocal
from app.db.models import (
    User, TussTerm, UserRole, Product, ReportTemplate,
    TussMaterial, RolVersion, DutVersion, RolProcedure, DutRule,
    AnvisaProduct, TissRule, ProductTussMapping,
    GlosaMotivo, OperadoraGlosaIndicador,
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
    ("medico_nome", "VARCHAR(255)"),
    ("medico_crm", "VARCHAR(50)"),
    ("medico_crm_uf", "VARCHAR(2)"),
    ("signature_hash", "VARCHAR(64)"),
    ("pdf_signed_bytes", "BYTEA"),
    # Identificação anti-glosa (paciente/guia/materiais)
    ("paciente_dob", "VARCHAR(20)"),
    ("paciente_carteirinha", "VARCHAR(60)"),
    ("paciente_cpf", "VARCHAR(20)"),
    ("guia_numero", "VARCHAR(60)"),
    ("atendimento_numero", "VARCHAR(60)"),
    ("cids_secundarios", "JSON"),
    ("materiais_tuss", "JSON"),
    ("compliance_texto", "TEXT"),
    ("operadora_registro_ans", "VARCHAR(20)"),
]

USER_NEW_COLUMNS = [
    ("nome", "VARCHAR(255)"),
    ("crm", "VARCHAR(50)"),
    ("crm_uf", "VARCHAR(2)"),
    ("rqe", "VARCHAR(50)"),
    ("clinica_nome", "VARCHAR(255)"),
    ("clinica_logo_url", "VARCHAR(500)"),
]

CLINICAL_EVIDENCE_NEW_COLUMNS = [
    ("doi", "VARCHAR(255)"),
]

ANVISA_NEW_COLUMNS = [
    ("nome_tecnico", "VARCHAR(500)"),
    ("modelos_descricao", "TEXT"),
    ("search_normalized", "TEXT"),
]


async def _add_missing_columns(table: str, columns: list[tuple[str, str]]) -> None:
    """Adiciona colunas novas UMA POR TRANSAÇÃO.

    CRÍTICO: no Postgres, um ALTER que falha (coluna já existe) aborta a
    transação inteira — se todos os ALTERs compartilharem uma transação, o
    primeiro "já existe" envenena os seguintes e as colunas NOVAS nunca são
    criadas (o except engole tudo silenciosamente). Uma transação por coluna
    isola cada falha esperada.
    """
    for col_name, col_type in columns:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"
                ))
            logger.info("Added column %s.%s", table, col_name)
        except Exception:
            pass  # coluna já existe


async def _ensure_anvisa_search_index() -> None:
    """Índice pg_trgm para busca por substring rápida em anvisa_products (~111k linhas).

    Postgres-only: em SQLite/dev os comandos falham e são engolidos (a busca
    ainda funciona, só varre a tabela). Idempotente via IF NOT EXISTS.
    """
    stmts = [
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        "CREATE INDEX IF NOT EXISTS ix_anvisa_search_trgm "
        "ON anvisa_products USING gin (search_normalized gin_trgm_ops)",
    ]
    for stmt in stmts:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(stmt))
            logger.info("pg_trgm: %s", stmt.split(" ON ")[0][:40])
        except Exception:
            pass  # SQLite/dev ou extensão indisponível — busca funciona sem índice


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await _add_missing_columns("reports", REPORT_NEW_COLUMNS)
    await _add_missing_columns("clinical_evidences", CLINICAL_EVIDENCE_NEW_COLUMNS)
    await _add_missing_columns("users", USER_NEW_COLUMNS)
    await _add_missing_columns("anvisa_products", ANVISA_NEW_COLUMNS)
    await _ensure_anvisa_search_index()


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
        "registro_anvisa": "80030810132",
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
        "registro_anvisa": "80030810176",
        "codigo_tuss_sugerido": "30713137",
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
        "registro_anvisa": "80804050173",
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
        "registro_anvisa": "80145900901",
        "codigo_tuss_sugerido": "31009107",
        "bula_url": "https://consultas.anvisa.gov.br/#/medicamentos/",
        "referencias_bibliograficas": [
            "Lichtenstein IL, et al. The tension-free hernioplasty. Am J Surg. 1989;157(2):188-93.",
            "EU Hernia Trialists Collaboration. Mesh compared with non-mesh methods. Br J Surg. 2000;87(7):854-9.",
        ],
    },
    {
        "nome": "Biossilex - Biovidro",
        "linha": "Biossilex",
        "descricao_tecnica": (
            "Substituto ósseo sintético à base de biovidro (SiO2-CaO-Na2O-P2O5). "
            "Grânulos bioativos que promovem osteocondução e osteoestimulação por meio da "
            "liberação iônica controlada de cálcio, silício e fósforo na interface óssea."
        ),
        "diferenciais_clinicos": (
            "Biovidro com propriedade antibacteriana intrínseca: elevação de pH local inibe "
            "colonização bacteriana, ideal para cavidades pós-osteomielite. Osteocondução e "
            "osteoestimulação comprovadas. Reabsorção gradual com substituição por osso neoformado. "
            "Dispensa coleta de enxerto autólogo (elimina morbidade do sítio doador)."
        ),
        "indicacoes": (
            "Preenchimento de defeitos ósseos pós-osteomielite, pseudoartroses, artrodeses, "
            "tumores ósseos, fraturas complexas com perda de substância, reconstrução craniofacial."
        ),
        "contraindicacoes": "Infecção ativa não desbridada. Defeitos sem contenção óssea ou de tecidos moles.",
        "viscosidade": "Não aplicável (grânulos sólidos)",
        "peso_molecular": "Não aplicável",
        "concentracao": "Não aplicável (biovidro 100%)",
        "registro_anvisa": "80030810167",
        "codigo_tuss_sugerido": "30727154",
        "bula_url": "https://consultas.anvisa.gov.br/#/medicamentos/",
        "referencias_bibliograficas": [
            "Hench LL. The story of Bioglass. J Mater Sci Mater Med. 2006;17(11):967-78.",
            "Fernandes HR, et al. Bioactive glasses and glass-ceramics for healthcare applications. Int J Appl Glass Sci. 2018;9(2):174-190.",
            "Rahaman MN, et al. Bioactive glass in tissue engineering. Acta Biomater. 2011;7(6):2355-73.",
        ],
    },
    {
        "nome": "Vitagraft - Enxerto Bifásico",
        "linha": "Vitagraft",
        "descricao_tecnica": (
            "Substituto ósseo bifásico composto por hidroxiapatita (HA) e beta-tricálcio fosfato "
            "(β-TCP) na proporção 60:40. Grânulos porosos com macro e microporos interconectados "
            "que mimetizam a estrutura do osso esponjoso."
        ),
        "diferenciais_clinicos": (
            "Composição bifásica combina estabilidade estrutural da HA com reabsorção controlada "
            "do β-TCP, promovendo osteocondução progressiva. Porosidade interconectada favorece "
            "vascularização e migração celular. Elimina necessidade de enxerto autólogo e morbidade "
            "do sítio doador. Aplicável em defeitos ósseos de múltiplas localizações anatômicas."
        ),
        "indicacoes": (
            "Pseudoartroses, artrodeses (coluna, membros superiores e inferiores), defeitos ósseos "
            "pós-ressecção tumoral, reconstrução craniana e craniofacial, perda de substância óssea."
        ),
        "contraindicacoes": "Infecção ativa no sítio de implante. Defeitos sem vascularização adequada.",
        "viscosidade": "Não aplicável (grânulos sólidos)",
        "peso_molecular": "Não aplicável",
        "concentracao": "HA 60% / β-TCP 40%",
        "registro_anvisa": "80030810162",
        "codigo_tuss_sugerido": "30713048",
        "bula_url": "https://consultas.anvisa.gov.br/#/medicamentos/",
        "referencias_bibliograficas": [
            "Daculsi G, et al. Biphasic calcium phosphate concept applied to artificial bone, implant coating and injectable bone substitute. Biomaterials. 1998;19(16):1473-8.",
            "LeGeros RZ. Calcium phosphate-based osteoinductive materials. Chem Rev. 2008;108(11):4742-53.",
            "Ebrahimi M, et al. Biphasic calcium phosphates bioceramics: an overview. J Mater Sci Mater Med. 2017;28(1):6.",
        ],
    },
    {
        "nome": "Kit EC2 - Enxerto Composto",
        "linha": "EC2",
        "descricao_tecnica": (
            "Sistema para colheita, processamento e aplicação de enxerto composto de tecido "
            "celular subcutâneo autólogo contendo fração vascular estromal (SVF). Composto por "
            "cânulas de acesso e colheita, gel carreador para preservação do enxerto."
        ),
        "diferenciais_clinicos": (
            "Permite colheita e reimplantação de enxerto composto autólogo rico em células do "
            "estroma vascular (SVF) para promoção de vasculogênese e angiogênese. Gel carreador "
            "preserva viabilidade celular entre colheita e reimplantação. Modulação do processo "
            "inflamatório e cicatricial. Aplicação em urologia (Peyronie, disfunção erétil, "
            "estenose uretral) e medicina regenerativa."
        ),
        "indicacoes": (
            "Doença de Peyronie, disfunção erétil com componente vascular, estenose uretral, "
            "reparação de corpo cavernoso, aplicações em medicina regenerativa."
        ),
        "contraindicacoes": "Infecção ativa no sítio de colheita ou implante. Coagulopatia não controlada.",
        "viscosidade": "Não aplicável (kit cirúrgico)",
        "peso_molecular": "Não aplicável",
        "concentracao": "Não aplicável (enxerto autólogo)",
        "registro_anvisa": "80030810130",
        "codigo_tuss_sugerido": "30101310",
        "bula_url": "https://consultas.anvisa.gov.br/#/medicamentos/",
        "referencias_bibliograficas": [
            "Zuk PA, et al. Multilineage cells from human adipose tissue. Tissue Eng. 2001;7(2):211-28.",
            "Bourin P, et al. Stromal cells from the adipose tissue-derived stromal vascular fraction. Cytotherapy. 2013;15(6):641-8.",
            "Haack-Sørensen M, et al. Mesenchymal stromal cell therapy for ischemic heart disease. Nat Rev Cardiol. 2019;16:727-740.",
        ],
    },
    {
        "nome": "Kit FO - Laser Cirúrgico",
        "linha": "Laser Dual",
        "descricao_tecnica": (
            "Sistema de fibra óptica para acoplamento em fonte de laser cirúrgico (diodo ou CO2). "
            "Fibras descartáveis estéreis com ponteiras anguladas para acesso endoscópico em "
            "cavidades nasais, laríngeas e brônquicas."
        ),
        "diferenciais_clinicos": (
            "Fibra óptica flexível permite acesso minimamente invasivo a vias aéreas superiores e "
            "inferiores. Corte e coagulação simultâneos reduzem sangramento intraoperatório. "
            "Precisão micrométrica preserva tecidos adjacentes. Ponteiras descartáveis eliminam "
            "risco de contaminação cruzada. Compatível com endoscópios rígidos e flexíveis."
        ),
        "indicacoes": (
            "Turbinectomia/turbinoplastia, ressecção de papiloma laríngeo, adenoidectomia, "
            "uvulopalatofaringoplastia (SAHOS), desobstrução brônquica, exérese de tumores "
            "de vias aéreas, cauterização nasal, sinequiotomia."
        ),
        "contraindicacoes": "Uso próximo a materiais inflamáveis. Coagulopatia severa não corrigida.",
        "viscosidade": "Não aplicável (dispositivo óptico)",
        "peso_molecular": "Não aplicável",
        "concentracao": "Não aplicável",
        "registro_anvisa": "80030810086",
        "codigo_tuss_sugerido": "30501458",
        "bula_url": "https://consultas.anvisa.gov.br/#/medicamentos/",
        "referencias_bibliograficas": [
            "Shapshay SM, et al. Laser surgery for laryngeal and pharyngeal disorders. Otolaryngol Clin North Am. 1996;29(6):941-54.",
            "Remacle M, et al. Laser-assisted surgery of the upper aero-digestive tract. Eur Arch Otorhinolaryngol. 2008;265(6):609-15.",
            "Janda P, et al. Diode laser treatment of hyperplasia of the inferior nasal turbinates. Lasers Surg Med. 2001;28(5):404-13.",
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


# ============================================================================
# Mapeamento Produto → TUSS (fonte: documentos oficiais Hugo/Rastriall)
# ============================================================================
PRODUCT_TUSS_MAPPINGS_SEED = {
    "Adhesion STP+": [
        {"tuss_code": "31307051", "procedure_name": "Aplicação de membranas antiaderentes", "subgroup": "Cirurgia Geral", "applications": "Cirurgias abdominais, peritoneais, aplicação de barreira anti-aderência, prevenção de aderências", "is_primary": True},
        {"tuss_code": "31009174", "procedure_name": "Laparotomia exploradora para liberação de bridas", "subgroup": "Cirurgia Geral", "applications": "Laparotomia, biópsia, drenagem de abscesso, liberação de bridas, oclusão intestinal"},
        {"tuss_code": "31009352", "procedure_name": "Videolaparoscopia para liberação de bridas/aderências", "subgroup": "Cirurgia Geral", "applications": "Videolaparoscopia, diagnóstico, biópsia, drenagem, liberação de bridas e aderências, rafias"},
        {"tuss_code": "31307078", "procedure_name": "Liberação de aderências pélvicas", "subgroup": "Ginecologia", "applications": "Aderências pélvicas, ressecção de cistos peritoneais, salpingólise, ginecologia"},
        {"tuss_code": "31303170", "procedure_name": "Lise de sinéquias uterinas", "subgroup": "Ginecologia", "applications": "Sinéquias uterinas, lise, ginecologia"},
        {"tuss_code": "30914116", "procedure_name": "Marsupialização de linfocele", "subgroup": "Urologia/Nefrologia", "applications": "Sistema linfático, nefrectomia, linfocele"},
        {"tuss_code": "30915040", "procedure_name": "Pericardiectomia", "subgroup": "Cirurgia Cardiovascular", "applications": "Pericárdio, pericardiectomia, sistema cardiocirculatório"},
        {"tuss_code": "82000468", "procedure_name": "Controle de hemorragia com agente hemostático", "subgroup": "Bucomaxilofacial", "applications": "Cabeça e pescoço, maxilofacial, hemostasia, hemorragia"},
        {"tuss_code": "82001545", "procedure_name": "Bridectomia/Bridotomia", "subgroup": "Cirurgia Plástica", "applications": "Bridas constritivas, cabeça e pescoço, bridectomia"},
        {"tuss_code": "30722179", "procedure_name": "Bridas congênitas - tratamento cirúrgico", "subgroup": "Ortopedia", "applications": "Bridas congênitas, sistema musculoesquelético"},
        {"tuss_code": "30101824", "procedure_name": "Tratamento cirúrgico de bridas constritivas", "subgroup": "Cirurgia Plástica", "applications": "Pele, tecido celular subcutâneo, bridas constritivas"},
        {"tuss_code": "31403360", "procedure_name": "Tratamento cirúrgico das neuropatias compressivas", "subgroup": "Neurocirurgia", "applications": "Sistema nervoso, neuropatias compressivas, neurocirurgia"},
        {"tuss_code": "30733030", "procedure_name": "Artroscopia para aderências", "subgroup": "Ortopedia", "applications": "Artroscopia, infecção, corpos estranhos, sinovectomia, aderências, desbridamento"},
    ],
    "Biossilex - Biovidro": [
        {"tuss_code": "30727154", "procedure_name": "Osteomielite dos ossos da perna", "subgroup": "Ortopedia", "applications": "Osteomielite, perna, tíbia, fíbula, infecção óssea", "is_primary": True},
        {"tuss_code": "30722519", "procedure_name": "Tratamento cirúrgico da osteomielite", "subgroup": "Ortopedia", "applications": "Osteomielite, tratamento cirúrgico geral, infecção óssea"},
        {"tuss_code": "30215099", "procedure_name": "Osteomielite de crânio - tratamento cirúrgico", "subgroup": "Neurocirurgia", "applications": "Osteomielite, crânio, cabeça"},
        {"tuss_code": "30601258", "procedure_name": "Osteomielite de costela ou esterno", "subgroup": "Cirurgia Torácica", "applications": "Osteomielite, costela, esterno, parede torácica"},
        {"tuss_code": "30717124", "procedure_name": "Osteomielite da cintura escapular", "subgroup": "Ortopedia", "applications": "Osteomielite, cintura escapular, ombro"},
        {"tuss_code": "30718082", "procedure_name": "Osteomielite de úmero", "subgroup": "Ortopedia", "applications": "Osteomielite, úmero, braço"},
        {"tuss_code": "30720125", "procedure_name": "Osteomielite dos ossos do antebraço", "subgroup": "Ortopedia", "applications": "Osteomielite, antebraço, rádio, ulna"},
        {"tuss_code": "30723078", "procedure_name": "Osteomielite da pelve", "subgroup": "Ortopedia", "applications": "Osteomielite, pelve, cintura pélvica"},
        {"tuss_code": "30725143", "procedure_name": "Osteomielite de membros inferiores", "subgroup": "Ortopedia", "applications": "Osteomielite, membros inferiores, fêmur"},
        {"tuss_code": "30729033", "procedure_name": "Osteomielite dos ossos do pé", "subgroup": "Ortopedia", "applications": "Osteomielite, pé, artrite, osteoartrite"},
        {"tuss_code": "30713048", "procedure_name": "Enxertos em pseudartroses", "subgroup": "Ortopedia", "applications": "Pseudoartrose, enxerto ósseo, não consolidação"},
        {"tuss_code": "30715245", "procedure_name": "Pseudoartrose de coluna", "subgroup": "Ortopedia", "applications": "Pseudoartrose, coluna vertebral"},
        {"tuss_code": "30720133", "procedure_name": "Pseudoartrose com ou sem fixador externo", "subgroup": "Ortopedia", "applications": "Pseudoartrose, osteotomia, fixador externo"},
        {"tuss_code": "30722306", "procedure_name": "Enxerto ósseo - perda de substância", "subgroup": "Ortopedia", "applications": "Enxerto ósseo, perda de substância, defeito ósseo, membros superiores"},
        {"tuss_code": "30732115", "procedure_name": "Tumor ósseo - ressecção e enxerto", "subgroup": "Ortopedia", "applications": "Tumor ósseo, ressecção, enxerto, neoplasia"},
        {"tuss_code": "30715016", "procedure_name": "Artrodese de coluna com instrumentação", "subgroup": "Ortopedia", "applications": "Artrodese, coluna, instrumentação, fusão vertebral"},
        {"tuss_code": "30715024", "procedure_name": "Artrodese de coluna via anterior/posterolateral", "subgroup": "Ortopedia", "applications": "Artrodese, coluna, via anterior, posterolateral"},
        {"tuss_code": "30715210", "procedure_name": "Osteomielite de coluna", "subgroup": "Ortopedia", "applications": "Osteomielite, coluna, espondilodiscite"},
        {"tuss_code": "30717019", "procedure_name": "Artrodese de ombro", "subgroup": "Ortopedia", "applications": "Artrodese, ombro, cintura escapular"},
        {"tuss_code": "30719011", "procedure_name": "Artrodese de cotovelo/braço", "subgroup": "Ortopedia", "applications": "Artrodese, cotovelo, membros superiores"},
        {"tuss_code": "30721032", "procedure_name": "Artrodese entre ossos do carpo", "subgroup": "Ortopedia", "applications": "Artrodese, carpo, punho, mão"},
        {"tuss_code": "30721059", "procedure_name": "Artrodese radiocárpica/punho", "subgroup": "Ortopedia", "applications": "Artrodese, radiocárpica, punho"},
        {"tuss_code": "30722110", "procedure_name": "Artrodese interfalangeana/metacarpofalangeana", "subgroup": "Ortopedia", "applications": "Artrodese, dedo, interfalangeana, metacarpofalangeana"},
        {"tuss_code": "30723086", "procedure_name": "Osteotomias/artrodeses pélvicas", "subgroup": "Ortopedia", "applications": "Osteotomia, artrodese, pelve, cintura pélvica"},
        {"tuss_code": "30724023", "procedure_name": "Artrose com ou sem fixador externo", "subgroup": "Ortopedia", "applications": "Artrose, fixador externo, tratamento cirúrgico"},
        {"tuss_code": "30724031", "procedure_name": "Artrodese coxofemoral", "subgroup": "Ortopedia", "applications": "Artrodese, coxofemoral, quadril"},
        {"tuss_code": "30726026", "procedure_name": "Artrodese de joelho", "subgroup": "Ortopedia", "applications": "Artrodese, joelho"},
        {"tuss_code": "30728045", "procedure_name": "Artrodese de tornozelo", "subgroup": "Ortopedia", "applications": "Artrodese, tornozelo"},
        {"tuss_code": "30729041", "procedure_name": "Artrodese de tarso/médio pé", "subgroup": "Ortopedia", "applications": "Artrodese, tarso, médio pé"},
        {"tuss_code": "30729050", "procedure_name": "Artrodese metatarso-falângica", "subgroup": "Ortopedia", "applications": "Artrodese, metatarso, falângica, pé"},
        {"tuss_code": "30207193", "procedure_name": "Fraturas complexas do terço médio da face", "subgroup": "Bucomaxilofacial", "applications": "Fratura, face, terço médio, enxerto ósseo, trauma craniomaxilofacial"},
        {"tuss_code": "30208106", "procedure_name": "Hemimandibulectomia/reconstrução mandíbula", "subgroup": "Cabeça e Pescoço", "applications": "Hemimandibulectomia, reconstrução, mandíbula, maxila, enxerto ósseo"},
        {"tuss_code": "30211050", "procedure_name": "Mandibulectomia com/sem enxerto ósseo", "subgroup": "Cabeça e Pescoço", "applications": "Mandibulectomia, esvaziamento ganglionar, enxerto ósseo"},
    ],
    "Kit EC2 - Linha Opus": [
        {"tuss_code": "30713137", "procedure_name": "Punção/infiltração articular diagnóstica ou terapêutica", "subgroup": "Ortopedia", "applications": "Viscossuplementação, infiltração articular, ácido hialurônico, osteoartrite, gonartrose, joelho", "is_primary": True},
    ],
    "Parafuso de Interferência Bioabsorvível": [
        {"tuss_code": "30727049", "procedure_name": "Reconstrução de LCA", "subgroup": "Ortopedia", "applications": "Reconstrução ligamentar, LCA, ligamento cruzado anterior, joelho, fixação de enxerto", "is_primary": True},
    ],
    "Tela de Polipropileno Macroporosa": [
        {"tuss_code": "31009107", "procedure_name": "Herniorrafia incisional", "subgroup": "Cirurgia Geral", "applications": "Hérnia incisional, hérnia inguinal, herniorrafia, hernioplastia, tela, polipropileno", "is_primary": True},
    ],
    "Vitagraft - Enxerto Bifásico": [
        {"tuss_code": "30713048", "procedure_name": "Enxertos em pseudartroses", "subgroup": "Ortopedia", "applications": "Pseudoartrose, enxerto ósseo, não consolidação, defeito ósseo", "is_primary": True},
        {"tuss_code": "30722306", "procedure_name": "Enxerto ósseo - perda de substância", "subgroup": "Ortopedia", "applications": "Enxerto ósseo, perda de substância, defeito ósseo"},
        {"tuss_code": "30715245", "procedure_name": "Pseudoartrose de coluna", "subgroup": "Ortopedia", "applications": "Pseudoartrose, coluna vertebral"},
        {"tuss_code": "30720133", "procedure_name": "Pseudoartrose com ou sem fixador externo", "subgroup": "Ortopedia", "applications": "Pseudoartrose, osteotomia, fixador externo"},
        {"tuss_code": "30732115", "procedure_name": "Tumor ósseo - ressecção e enxerto", "subgroup": "Ortopedia", "applications": "Tumor ósseo, ressecção, enxerto"},
        {"tuss_code": "30715016", "procedure_name": "Artrodese de coluna com instrumentação", "subgroup": "Ortopedia", "applications": "Artrodese, coluna, instrumentação, fusão vertebral"},
        {"tuss_code": "30715024", "procedure_name": "Artrodese de coluna via anterior/posterolateral", "subgroup": "Ortopedia", "applications": "Artrodese, coluna, via anterior, posterolateral"},
        {"tuss_code": "30215048", "procedure_name": "Reconstrução craniana ou craniofacial", "subgroup": "Neurocirurgia", "applications": "Reconstrução craniana, craniofacial, cranioplastia"},
        {"tuss_code": "30717019", "procedure_name": "Artrodese de ombro", "subgroup": "Ortopedia", "applications": "Artrodese, ombro"},
        {"tuss_code": "30719011", "procedure_name": "Artrodese de cotovelo", "subgroup": "Ortopedia", "applications": "Artrodese, cotovelo"},
        {"tuss_code": "30721032", "procedure_name": "Artrodese entre ossos do carpo", "subgroup": "Ortopedia", "applications": "Artrodese, carpo, punho"},
        {"tuss_code": "30724031", "procedure_name": "Artrodese coxofemoral", "subgroup": "Ortopedia", "applications": "Artrodese, coxofemoral, quadril"},
        {"tuss_code": "30726026", "procedure_name": "Artrodese de joelho", "subgroup": "Ortopedia", "applications": "Artrodese, joelho"},
        {"tuss_code": "30728045", "procedure_name": "Artrodese de tornozelo", "subgroup": "Ortopedia", "applications": "Artrodese, tornozelo"},
        {"tuss_code": "30729041", "procedure_name": "Artrodese de tarso/médio pé", "subgroup": "Ortopedia", "applications": "Artrodese, tarso, médio pé"},
        {"tuss_code": "30729050", "procedure_name": "Artrodese metatarso-falângica", "subgroup": "Ortopedia", "applications": "Artrodese, metatarso, falângica"},
        {"tuss_code": "30601169", "procedure_name": "Toracoplastia", "subgroup": "Cirurgia Torácica", "applications": "Toracoplastia, parede torácica"},
        {"tuss_code": "30601096", "procedure_name": "Reconstrução da parede torácica", "subgroup": "Cirurgia Torácica", "applications": "Reconstrução, parede torácica, enxerto, prótese"},
        {"tuss_code": "30207193", "procedure_name": "Fraturas complexas do terço médio da face", "subgroup": "Bucomaxilofacial", "applications": "Fratura, face, terço médio, enxerto ósseo"},
        {"tuss_code": "30208106", "procedure_name": "Hemimandibulectomia/reconstrução mandíbula", "subgroup": "Cabeça e Pescoço", "applications": "Hemimandibulectomia, reconstrução, mandíbula, maxila"},
        {"tuss_code": "30211050", "procedure_name": "Mandibulectomia com/sem enxerto ósseo", "subgroup": "Cabeça e Pescoço", "applications": "Mandibulectomia, esvaziamento ganglionar"},
        {"tuss_code": "30723086", "procedure_name": "Osteotomias/artrodeses pélvicas", "subgroup": "Ortopedia", "applications": "Osteotomia, artrodese, pelve"},
        {"tuss_code": "30724023", "procedure_name": "Artrose com ou sem fixador externo", "subgroup": "Ortopedia", "applications": "Artrose, fixador externo"},
    ],
    "Kit EC2 - Enxerto Composto": [
        {"tuss_code": "30101310", "procedure_name": "Enxerto composto - tecido celular subcutâneo", "subgroup": "Cirurgia Geral", "applications": "Enxerto composto, tecido celular subcutâneo, SVF, estroma vascular, medicina regenerativa", "is_primary": True},
        {"tuss_code": "31206204", "procedure_name": "Plástica de corpo cavernoso", "subgroup": "Urologia", "applications": "Corpo cavernoso, disfunção erétil, Peyronie, curvatura peniana"},
        {"tuss_code": "31206042", "procedure_name": "Doença de Peyronie - tratamento cirúrgico", "subgroup": "Urologia", "applications": "Peyronie, curvatura peniana, placa fibrosa"},
        {"tuss_code": "31206263", "procedure_name": "Revascularização peniana", "subgroup": "Urologia", "applications": "Revascularização, disfunção erétil, insuficiência vascular peniana"},
        {"tuss_code": "31104142", "procedure_name": "Meatotomia uretral", "subgroup": "Urologia", "applications": "Estenose uretral, meatotomia, meato uretral"},
        {"tuss_code": "30101670", "procedure_name": "Plástica em Z ou W", "subgroup": "Cirurgia Plástica", "applications": "Plástica, reconstrução, cicatriz, brida, retração"},
    ],
    "Kit FO - Laser Cirúrgico": [
        {"tuss_code": "30501458", "procedure_name": "Turbinectomia/turbinoplastia", "subgroup": "Otorrinolaringologia", "applications": "Turbinectomia, turbinoplastia, cornetos, septoplastia, hipertrofia de cornetos, obstrução nasal", "is_primary": True},
        {"tuss_code": "30501113", "procedure_name": "Cauterização nasal (qualquer técnica)", "subgroup": "Otorrinolaringologia", "applications": "Cauterização, hemostasia, coagulação nasal, sangramento"},
        {"tuss_code": "30501199", "procedure_name": "Exérese de tumor nasal por via endoscópica", "subgroup": "Otorrinolaringologia", "applications": "Tumor nasal, endoscopia, Rendu-Osler-Weber, sinéquias nasais"},
        {"tuss_code": "30502080", "procedure_name": "Etmoidectomia intranasal", "subgroup": "Otorrinolaringologia", "applications": "Etmoidectomia, seios paranasais, etmoide"},
        {"tuss_code": "30206219", "procedure_name": "Microcirurgia com laser - lesões malignas", "subgroup": "Otorrinolaringologia", "applications": "Laser, lesões malignas, laringe, traqueia, estenose laríngea"},
        {"tuss_code": "30206227", "procedure_name": "Microcirurgia com laser - lesões benignas", "subgroup": "Otorrinolaringologia", "applications": "Laser, lesões benignas, laringe, traqueia, papiloma, sinéquias"},
        {"tuss_code": "40202763", "procedure_name": "Laringoscopia/traqueoscopia com laser", "subgroup": "Otorrinolaringologia", "applications": "Laringoscopia, traqueoscopia, laser, papiloma, tumor laríngeo"},
        {"tuss_code": "30206065", "procedure_name": "Exérese de tumor por via endoscópica com laser", "subgroup": "Otorrinolaringologia", "applications": "Tumor, endoscopia, laser, laringe, traqueia"},
        {"tuss_code": "30205034", "procedure_name": "Adeno-amigdalectomia", "subgroup": "Otorrinolaringologia", "applications": "Adenoidectomia, amigdalectomia, adenoide, amígdala, hipertrofia"},
        {"tuss_code": "30205247", "procedure_name": "Uvulopalatofaringoplastia", "subgroup": "Otorrinolaringologia", "applications": "Uvuloplastia, uvulopalatoplastia, apneia obstrutiva do sono, ronco, SAHOS"},
        {"tuss_code": "30501377", "procedure_name": "Ressecção de sinéquias", "subgroup": "Otorrinolaringologia", "applications": "Sinéquias nasais, paranasais, laríngeas, faríngeas, pós-cirúrgicas"},
        {"tuss_code": "40202151", "procedure_name": "Desobstrução brônquica com laser", "subgroup": "Pneumologia", "applications": "Desobstrução brônquica, estenose brônquica, tumor brônquico, vias aéreas"},
    ],
}

# ============================================================================
# Templates de relatórios cirúrgicos reais (fonte: relatórios aprovados Hugo/Rastriall)
# ============================================================================
UROLOGY_TEMPLATES_SEED = [
    {
        "nome": "Template EC2 - Urologia - Doença de Peyronie",
        "especialidade": "Urologia",
        "produto_nome": "Kit EC2 - Enxerto Composto",
        "tom_de_voz": (
            "Tom científico, formal e assertivo. Justificar necessidade do enxerto composto "
            "para reparação do corpo cavernoso. Referenciar técnica de colheita de SVF."
        ),
        "template_corpo": (
            "O paciente {paciente_nome}, portador de {diagnostico} (CID {cid}), será submetido "
            "a tratamento cirúrgico para Doença de Peyronie com plástica de corpo cavernoso e "
            "aplicação de enxerto composto em toda extensão e base do corpo cavernoso, a fim de "
            "proporcionar vasculogênese e angiogênese para melhor resposta à conduta clínica e "
            "modulação do processo inflamatório e cicatricial.\n\n"
            "A colheita de enxerto composto quando abordado o tecido celular subcutâneo deve ser "
            "acompanhada dos cuidados de preservação entre o momento da colheita e a efetiva "
            "reimplantação. É fundamental ter instrumental adequado (cânulas de acesso e colheita) "
            "e meios de preservação do enxerto composto (gel carreador) para que não haja degradação "
            "ou contaminação do tecido celular subcutâneo coletado.\n\n"
            "Enxertos compostos são formados por grupos celulares subcutâneos onde encontramos "
            "células do estroma vascular (SVF) que são fundamentais para a reparação tecidual. "
            "{falha_terapeutica}\n\n"
            "A não realização do procedimento implica em {risco_nao_realizacao}."
        ),
        "bases_legais": ["RN 395", "RN 424", "RN 465"],
        "referencias_padrao": [
            "Glauco Andre Almeida Guedes, CRM-DF 9934. Relatório Cirúrgico EC2 - Doença de Peyronie.",
        ],
        "exemplos_aprovados": [
            "Paciente J.R., portador de Doença de Peyronie com disfunção erétil e calcificações em topografia de corpo cavernoso bilateral, com curvatura peniana (CID N45), será submetido a plástica de corpo cavernoso (31206204), Doença de Peyronie - tratamento cirúrgico (31206042), meatotomia uretral (31104142), plástica em Z ou W (30101670) e enxerto composto de tecido celular subcutâneo (30101310). Para esse caso necessito de tratamento cirúrgico para aplicação de enxerto composto em toda extensão e base do corpo cavernoso, a fim de proporcionar vasculogênese e angiogênese para melhor resposta à conduta clínica e modulação do processo inflamatório e cicatricial. A colheita de enxerto composto deve ser acompanhada dos cuidados de preservação entre colheita e reimplantação, sendo fundamental instrumental adequado e meios de preservação para que não haja degradação ou contaminação do tecido coletado.",
        ],
    },
    {
        "nome": "Template EC2 - Urologia - Disfunção Erétil",
        "especialidade": "Urologia",
        "produto_nome": "Kit EC2 - Enxerto Composto",
        "tom_de_voz": (
            "Tom científico, formal e assertivo. Justificar enxerto composto para "
            "revascularização e reparação de corpo cavernoso em disfunção erétil."
        ),
        "template_corpo": (
            "O paciente {paciente_nome}, portador de {diagnostico} (CID {cid}), será submetido "
            "a plástica de corpo cavernoso com revascularização peniana e aplicação de enxerto "
            "composto de tecido celular subcutâneo.\n\n"
            "Para esse caso necessito de tratamento cirúrgico para aplicação de enxerto composto "
            "em toda extensão e base do corpo cavernoso, a fim de proporcionar vasculogênese e "
            "angiogênese para melhor resposta à conduta clínica e modulação do processo inflamatório "
            "e cicatricial. {falha_terapeutica}\n\n"
            "A não realização do procedimento implica em {risco_nao_realizacao}."
        ),
        "bases_legais": ["RN 395", "RN 424", "RN 465"],
        "referencias_padrao": [
            "Glauco Andre Almeida Guedes, CRM-DF 9934. Relatório Cirúrgico EC2 - Disfunção Erétil.",
        ],
        "exemplos_aprovados": [
            "Paciente R.A., portador de disfunção erétil com calcificações significativas em topografia de corpo cavernoso bilateral, com curvatura peniana (CID N45), será submetido a plástica de corpo cavernoso (31206204), revascularização peniana (31206263), plástica em Z ou W (30101670) e enxerto composto de tecido celular subcutâneo (30101310). Enxertos compostos são formados por grupos celulares subcutâneos onde encontramos células do estroma vascular (SVF) fundamentais para a reparação tecidual. A colheita deve ser acompanhada dos cuidados de preservação entre colheita e reimplantação, com instrumental adequado e meios de preservação do gel carreador.",
        ],
    },
    {
        "nome": "Template EC2 - Urologia - Estenose Uretral",
        "especialidade": "Urologia",
        "produto_nome": "Kit EC2 - Enxerto Composto",
        "tom_de_voz": (
            "Tom científico, formal e assertivo. Justificar enxerto composto para "
            "tratamento de estenose uretral com meatotomia e plástica."
        ),
        "template_corpo": (
            "O paciente {paciente_nome}, portador de {diagnostico} (CID {cid}), será submetido "
            "a meatotomia uretral para tratamento de estenose com plástica de corpo cavernoso "
            "e aplicação de enxerto composto de tecido celular subcutâneo.\n\n"
            "Para esse caso necessito de tratamento cirúrgico para aplicação de enxerto composto "
            "a fim de proporcionar vasculogênese e angiogênese para melhor resposta à conduta "
            "clínica e modulação do processo inflamatório e cicatricial. {falha_terapeutica}\n\n"
            "A não realização do procedimento implica em {risco_nao_realizacao}."
        ),
        "bases_legais": ["RN 395", "RN 424", "RN 465"],
        "referencias_padrao": [
            "Glauco Andre Almeida Guedes, CRM-DF 9934. Relatório Cirúrgico EC2 - Estenose Uretral.",
        ],
        "exemplos_aprovados": [
            "Paciente M.C., portador de estenose uretral com disfunção erétil e calcificações em topografia de corpo cavernoso bilateral (CID N45), será submetido a plástica de corpo cavernoso (31206204), meatotomia uretral (31104142), plástica em Z ou W (30101670) e enxerto composto de tecido celular subcutâneo (30101310). A colheita de enxerto composto quando abordado o tecido celular subcutâneo deve ser acompanhada dos cuidados de preservação. Enxertos compostos são formados por grupos celulares subcutâneos com células do estroma vascular (SVF) fundamentais para reparação tecidual.",
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
        "descricao": "GLOSA: Materiais OPME (Tabela 19) NÃO podem ser lançados como Honorários. Devem ir no Anexo OPME ou Mat/Med. (TISS Tabela 38 — motivo 1801: PROCEDIMENTO INVÁLIDO)",
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
        "descricao": "GLOSA: Materiais OPME (Tabela 19) NÃO podem ser lançados como Honorários em guia de Internação. (TISS Tabela 38 — motivo 1801: PROCEDIMENTO INVÁLIDO)",
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
        "descricao": "GLOSA: Guia de Honorário Individual NÃO pode conter materiais OPME (Tabela 19). (TISS Tabela 38 — motivo 1801: PROCEDIMENTO INVÁLIDO)",
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
            ("31009107", "Herniorrafia incisional"),
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

        # Seed product-TUSS mappings
        for product_name, mappings in PRODUCT_TUSS_MAPPINGS_SEED.items():
            pid = product_map.get(product_name)
            if not pid:
                continue
            for mdata in mappings:
                db.add(ProductTussMapping(product_id=pid, **mdata))

        # Seed urology templates
        for tdata in UROLOGY_TEMPLATES_SEED:
            tdata = dict(tdata)
            produto_nome = tdata.pop("produto_nome")
            t = ReportTemplate(
                produto_id=product_map.get(produto_nome),
                **tdata,
            )
            db.add(t)

        await db.commit()


async def main():
    await create_tables()
    await seed()
    print("DB initialized and seeded.")


if __name__ == "__main__":
    asyncio.run(main())
