"""
Ingestão completa dos estudos locais (Lipedema, Ortopedia, Rec Mama, Regenerativa)
→ tabela clinical_evidences.

Ignora duplicatas de arquivos já ingeridos em seed_estudos_estetica.py.
Os .docx de "Relatório" são templates, não evidências — ficam de fora.
A RDC 508/2021 é normativa ANVISA, inserida como base legal, não snippet clínico.

Uso:
    cd services/api
    python3 -m scripts.seed_estudos_completo
"""
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app.db.session import engine

# ─── IDs dos produtos (placeholders - resolvidos em runtime) ──────────
KIT_FO_LASER = "__KIT_FO_LASER__"
KIT_EC2_ENXERTO = "__KIT_EC2_ENXERTO__"
KIT_EC2_OPUS = "__KIT_EC2_OPUS__"
KIT_LP_CT = "__KIT_LP_CT__"

async def _resolve_product_ids(evidences):
    from app.db.session import AsyncSessionLocal
    from app.db.models import Product
    from sqlalchemy import select
    mapping = {}
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Product))
        for p in r.scalars().all():
            name = p.nome.lower()
            pid = str(p.id)
            if "laser" in name or "kit fo" in name:
                mapping["__KIT_FO_LASER__"] = pid
            elif "enxerto" in name and "ec2" in name:
                mapping["__KIT_EC2_ENXERTO__"] = pid
            elif "opus" in name or ("ec2" in name and "enxerto" not in name):
                mapping["__KIT_EC2_OPUS__"] = pid
            elif "biossilex" in name or "biovidro" in name:
                mapping["__KIT_LP_CT__"] = pid
    # fallback
    if "__KIT_LP_CT__" not in mapping and "__KIT_EC2_OPUS__" in mapping:
        mapping["__KIT_LP_CT__"] = mapping["__KIT_EC2_OPUS__"]
    fallback = next(iter(mapping.values()), None)
    for ev in evidences:
        ev["product_id"] = mapping.get(ev["product_id"], fallback)

EVIDENCES = [
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # LIPEDEMA
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_FO_LASER,
        "cid": "E88.2",
        "snippet": (
            "Em estudo caso-controle com 10 pacientes com lipedema grau 1, a lipoaspiração "
            "assistida por laser (dispositivo Lipo One Step HD, 1210 nm) reduziu significativamente "
            "o tempo operatório (94±10 min vs 122±15 min, p=0.003), a perda sanguínea "
            "(408±30 mL vs 551±50 mL, p<0.001) e a dor pós-operatória (VAS 4.2±0.8 vs 6.5±1.0, "
            "p=0.01), com retorno mais rápido às atividades normais (6.4±1.5 vs 9.8±2.1 dias, p=0.03)."
        ),
        "autor": "Valente DS et al.",
        "referencia_completa": (
            "Valente DS, Zanella RK, Jardim GM, Herzog CG, Gianesini G, Carvalho LA. "
            "Conventional and Laser-assisted Liposuction: A Case-Control Study in Lipedema "
            "Patients. Int J Clin Med Surg. 2024;2(1):1-3."
        ),
        "ano": "2024",
        "tipo": "caso-controle",
        "relevancia": "alta",
    },
    {
        "product_id": KIT_LP_CT,
        "cid": "E88.2",
        "snippet": (
            "A lipoaspiração assistida por laser com comprimento de onda de 1210 nm (Lipo One "
            "Step HD) em pacientes com lipedema demonstrou vantagens significativas sobre a "
            "técnica convencional: redução de 23% no tempo cirúrgico, 26% menos perda sanguínea "
            "e scores de qualidade de vida (SF-36) superiores em componentes físicos e mentais."
        ),
        "autor": "Valente DS et al.",
        "referencia_completa": (
            "Valente DS, Zanella RK, Jardim GM, Herzog CG, Gianesini G, Carvalho LA. "
            "Conventional and Laser-assisted Liposuction: A Case-Control Study in Lipedema "
            "Patients. Int J Clin Med Surg. 2024;2(1):1-3."
        ),
        "ano": "2024",
        "tipo": "caso-controle",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ORTOPEDIA — Özkan et al. (2022) SVF em retalhos com DM + DRC
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "E11.5",
        "snippet": (
            "A injeção de SVF adiposo aumentou significativamente a viabilidade de retalhos cutâneos "
            "em ratos com diabetes mellitus e doença renal crônica (p<0.05). Observou-se aumento "
            "significativo na formação de novos capilares e nos níveis de VEGF nos grupos tratados "
            "com SVF comparados ao controle, demonstrando diferenciação endotelial e neovascularização."
        ),
        "autor": "Özkan B et al.",
        "referencia_completa": (
            "Özkan B, Eyüboğlu AA, Terzi A, Özer EÖ, Tatar BE, Uysal CA. The Effect of Adipose "
            "Derived Stromal Vascular Fraction on Flap Viability in Experimental Diabetes Mellitus "
            "and Chronic Renal Disease. J Invest Surg. 2022. DOI: 10.1080/08941939.2022.2066741"
        ),
        "ano": "2022",
        "tipo": "experimental",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ORTOPEDIA — Sadri et al. (2023) AD-MSC para OA de joelho (RCT fase II)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "M17.0",
        "snippet": (
            "Ensaio clínico randomizado fase II, triplo-cego, placebo-controlado com 40 pacientes: "
            "injeção intra-articular de 100×10⁶ AD-MSCs alogênicas demonstrou regeneração da "
            "cartilagem articular por RM (aumento significativo na espessura tibial medial posterior "
            "p<0.01 e anterior p<0.05), redução dramática de marcadores inflamatórios após 3 meses "
            "(p<0.001) e aumento de IL-10 anti-inflamatória em 1 semana (p<0.05)."
        ),
        "autor": "Sadri B et al.",
        "referencia_completa": (
            "Sadri B, Hassanzadeh M, Bagherifard A, et al. Cartilage regeneration and inflammation "
            "modulation in knee osteoarthritis following injection of allogeneic adipose-derived "
            "mesenchymal stromal cells: a phase II, triple-blinded, placebo controlled, randomized "
            "trial. Stem Cell Res Ther. 2023;14:162. DOI: 10.1186/s13287-023-03359-8"
        ),
        "ano": "2023",
        "tipo": "rct",
        "relevancia": "alta",
    },
    {
        "product_id": KIT_EC2_OPUS,
        "cid": "M17.0",
        "snippet": (
            "Em pacientes com gonartrose, AD-MSCs reduziram significativamente os níveis séricos "
            "de ácido hialurônico e proteína oligomérica da matriz cartilaginosa (COMP) (p<0.05), "
            "indicando modulação da degradação articular. Expressão de CD3, CD4, CD8 com tendência "
            "decrescente até 6 meses (p<0.001), confirmando imunomodulação local."
        ),
        "autor": "Sadri B et al.",
        "referencia_completa": (
            "Sadri B, Hassanzadeh M, Bagherifard A, et al. Cartilage regeneration and inflammation "
            "modulation in knee osteoarthritis following injection of allogeneic AD-MSCs: phase II RCT. "
            "Stem Cell Res Ther. 2023;14:162. DOI: 10.1186/s13287-023-03359-8"
        ),
        "ano": "2023",
        "tipo": "rct",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ORTOPEDIA — Anil et al. (2021) Network meta-analysis infiltrações joelho
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "M17.0",
        "snippet": (
            "Network meta-analysis de 79 RCTs (8.761 pacientes): em todos os tempos de seguimento, "
            "SVF obteve o maior P-Score para VAS (0.86-0.99) e WOMAC em 12 meses (0.90). "
            "SVF superou PRP, HA de alto peso molecular, corticosteroides, BMAC e MSCs cultivadas "
            "em dor e desfechos funcionais para osteoartrite de joelho."
        ),
        "autor": "Anil U et al.",
        "referencia_completa": (
            "Anil U, Markus DH, Hurley ET, et al. The efficacy of intra-articular injections in the "
            "treatment of knee osteoarthritis: A network meta-analysis of randomized controlled "
            "trials. The Knee. 2021;32:173-182. DOI: 10.1016/j.knee.2021.08.008"
        ),
        "ano": "2021",
        "tipo": "meta-analise",
        "relevancia": "alta",
    },
    {
        "product_id": KIT_EC2_OPUS,
        "cid": "M17.1",
        "snippet": (
            "Em meta-análise de rede com 8.761 pacientes, HA de alto peso molecular + corticosteroide "
            "obteve melhor P-Score WOMAC em 4-6 semanas (0.95) e 3 meses (0.85). PRP liderou "
            "em 6 meses (0.77). Viscossuplementação com HA de alto peso molecular demonstrou "
            "eficácia superior a HA convencional em todos os tempos avaliados."
        ),
        "autor": "Anil U et al.",
        "referencia_completa": (
            "Anil U, Markus DH, Hurley ET, et al. The efficacy of intra-articular injections in the "
            "treatment of knee osteoarthritis: A network meta-analysis of RCTs. The Knee. "
            "2021;32:173-182. DOI: 10.1016/j.knee.2021.08.008"
        ),
        "ano": "2021",
        "tipo": "meta-analise",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ORTOPEDIA — Nguyen et al. (2015) SVF Review Part 1
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "M17.0",
        "snippet": (
            "SVF é uma coleção heterogênea de células do tecido adiposo incluindo MSCs, células "
            "precursoras endoteliais, células T regulatórias, macrófagos, pericitos e pré-adipócitos. "
            "A sinergia entre esses componentes confere potencial regenerativo comparativamente "
            "eficaz ao das ADSCs cultivadas, com a vantagem de disponibilidade imediata no "
            "ponto de atendimento."
        ),
        "autor": "Nguyen A et al.",
        "referencia_completa": (
            "Nguyen A, Guo J, Banyard DA, et al. Stromal vascular fraction: A regenerative reality? "
            "Part 1: Current concepts and review of the literature. J Plast Reconstr Aesthet Surg. "
            "2015. DOI: 10.1016/j.bjps.2015.10.015"
        ),
        "ano": "2015",
        "tipo": "revisao",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ORTOPEDIA — Berman et al. (2019) SVF prospectivo 2.586 pacientes
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "M17.0",
        "snippet": (
            "Estudo prospectivo com 2.586 pacientes tratados com SVF autólogo para osteoartrite "
            "de joelho: melhora estatisticamente significativa em dor e mobilidade em 1 e 2 anos, "
            "82% de melhora geral, sem diferença entre gêneros. Poucos eventos adversos, "
            "todos menores ou facilmente tratáveis. SVF demonstrou segurança e eficácia mesmo "
            "em casos crônicos difíceis."
        ),
        "autor": "Berman M et al.",
        "referencia_completa": (
            "Berman M, Lander E, Grogan T, O'Brien W, Braslow J, Dowell S, Berman S. "
            "Prospective Study of Autologous Adipose Derived Stromal Vascular Fraction Containing "
            "Stem Cells for the Treatment of Knee Osteoarthritis. Int J Stem Cell Res Ther. "
            "2019;6:064. DOI: 10.23937/2469-570X/1410064"
        ),
        "ano": "2019",
        "tipo": "coorte",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ORTOPEDIA — Bora & Majumdar (2017) SVF biology and translation
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "L97",
        "snippet": (
            "Review sobre biologia da SVF demonstra que a composição heterogênea (ADSCs, EPCs, "
            "pericitos, células imunes) confere resultados terapêuticos superiores aos de ADSCs "
            "isoladas em estudos comparativos in vivo. SVF é mais facilmente obtida, sem necessidade "
            "de cultivo, com menor contato com reagentes — tornando-a mais segura e com menor "
            "barreira regulatória."
        ),
        "autor": "Bora P, Majumdar AS",
        "referencia_completa": (
            "Bora P, Majumdar AS. Adipose tissue-derived stromal vascular fraction in regenerative "
            "medicine: a brief review on biology and translation. Stem Cell Res Ther. 2017;8:145. "
            "DOI: 10.1186/s13287-017-0598-y"
        ),
        "ano": "2017",
        "tipo": "revisao",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ORTOPEDIA — Zhao et al. (2020) SVF para pé diabético
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "E11.5",
        "snippet": (
            "Review sobre SVF para pé diabético: o transplante de células-tronco promove regeneração "
            "de vasos sanguíneos e tecidos nervosos ao redor do sítio transplantado, reconstruindo "
            "a circulação e melhorando o suprimento sanguíneo. A remodelação vascular é o mecanismo "
            "potencial pelo qual a SVF trata o pé diabético, superando limitações de bypass vascular "
            "e cirurgia intervencionista."
        ),
        "autor": "Zhao X et al.",
        "referencia_completa": (
            "Zhao X, Guo J, Zhang F, Zhang J, Liu D, Hu W, Yin H, Jin L. Therapeutic application "
            "of adipose-derived stromal vascular fraction in diabetic foot. Stem Cell Res Ther. "
            "2020;11:394. DOI: 10.1186/s13287-020-01825-1"
        ),
        "ano": "2020",
        "tipo": "revisao",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ORTOPEDIA — Rodriguez-Merchan (2022) SVF para lesões musculoesqueléticas
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "M17.0",
        "snippet": (
            "Injeções intra-articulares de SVF demonstram segurança e eficácia no tratamento de "
            "osteoartrite de joelho. SVF também mostrou utilidade em tendinopatia de Aquiles "
            "recalcitrante, epicondilite lateral crônica, úlceras diabéticas crônicas e regeneração "
            "de cartilagem articular via gel de matriz extracelular/SVF."
        ),
        "autor": "Rodriguez-Merchan EC, Encinas-Ullan CA",
        "referencia_completa": (
            "Rodriguez-Merchan EC, Encinas-Ullan CA. Stromal Vascular Fraction for "
            "Musculoskeletal Lesions. Int J Orthop. 2022;9(3):1658-1668."
        ),
        "ano": "2022",
        "tipo": "revisao",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ORTOPEDIA — Clarke LK (2014) Bioquímica celular para med regenerativa
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "L97",
        "snippet": (
            "A otimização da bioquímica celular — suplementação com CoQ10, acetil-L-carnitina, "
            "ácido alfa-lipoico e hormônios anabólicos — pode potencializar a eficácia do PRP e "
            "de terapias regenerativas. Em caso documentado, ferida de 10 anos cicatrizou em 3 meses "
            "apenas com protocolo bioquímico (sem PRP), demonstrando que o 'solo celular' deve "
            "ser preparado para resultados regenerativos ótimos."
        ),
        "autor": "Clarke LK",
        "referencia_completa": (
            "Clarke LK. Preparing the Soil: Practical Cellular Biochemistry for Regenerative "
            "Medicine. In: Lana JFSD et al. (eds) Platelet-Rich Plasma. Lecture Notes in "
            "Bioengineering. Springer, Berlin. 2014. DOI: 10.1007/978-3-642-40117-6_3"
        ),
        "ano": "2014",
        "tipo": "revisao",
        "relevancia": "media",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ORTOPEDIA — RDC 508/2021 (base legal ANVISA para células)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "M17.0",
        "snippet": (
            "A RDC 508/2021 da ANVISA estabelece Boas Práticas em Células Humanas para Uso "
            "Terapêutico. Conforme Art. 5°, §I, procedimentos autólogos realizados durante o mesmo "
            "ato cirúrgico com manipulação mínima estão ISENTOS das exigências de Centro de "
            "Processamento Celular — validando o uso intraoperatório de SVF obtida por técnicas "
            "como a One STEP™."
        ),
        "autor": "ANVISA",
        "referencia_completa": (
            "Brasil. Agência Nacional de Vigilância Sanitária. Resolução RDC nº 508, de 27 de "
            "maio de 2021. Dispõe sobre as Boas Práticas em Células Humanas para Uso Terapêutico "
            "e pesquisa clínica. DOU, Seção 1, 31/05/2021, p. 136."
        ),
        "ano": "2021",
        "tipo": "normativa",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # REC MAMA — Centurión-Rivas et al. (2017) Laser + lipoabdominoplastia
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_FO_LASER,
        "cid": "L90.5",
        "snippet": (
            "Em 101 lipoabdominoplastias (47 com laser 980nm, 54 com 1210nm), o laser 1210nm "
            "demonstrou protocolo reprodutível e seguro, sem queimaduras, tromboembolismo ou "
            "epidermólise. O 1210nm preserva adipócitos para uso em lipoenxertia, enquanto "
            "lasers com afinidade por água (980nm) promovem lipólise térmica que inviabiliza "
            "o material para enxerto."
        ),
        "autor": "Centurión-Rivas P, Gamarra-García R, Romero-Naváez C",
        "referencia_completa": (
            "Centurión-Rivas P, Gamarra-García R, Romero-Naváez C. Experiencia en el uso "
            "combinado de liposucción asistida por láser en lipoabdominoplastía. Cir Plást "
            "Iberolatinoam. 2017;43(1):21-31. DOI: 10.4321/S0376-78922016000400008"
        ),
        "ano": "2017",
        "tipo": "coorte",
        "relevancia": "alta",
    },
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "N60.9",
        "snippet": (
            "O laser 1210nm preserva adipócitos intactos para enxertia composta em reconstrução "
            "mamária. Em 54 procedimentos com 1210nm, observou-se menor taxa de seroma "
            "comparado ao 980nm, e o material lipoaspirado manteve viabilidade celular adequada "
            "para lipoenxertia autóloga pós-mastectomia."
        ),
        "autor": "Centurión-Rivas P et al.",
        "referencia_completa": (
            "Centurión-Rivas P, Gamarra-García R, Romero-Naváez C. Experiencia en el uso "
            "combinado de liposucción asistida por láser en lipoabdominoplastía. Cir Plást "
            "Iberolatinoam. 2017;43(1):21-31. DOI: 10.4321/S0376-78922016000400008"
        ),
        "ano": "2017",
        "tipo": "coorte",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # REC MAMA — Tan et al. (2026) SVF + fat grafting em expansão cutânea (RCT)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "N60.9",
        "snippet": (
            "RCT multicêntrico com 72 pacientes: transplante autólogo de SVF e enxertia adiposa "
            "promoveram aumento significativo na espessura cutânea vs controle (p<0.05) e maior "
            "índice de expansão em 12 semanas (p<0.001). Em pele com regeneração pobre, os "
            "tratamentos reverteram o afinamento. Sem eventos adversos graves em 2 anos de "
            "seguimento. Publicado em Plast Reconstr Surg."
        ),
        "autor": "Tan PC et al.",
        "referencia_completa": (
            "Tan PC, Wang YW, Xie Y, Xu X, Xiao H, Li G, Zhang PQ, Zhou SB, Li Q. "
            "Enhancing Skin Regeneration during Expansion: A Multicenter Randomized Controlled "
            "Trial of Stromal Vascular Fraction and Fat Grafting. Plast Reconstr Surg. "
            "2026;157:360. DOI: 10.1097/PRS.0000000000012347"
        ),
        "ano": "2026",
        "tipo": "rct",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # REGENERATIVA — Chang et al. (2020) PBM em células-tronco
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_FO_LASER,
        "cid": "L97",
        "snippet": (
            "A fotobiomodulação (PBM) estimula diferentes tipos de células-tronco a aumentar "
            "migração, proliferação e diferenciação tanto in vitro quanto in vivo. PBM com "
            "comprimentos de onda no infravermelho próximo (600-1100 nm) promove diferenciação "
            "osteogênica, condrogênica e adipogênica de MSCs, potencializando terapias "
            "regenerativas baseadas em células-tronco."
        ),
        "autor": "Chang SY et al.",
        "referencia_completa": (
            "Chang SY, Carpena NT, Kang BJ, Lee MY. Effects of Photobiomodulation on Stem "
            "Cells Important for Regenerative Medicine. Med Laser. 2020;9(2):134-141. "
            "DOI: 10.25289/ML.2020.9.2.134"
        ),
        "ano": "2020",
        "tipo": "revisao",
        "relevancia": "alta",
    },
    {
        "product_id": KIT_FO_LASER,
        "cid": "M17.0",
        "snippet": (
            "PBM com laser de baixa intensidade demonstrou aumentar a diferenciação condrogênica "
            "de MSCs derivadas de tecido adiposo, com upregulation de genes condrogênicos "
            "(SOX9, COL2A1, agrecano). Essa sinergia entre laser e células-tronco é particularmente "
            "relevante para regeneração da cartilagem articular em osteoartrite."
        ),
        "autor": "Chang SY et al.",
        "referencia_completa": (
            "Chang SY, Carpena NT, Kang BJ, Lee MY. Effects of Photobiomodulation on Stem "
            "Cells Important for Regenerative Medicine. Med Laser. 2020;9(2):134-141. "
            "DOI: 10.25289/ML.2020.9.2.134"
        ),
        "ano": "2020",
        "tipo": "revisao",
        "relevancia": "alta",
    },
]

INSERT_SQL = text("""
    INSERT INTO clinical_evidences (id, cid, product_id, snippet, autor, referencia_completa, ano, tipo, relevancia, created_at)
    VALUES (:id, :cid, :product_id, :snippet, :autor, :referencia_completa, :ano, :tipo, :relevancia, :created_at)
""")


async def main():
    await _resolve_product_ids(EVIDENCES)
    async with engine.begin() as conn:
        count_before = (await conn.execute(text("SELECT count(*) FROM clinical_evidences"))).scalar()
        print(f"Evidências antes: {count_before}")

        inserted = 0
        for ev in EVIDENCES:
            await conn.execute(INSERT_SQL, {
                "id": str(uuid.uuid4()),
                "cid": ev["cid"],
                "product_id": ev["product_id"],
                "snippet": ev["snippet"],
                "autor": ev["autor"],
                "referencia_completa": ev["referencia_completa"],
                "ano": ev["ano"],
                "tipo": ev["tipo"],
                "relevancia": ev["relevancia"],
                "created_at": datetime.now(timezone.utc),
            })
            inserted += 1
            print(f"  ✓ [{ev['cid']}] {ev['autor'][:45]:<45} | {ev['tipo']}")

        count_after = (await conn.execute(text("SELECT count(*) FROM clinical_evidences"))).scalar()
        print(f"\nInseridas: {inserted}")
        print(f"Total no banco: {count_after}")


if __name__ == "__main__":
    asyncio.run(main())
