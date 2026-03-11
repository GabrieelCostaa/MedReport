"""
Ingestão dos estudos locais de Estética → tabela clinical_evidences.

Cada entrada associa um snippet científico verificado a um Produto + CID,
permitindo que o Agente Pesquisador injete essas evidências automaticamente.

Uso:
    cd services/api
    python -m scripts.seed_estudos_estetica
"""
import asyncio
import uuid
from datetime import datetime

from sqlalchemy import text

from app.db.session import engine

# ─── IDs dos produtos (já existem no banco) ───────────────────────────
KIT_FO_LASER = "3215b856-0d5b-4ae1-93bf-5a5f41c1b57c"
KIT_EC2_ENXERTO = "6c58abf0-7206-40d0-8ee1-124e6187f4f7"

EVIDENCES = [
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. Levy et al. (2019) – One S.T.E.P. Technique™ / MSCs preservadas
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_FO_LASER,
        "cid": "L97",
        "snippet": (
            "A técnica One S.T.E.P.™ (laser diodo 1210 nm) não depende de lipólise e libera "
            "tanto adipócitos preservados quanto células-tronco mesenquimais (MSCs). As células "
            "isoladas expressaram CD29, CD90 e CD105, confirmando sua identidade como MSCs "
            "conforme critérios da ISCT, e diferenciaram-se em linhagens condrogênica, osteogênica "
            "e adipogênica."
        ),
        "autor": "Levy D et al.",
        "referencia_completa": (
            "Levy D, Mello L, Giglio PN, Centurion P, Vasquez MWM, Lopes LA, Bydlowski SP, "
            "Demange MK. One S.T.E.P. Technique™ is Efficient in Harvesting Mesenchymal Stem "
            "Cells from Human Adipose Tissue. Aesth Plast Surg. 2019;43:1122-1123. "
            "DOI: 10.1007/s00266-018-1110-5"
        ),
        "ano": "2019",
        "tipo": "experimental",
        "relevancia": "alta",
    },
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "L97",
        "snippet": (
            "A lipólise laser convencional destrói adipócitos e MSCs pelo efeito fototérmico "
            "intenso. A técnica One S.T.E.P.™ preserva 98% dos adipócitos e libera MSCs "
            "viáveis com capacidade de diferenciação trilinear, tornando o material adequado "
            "para enxerto composto e medicina regenerativa."
        ),
        "autor": "Levy D et al.",
        "referencia_completa": (
            "Levy D, Mello L, Giglio PN, Centurion P, Vasquez MWM, Lopes LA, Bydlowski SP, "
            "Demange MK. One S.T.E.P. Technique™ is Efficient in Harvesting Mesenchymal Stem "
            "Cells from Human Adipose Tissue. Aesth Plast Surg. 2019;43:1122-1123. "
            "DOI: 10.1007/s00266-018-1110-5"
        ),
        "ano": "2019",
        "tipo": "experimental",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. Centurión et al. (2020) – One STEP™ facial lipografting (245 pts)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_FO_LASER,
        "cid": "L90.5",
        "snippet": (
            "Em 245 pacientes submetidos a lipoenxertia facial com a técnica One STEP™ "
            "(laser 1210 nm), a atividade mitocondrial das ADSCs foi mais de 7x superior "
            "em amostras frescas comparadas à lipoaspiração convencional (SAL), aumentando "
            "para 12x após 24 horas de cultura. Resultados volumétricos e regenerativos "
            "excelentes sem hipercorreção."
        ),
        "autor": "Centurión P et al.",
        "referencia_completa": (
            "Centurión P, Gamarra R, Caballero G, Kaufmann P, Delgado P. Optimizing harvesting "
            "for facial lipografting with a new photochemical stimulation concept: One STEP technique™. "
            "Eur J Plast Surg. 2020. DOI: 10.1007/s00238-020-01643-x"
        ),
        "ano": "2020",
        "tipo": "coorte",
        "relevancia": "alta",
    },
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "L90.5",
        "snippet": (
            "O PicoGraft™ obtido pela técnica One STEP™ resulta em enxerto de gordura homogêneo, "
            "sem grumos, com alta concentração de ADSCs viáveis estimuladas e alto número de "
            "adipócitos viáveis. Melhora subjetiva na área periorbital observada a partir do "
            "segundo mês, com progressão até 12 meses."
        ),
        "autor": "Centurión P et al.",
        "referencia_completa": (
            "Centurión P, Gamarra R, Caballero G, Kaufmann P, Delgado P. Optimizing harvesting "
            "for facial lipografting with a new photochemical stimulation concept: One STEP technique™. "
            "Eur J Plast Surg. 2020. DOI: 10.1007/s00238-020-01643-x"
        ),
        "ano": "2020",
        "tipo": "coorte",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. Centurión P et al. (2018) – Letter: LAL vs 1210nm photochemistry
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_FO_LASER,
        "cid": "L97",
        "snippet": (
            "O laser de 1210 nm utiliza a propriedade fotoquímica (e não fototérmica), "
            "dissolvendo o tecido conectivo subcutâneo e liberando os adipócitos sem alterá-los, "
            "com preservação de 98%. Diferente dos lasers com afinidade por água (980 nm, 1440 nm), "
            "o comprimento de onda de 1210 nm tem afinidade pelo tecido rico em lipídios."
        ),
        "autor": "Centurion P, Caballero G, Weiss M",
        "referencia_completa": (
            "Centurion P, Caballero G, Weiss M. Comment to: 'Laser-Assisted Liposuction (LAL) "
            "Versus Traditional Liposuction: Systematic Review'. Aesth Plast Surg. "
            "2019;43:1122-1123. DOI: 10.1007/s00266-018-1110-5"
        ),
        "ano": "2018",
        "tipo": "carta-editorial",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. De Andrade et al. (2017) – PBM 808nm para dor neuropática
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_FO_LASER,
        "cid": "G62.9",
        "snippet": (
            "A fotobiomodulação com laser infravermelho em densidades de energia de 20 e "
            "40 J/cm² demonstrou redução significativa do limiar nociceptivo a partir do 30º dia "
            "de tratamento em modelo de constrição crônica do nervo ciático. A dosagem de "
            "β-endorfina foi significativamente elevada nos grupos de maior densidade energética."
        ),
        "autor": "de Andrade ALM et al.",
        "referencia_completa": (
            "de Andrade ALM, Bossini PS, do Canto De Souza ALM, Sanchez AD, Parizotto NA. "
            "Effect of photobiomodulation therapy (808 nm) in the control of neuropathic pain "
            "in mice. Lasers Med Sci. 2017. DOI: 10.1007/s10103-017-2186-x"
        ),
        "ano": "2017",
        "tipo": "experimental",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 5. Cotler et al. (2015) – LLLT for Musculoskeletal Pain (Review)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_FO_LASER,
        "cid": "M79.1",
        "snippet": (
            "Por mais de quarenta anos, a LLLT demonstrou reduzir inflamação e edema, "
            "induzir analgesia e promover cicatrização em uma gama de patologias musculoesqueléticas. "
            "O efeito é fotoquímico, não térmico: a luz desencadeia mudanças bioquímicas intracelulares "
            "comparáveis ao processo de fotossíntese em plantas."
        ),
        "autor": "Cotler HB et al.",
        "referencia_completa": (
            "Cotler HB, Chow RT, Hamblin MR, Carroll J. The Use of Low Level Laser Therapy "
            "(LLLT) For Musculoskeletal Pain. MOJ Orthop Rheumatol. 2015;2(5). "
            "DOI: 10.15406/mojor.2015.02.00068"
        ),
        "ano": "2015",
        "tipo": "revisao",
        "relevancia": "alta",
    },
    {
        "product_id": KIT_FO_LASER,
        "cid": "M54.5",
        "snippet": (
            "LLLT a 830 nm com dose de 3 J/ponto demonstrou alívio significativo da dor "
            "lombar crônica em ensaios clínicos randomizados. O mecanismo envolve supressão "
            "de mediadores inflamatórios (PGE2, IL-1β, TNF-α) e estímulo à produção de ATP "
            "mitocondrial via absorção pelo citocromo C oxidase."
        ),
        "autor": "Cotler HB et al.",
        "referencia_completa": (
            "Cotler HB, Chow RT, Hamblin MR, Carroll J. The Use of Low Level Laser Therapy "
            "(LLLT) For Musculoskeletal Pain. MOJ Orthop Rheumatol. 2015;2(5). "
            "DOI: 10.15406/mojor.2015.02.00068"
        ),
        "ano": "2015",
        "tipo": "revisao",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 6. De Andrade et al. (2016) – LLLT neuropathic pain systematic review
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_FO_LASER,
        "cid": "G62.9",
        "snippet": (
            "Revisão sistemática de 14 artigos (10 experimentais, 4 clínicos) demonstrou que "
            "a LLLT possui efeitos positivos no controle da analgesia para dor neuropática. "
            "Estudos experimentais revelaram melhores resultados com laser infravermelho em "
            "potências acima de 70 mW. Todos os estudos clínicos demonstraram eficácia da LLLT."
        ),
        "autor": "de Andrade ALM, Bossini PS, Parizotto NA",
        "referencia_completa": (
            "de Andrade ALM, Bossini PS, Parizotto NA. Use of low level laser therapy to control "
            "neuropathic pain: a systematic review. J Photochem Photobiol B. 2016. "
            "DOI: 10.1016/j.jphotobiol.2016.08.025"
        ),
        "ano": "2016",
        "tipo": "revisao-sistematica",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 7. Tapia-Rojas et al. (2020) – Protocolo de cultivo ASC do lipoaspirado
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "L97",
        "snippet": (
            "Protocolo padronizado para cultivo e identificação de células-tronco mesenquimais "
            "(ASCs) obtidas de lipoaspirado humano, incluindo caracterização imunofenotípica "
            "(CD73+, CD90+, CD105+), potencial de diferenciação trilinear e controle de qualidade. "
            "Confirma a viabilidade do tecido adiposo como fonte de MSCs para medicina regenerativa."
        ),
        "autor": "Tapia-Rojas S et al.",
        "referencia_completa": (
            "Tapia-Rojas S, Mayanga-Herrera A, Enciso-Gutiérrez J, Centurion P, Amiel-Pérez J. "
            "Procedimiento para el cultivo e identificación de células madre obtenidas de lipoaspirado "
            "humano con fines de investigación. Rev Peru Med Exp Salud Publica. 2020;37(3). "
            "DOI: 10.17843/rpmesp.2020.373.5201"
        ),
        "ano": "2020",
        "tipo": "experimental",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 8. Teixeira FF et al. (2021) – MSC/SVF em feridas vasculares crônicas
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "L97",
        "snippet": (
            "Em 7 pacientes vasculopatas e diabéticos com risco iminente de amputação, o transplante "
            "autólogo de MSCs derivadas do SVF do tecido adiposo via técnica One STEP™ resultou em "
            "0% de amputação maior (vs 25% na literatura) e 71% de fechamento completo da lesão "
            "em 8 meses. Neoangiogênese observada já na primeira troca de curativo (7 dias)."
        ),
        "autor": "Teixeira FF et al.",
        "referencia_completa": (
            "Teixeira FF, Teixeira MC, Lima VLC, Cabral DDL, Ferreira CJG, Centurion P, "
            "Freitas GM, Silva MO. Terapia com células-tronco mesenquimais derivadas da fração "
            "vascular estromal do tecido adiposo como tratamento adjuvante em feridas vasculares "
            "crônicas. Rev Angiologia Cirurgia Vascular SBACV-RJ. 2021;2."
        ),
        "ano": "2021",
        "tipo": "coorte",
        "relevancia": "alta",
    },
    {
        "product_id": KIT_FO_LASER,
        "cid": "L97",
        "snippet": (
            "Ao estimular o tecido com laser 1210 nm, realizou-se fotoestimulação na enzima "
            "colagenase endógena presente no tecido conectivo em estado quiescente, ativando-a "
            "e dissolvendo adesões. O efeito biomodulador residual promove angiogênese via "
            "liberação de VEGF e analgesia via liberação de opioides endógenos."
        ),
        "autor": "Teixeira FF et al.",
        "referencia_completa": (
            "Teixeira FF, Teixeira MC, Lima VLC, Cabral DDL, Ferreira CJG, Centurion P, "
            "Freitas GM, Silva MO. Terapia com células-tronco mesenquimais derivadas da fração "
            "vascular estromal do tecido adiposo como tratamento adjuvante em feridas vasculares "
            "crônicas. Rev Angiologia Cirurgia Vascular SBACV-RJ. 2021;2."
        ),
        "ano": "2021",
        "tipo": "coorte",
        "relevancia": "alta",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 9. Compilação técnica – Vantagens gerais da laserterapia (docx)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_FO_LASER,
        "cid": "M79.1",
        "snippet": (
            "A LTBI (laserterapia de baixa intensidade) exerce efeitos bioquímicos, bioelétricos "
            "e bioenergéticos: estimula produção de ATP intracelular, aumenta β-endorfina no "
            "líquor espinal, melhora microcirculação local, aumenta fluxo linfático, reduz edema "
            "e promove aumento de fibroblastos e síntese de colágeno no reparo tecidual."
        ),
        "autor": "Simunovic Z et al. (compilação)",
        "referencia_completa": (
            "Compilação técnica: Resumo sobre as vantagens da cirurgia a laser. "
            "Refs: Simunovic Z et al. (2000); Passarella S et al. (1984); Rocha Jr AM et al. (2006); "
            "Matera JM et al. (2003). Documento interno do parceiro."
        ),
        "ano": "2000",
        "tipo": "revisao",
        "relevancia": "media",
    },
    {
        "product_id": KIT_FO_LASER,
        "cid": "G62.9",
        "snippet": (
            "O laser reduz liberação de substâncias álgicas como bradicinina, histamina e "
            "acetilcolina. Aumenta excreção de serotonina e altera equilíbrio noradrenalina-adrenalina. "
            "Hiperpolarização da membrana nervosa via diminuição de permeabilidade Na/K eleva "
            "o limiar de dor, produzindo analgesia sustentada."
        ),
        "autor": "Simunovic Z (1996)",
        "referencia_completa": (
            "Simunovic Z. Low Level Laser Therapy with Trigger Points Technique: A Clinical Study "
            "on 243 Patients. J Clin Laser Med Surg. 1996;14(4):163-167. "
            "Citado em: Resumo sobre as vantagens da cirurgia a laser (doc. interno)."
        ),
        "ano": "1996",
        "tipo": "revisao",
        "relevancia": "media",
    },

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Extra: CIDs adicionais para maximizar cobertura do Kit FO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "product_id": KIT_FO_LASER,
        "cid": "L90.5",
        "snippet": (
            "O laser 1210 nm explora a propriedade fotoquímica da luz — análoga à fotossíntese — "
            "transformando energia luminosa em energia química estável, sem efeito fototérmico. "
            "Isso permite dissolução seletiva do tecido conectivo, preservação de 98% dos adipócitos "
            "e estimulação de ADSCs com atividade mitocondrial 7-12x superior à lipoaspiração "
            "convencional, ideal para rejuvenescimento facial."
        ),
        "autor": "Centurión P et al.",
        "referencia_completa": (
            "Centurión P, Gamarra R, Caballero G, Kaufmann P, Delgado P. Optimizing harvesting "
            "for facial lipografting with a new photochemical stimulation concept: One STEP technique™. "
            "Eur J Plast Surg. 2020. DOI: 10.1007/s00238-020-01643-x"
        ),
        "ano": "2020",
        "tipo": "coorte",
        "relevancia": "alta",
    },
    {
        "product_id": KIT_EC2_ENXERTO,
        "cid": "M79.3",
        "snippet": (
            "O SVF (Fração Vascular Estromal) do tecido adiposo possui todos os elementos na "
            "quantidade necessária para regenerar tecidos e cumpre integralmente os requisitos da "
            "ISCT para classificação de MSCs. O transplante autólogo de todos os componentes do "
            "coquetel regenerativo do SVF em conjunto mostrou-se beneficamente superior ao "
            "transplante celular isolado de laboratório."
        ),
        "autor": "Teixeira FF et al.",
        "referencia_completa": (
            "Teixeira FF et al. Terapia com células-tronco mesenquimais derivadas da fração "
            "vascular estromal do tecido adiposo como tratamento adjuvante em feridas vasculares "
            "crônicas. Rev Angiologia Cirurgia Vascular SBACV-RJ. 2021;2."
        ),
        "ano": "2021",
        "tipo": "coorte",
        "relevancia": "alta",
    },
]

INSERT_SQL = text("""
    INSERT INTO clinical_evidences (id, cid, product_id, snippet, autor, referencia_completa, ano, tipo, relevancia, created_at)
    VALUES (:id, :cid, :product_id, :snippet, :autor, :referencia_completa, :ano, :tipo, :relevancia, :created_at)
""")


async def main():
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
                "created_at": datetime.utcnow(),
            })
            inserted += 1
            print(f"  ✓ [{ev['cid']}] {ev['autor'][:40]}... → {ev['tipo']}")

        count_after = (await conn.execute(text("SELECT count(*) FROM clinical_evidences"))).scalar()
        print(f"\nInseridas: {inserted}")
        print(f"Total no banco: {count_after}")


if __name__ == "__main__":
    asyncio.run(main())
