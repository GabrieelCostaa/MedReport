"""
Few-shot examples per specialty for the Writer agent.

Each specialty has an approved OPME justification broken into the SAME 6 sections
as WriterOutput (quadro_clinico, falha_terapeutica, justificativa_tecnica,
evidencia_cientifica, risco_nao_realizacao, conclusao) plus diagnostico_resumo,
base_legal and referencias. The assistant example is serialized as JSON so the
Writer mimics BOTH the sectioned structure and the technical depth/length.
"""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Encerramento padrão reutilizável (Regra #6 do WRITER_SYSTEM).
_CONCLUSAO_PADRAO = (
    "Diante do exposto, com quadro clínico documentado, falha terapêutica comprovada, "
    "fundamentação técnica e respaldo científico, solicita-se a autorização do material "
    "indicado, por ser o tecnicamente adequado e clinicamente necessário ao paciente. "
    "A substituição deste material por opção de menor desempenho técnico transfere à "
    "operadora de saúde a responsabilidade integral por eventuais complicações clínicas, "
    "reoperações ou insucesso do desfecho cirúrgico, conforme responsabilidade civil "
    "profissional. Certos de vossa presteza, aguardamos a liberação."
)

_BASE_LEGAL_PADRAO = (
    "Nos termos da RN 424/2017 da ANS, cabe exclusivamente ao médico assistente a "
    "prerrogativa de determinar as características e a matéria-prima dos materiais (OPME). "
    "Os procedimentos indicados são de cobertura mínima obrigatória (RN 465/2021 e "
    "atualizações). Em caso de negativa, requer-se, com fundamento na RN 395/2016, "
    "justificativa técnica por escrito fundamentada em evidência científica de mesmo nível. "
    "Aplica-se ainda o Código de Ética Médica (Cap. I, item V)."
)


# ─── Specialty examples ───────────────────────────────────────────────────────
# Cada entry: {"user": <resumo do caso>, "assistant": {<WriterOutput em seções>}}

EXAMPLES = {
    "ortopedia": {
        "user": (
            "Diagnóstico: Gonartrose primária bilateral (CID M17.0)\n"
            "Material: Synvisc-One (hialuronato de alto peso molecular, 6.000 kDa)\n"
            "Código TUSS: 20104340\n"
            "Falha terapêutica: AINEs + fisioterapia por 14 semanas + 2 infiltrações de corticoide"
        ),
        "assistant": {
            "quadro_clinico": (
                "O paciente apresenta diagnóstico de gonartrose primária bilateral (CID M17.0), "
                "classificada como grau III na escala de Kellgren-Lawrence, com redução do espaço "
                "articular, esclerose subcondral e osteófitos marginais documentados radiograficamente. "
                "Clinicamente, evolui com dor mecânica de padrão progressivo, rigidez matinal e "
                "limitação funcional para atividades de vida diária, com escore WOMAC elevado. "
                "O quadro inflamatório crônico intra-articular, dominado por citocinas pró-inflamatórias "
                "(IL-1β, TNF-α), desencadeia uma cascata de degeneração autossustentada: a ativação "
                "persistente de metaloproteinases da matriz (MMP-13) acelera a degradação do colágeno "
                "tipo II e a apoptose dos condrócitos remanescentes, comprometendo de forma irreversível "
                "a homeostase da cartilagem articular e perpetuando o ciclo de dor e perda funcional."
            ),
            "falha_terapeutica": (
                "O paciente foi submetido a tratamento conservador estruturado e exaurido ao longo de "
                "14 semanas, incluindo anti-inflamatórios não esteroidais em dose plena, programa de "
                "fisioterapia cinesioterapêutica supervisionada e duas infiltrações intra-articulares "
                "de corticosteroide, sem melhora funcional sustentada. A refratariedade a essa conduta "
                "escalonada comprova o esgotamento das medidas clínicas de primeira e segunda linha e "
                "caracteriza a indicação da viscossuplementação como etapa terapêutica subsequente e "
                "tecnicamente apropriada."
            ),
            "justificativa_tecnica": (
                "A viscossuplementação com hialuronato de alto peso molecular (6.000 kDa) promove o "
                "reestabelecimento da homeostase articular e a viscoindução, restaurando as propriedades "
                "viscoelásticas do líquido sinovial degradado. Diferentemente dos hialuronatos lineares "
                "de baixo peso molecular, a rede tridimensional reticulada (cross-linked) do produto "
                "cria uma grade de proteção molecular que impede o acesso das hialuronidases — as enzimas "
                "responsáveis pela degradação do ácido hialurônico endógeno —, garantindo permanência "
                "intra-articular prolongada, enquanto formulações lineares são degradadas em poucas "
                "horas. Esse diferencial biomecânico traduz-se em modulação da nocicepção articular, "
                "efeito condroprotetor e prolongamento do intervalo terapêutico, características "
                "inexistentes em materiais de menor peso molecular ou não reticulados."
            ),
            "evidencia_cientifica": (
                "A eficácia da viscossuplementação com hialuronato de alto peso molecular na gonartrose "
                "sintomática está respaldada em evidência de nível 1. Meta-análise demonstrou melhora "
                "significativa da dor e da função articular frente ao placebo, com benefício sustentado "
                "por até 26 semanas (Altman et al., 2015). Revisão sistemática subsequente confirmou "
                "superioridade dos hialuronatos de alto peso molecular reticulados em relação às "
                "formulações lineares quanto à durabilidade do efeito clínico (Bannuru et al., 2019)."
            ),
            "risco_nao_realizacao": (
                "A não realização da viscossuplementação implica manutenção do ambiente bioquímico "
                "hostil e progressão da degeneração condral, com evolução esperada para gonartrose grau "
                "IV. Esse desfecho cursa com dor incapacitante, deformidade em varo/valgo e perda "
                "funcional irreversível, conduzindo à necessidade futura de artroplastia total de joelho "
                "— procedimento de maior porte, morbidade e tempo de reabilitação. A intervenção precoce "
                "com o material indicado visa justamente interromper essa progressão e postergar ou "
                "evitar a substituição articular protética."
            ),
            "conclusao": _CONCLUSAO_PADRAO,
            "diagnostico_resumo": "Gonartrose primária bilateral grau III (Kellgren-Lawrence), refratária a tratamento conservador.",
            "base_legal": _BASE_LEGAL_PADRAO,
            "referencias": ["Altman et al., 2015", "Bannuru et al., 2019"],
        },
    },
    "neurocirurgia": {
        "user": (
            "Diagnóstico: Hérnia discal lombar L4-L5 com radiculopatia (CID M51.1)\n"
            "Material: Cage intersomático PEEK\n"
            "Código TUSS: 30715016\n"
            "Falha terapêutica: 12 semanas de tratamento clínico + bloqueio foraminal"
        ),
        "assistant": {
            "quadro_clinico": (
                "O paciente apresenta hérnia discal lombar L4-L5 com radiculopatia compressiva associada "
                "(CID M51.1), confirmada por ressonância magnética que evidencia protrusão discal com "
                "compressão da raiz nervosa e redução do canal foraminal. Clinicamente, manifesta "
                "lombociatalgia de padrão dermatomérico, parestesia e déficit de força em grau inicial no "
                "território correspondente. A manutenção da compressão radicular perpetua um processo de "
                "sofrimento neural progressivo: o edema perineural e a isquemia axonal crônica desencadeiam "
                "desmielinização e degeneração walleriana, comprometendo de forma cumulativa a condução "
                "nervosa e a função motora e sensitiva do segmento acometido."
            ),
            "falha_terapeutica": (
                "O paciente foi submetido a tratamento conservador por 12 semanas, incluindo "
                "anti-inflamatórios não esteroidais, corticoterapia oral em curso, fisioterapia "
                "cinesioterapêutica e bloqueio foraminal guiado por fluoroscopia, sem melhora funcional "
                "sustentada. A persistência dos sintomas radiculares após terapêutica clínica e "
                "intervencionista minimamente invasiva caracteriza a refratariedade do quadro e a "
                "indicação da abordagem cirúrgica descompressiva com estabilização intersomática."
            ),
            "justificativa_tecnica": (
                "O cage intersomático em PEEK (poliéter-éter-cetona) apresenta módulo de elasticidade "
                "semelhante ao do osso cortical (~3,5 GPa), minimizando o efeito de stress-shielding que "
                "compromete a fusão óssea em dispositivos metálicos de maior rigidez. Sua radiotransparência "
                "permite avaliação fidedigna da consolidação da artrodese no seguimento por imagem, "
                "diferencial ausente em implantes metálicos que geram artefatos. A geometria anatômica do "
                "implante restaura a lordose segmentar e a altura discal, descomprimindo indiretamente o "
                "forame de conjugação, enquanto a superfície de contato porosa favorece a osteointegração "
                "e a formação de ponte óssea intersomática estável."
            ),
            "evidencia_cientifica": (
                "O uso do cage de PEEK na artrodese lombar intersomática está fundamentado em evidência "
                "consolidada. Estudos demonstram taxas de fusão e desfechos clínicos favoráveis com o "
                "dispositivo de PEEK, com perfil de osteointegração superior ao de alternativas metálicas "
                "rígidas (Nemoto et al., 2014). Diretrizes baseadas em evidência reforçam que a "
                "descompressão associada à estabilização é a conduta indicada na radiculopatia refratária "
                "com instabilidade segmentar (Kreiner et al., 2014)."
            ),
            "risco_nao_realizacao": (
                "A manutenção da compressão radicular sem descompressão adequada resulta em desmielinização "
                "progressiva e dano axonal irreversível, com evolução para déficit motor permanente, "
                "hipotrofia muscular e, nas formas mais graves, síndrome da cauda equina — emergência "
                "neurocirúrgica com sequelas esfincterianas. A postergação da intervenção reduz a janela "
                "de reversibilidade do dano neural e amplia a probabilidade de déficit definitivo, exigindo "
                "no futuro procedimentos de maior complexidade e menor prognóstico funcional."
            ),
            "conclusao": _CONCLUSAO_PADRAO,
            "diagnostico_resumo": "Hérnia discal L4-L5 com radiculopatia refratária a tratamento conservador e intervencionista.",
            "base_legal": _BASE_LEGAL_PADRAO,
            "referencias": ["Nemoto et al., 2014", "Kreiner et al., 2014"],
        },
    },
    "cirurgia_vascular": {
        "user": (
            "Diagnóstico: Úlcera venosa crônica MIE (CID L97)\n"
            "Material: Kit de terapia por pressão negativa (VAC)\n"
            "Código TUSS: 30911036"
        ),
        "assistant": {
            "quadro_clinico": (
                "Paciente portador de úlcera venosa crônica em membro inferior esquerdo (CID L97), com "
                "evolução de 18 meses, extensa área de perda tecidual, tecido de granulação exuberante "
                "porém friável e exsudato abundante. A estase venosa crônica mantém hipertensão no leito "
                "capilar, extravasamento de fibrinogênio e formação de manguito pericapilar, perpetuando "
                "hipóxia tecidual local, resposta inflamatória sustentada e falência do processo "
                "cicatricial fisiológico."
            ),
            "falha_terapeutica": (
                "A lesão mostrou-se refratária a desbridamentos seriados, terapia compressiva "
                "multicamadas e curativos bioativos aplicados de forma continuada ao longo do seguimento, "
                "sem progressão consistente da cicatrização. O esgotamento das medidas convencionais "
                "caracteriza a indicação de terapia avançada de estímulo ativo do leito da ferida."
            ),
            "justificativa_tecnica": (
                "A terapia por pressão negativa (TPN) promove macro e microdeformação do leito da ferida, "
                "estimulando angiogênese, proliferação de fibroblastos, formação de tecido de granulação "
                "e remoção contínua de exsudato contaminado e mediadores inflamatórios. O ambiente úmido "
                "e a redução do edema intersticial otimizam a perfusão capilar local, acelerando a "
                "contração da ferida — mecanismo ativo inexistente em curativos passivos convencionais."
            ),
            "evidencia_cientifica": (
                "O princípio da pressão negativa no manejo de feridas complexas foi estabelecido por "
                "Argenta e Morykwas (1997). Meta-análise subsequente demonstrou redução significativa do "
                "tempo de cicatrização em comparação com curativos convencionais (Dumville et al., 2015)."
            ),
            "risco_nao_realizacao": (
                "A não intervenção resulta em expansão progressiva da área ulcerada, infecção secundária "
                "com potencial evolução para osteomielite e sepse, além da necessidade futura de "
                "procedimento de maior morbidade, incluindo enxerto cutâneo ou amputação parcial do "
                "membro (Clarke, 2013)."
            ),
            "conclusao": _CONCLUSAO_PADRAO,
            "diagnostico_resumo": "Úlcera venosa crônica de MIE refratária a terapia compressiva e curativos convencionais.",
            "base_legal": _BASE_LEGAL_PADRAO,
            "referencias": ["Argenta e Morykwas, 1997", "Dumville et al., 2015", "Clarke, 2013"],
        },
    },
    "cirurgia_cardiaca": {
        "user": (
            "Diagnóstico: Estenose aórtica severa (CID I35.0)\n"
            "Material: Prótese valvar biológica\n"
            "Código TUSS: 30401011"
        ),
        "assistant": {
            "quadro_clinico": (
                "Paciente com estenose aórtica severa (CID I35.0), área valvar inferior a 1,0 cm² e "
                "gradiente médio superior a 40 mmHg ao ecocardiograma, sintomático com dispneia classe "
                "funcional III (NYHA) e episódio sincopal documentado. A sobrecarga pressórica crônica do "
                "ventrículo esquerdo induz hipertrofia miocárdica concêntrica que, mantida a obstrução, "
                "evolui para disfunção diastólica, fibrose intersticial e deterioração progressiva e "
                "irreversível da função contrátil."
            ),
            "falha_terapeutica": (
                "A estenose aórtica severa sintomática não possui tratamento clínico modificador de "
                "história natural; a terapêutica medicamentosa tem caráter apenas paliativo e não impede "
                "a progressão da obstrução valvar. O surgimento de sintomas define, por si, a indicação de "
                "substituição valvar, sendo a conduta expectante associada a elevado risco de mortalidade."
            ),
            "justificativa_tecnica": (
                "A prótese valvar biológica de pericárdio bovino com tratamento anti-calcificação "
                "apresenta perfil hemodinâmico otimizado, com baixo gradiente transvalvar residual e "
                "durabilidade prolongada na faixa etária indicada, eliminando a necessidade de "
                "anticoagulação oral permanente exigida pelas próteses mecânicas — diferencial relevante "
                "na redução do risco hemorrágico e tromboembólico do paciente."
            ),
            "evidencia_cientifica": (
                "A durabilidade e o desempenho das próteses biológicas de pericárdio bovino estão "
                "documentados em séries de longo seguimento (Bourguignon et al., 2015). A história natural "
                "adversa da estenose aórtica severa sintomática e o benefício da intervenção estão "
                "consolidados em diretriz internacional (Otto et al., 2021)."
            ),
            "risco_nao_realizacao": (
                "A história natural da estenose aórtica severa sintomática sem intervenção cursa com "
                "mortalidade de aproximadamente 50% em 2 anos e risco de morte súbita cardíaca "
                "(Otto et al., 2021). A progressão para insuficiência cardíaca descompensada e dano "
                "miocárdico irreversível torna mandatória a intervenção precoce."
            ),
            "conclusao": _CONCLUSAO_PADRAO,
            "diagnostico_resumo": "Estenose aórtica severa sintomática (NYHA III) com indicação de troca valvar.",
            "base_legal": _BASE_LEGAL_PADRAO,
            "referencias": ["Bourguignon et al., 2015", "Otto et al., 2021"],
        },
    },
    "urologia": {
        "user": (
            "Diagnóstico: Doença de Peyronie com curvatura > 30° (CID N48.6)\n"
            "Material: Enxerto de pericárdio bovino para tunical grafting\n"
            "Código TUSS: 31301037"
        ),
        "assistant": {
            "quadro_clinico": (
                "Paciente portador de doença de Peyronie (CID N48.6) com curvatura peniana documentada "
                "superior a 30° ao ultrassom com Doppler, associada a placa fibrótica túnica albugínea "
                "estável. A deposição progressiva de colágeno desorganizado na túnica albugínea reduz sua "
                "elasticidade, agravando a deformidade e comprometendo a função erétil e a capacidade de "
                "penetração."
            ),
            "falha_terapeutica": (
                "O quadro mostrou-se refratário ao tratamento conservador com injeções intralesionais de "
                "colagenase e verapamil e terapia de tração, mantidos por cerca de 12 meses, sem correção "
                "satisfatória da curvatura. A estabilização da placa e a persistência da deformidade "
                "funcional caracterizam a indicação de correção cirúrgica com enxertia."
            ),
            "justificativa_tecnica": (
                "A tunical grafting com enxerto de pericárdio bovino permite a correção da curvatura com "
                "preservação do comprimento peniano, evitando o encurtamento inerente às técnicas de "
                "plicatura. O scaffold colágeno do pericárdio bovino atua como arcabouço para integração "
                "tecidual e neovascularização no sítio da placa fibrótica, oferecendo resistência mecânica "
                "adequada e baixa taxa de retração do enxerto."
            ),
            "evidencia_cientifica": (
                "A técnica de enxertia na doença de Peyronie apresenta elevada taxa de retificação da "
                "curvatura em séries clínicas (Levine et al., 2015). O comportamento do scaffold de "
                "pericárdio bovino quanto à integração tecidual foi descrito por Egydio et al. (2013)."
            ),
            "risco_nao_realizacao": (
                "Sem intervenção, a progressão natural resulta em agravamento da curvatura, disfunção "
                "erétil, impossibilidade de relação sexual e impacto psicológico significativo, com "
                "prejuízo à qualidade de vida do paciente."
            ),
            "conclusao": _CONCLUSAO_PADRAO,
            "diagnostico_resumo": "Doença de Peyronie com curvatura > 30° refratária a tratamento conservador.",
            "base_legal": _BASE_LEGAL_PADRAO,
            "referencias": ["Levine et al., 2015", "Egydio et al., 2013"],
        },
    },
    "cirurgia_plastica": {
        "user": (
            "Diagnóstico: Reconstrução mamária pós-mastectomia (CID N60.9)\n"
            "Material: Expansor tissular e prótese de silicone\n"
            "Código TUSS: 30802060"
        ),
        "assistant": {
            "quadro_clinico": (
                "Paciente submetida a mastectomia radical modificada por neoplasia maligna da mama "
                "(CID N60.9), em programa de reconstrução mamária. A ausência do complexo mamário resulta "
                "em assimetria torácica, retração cicatricial e déficit de cobertura cutânea, com impacto "
                "direto sobre a autoimagem, a qualidade de vida e a reintegração psicossocial da paciente."
            ),
            "falha_terapeutica": (
                "A reconstrução mamária integra o tratamento oncológico e não possui alternativa clínica "
                "conservadora que restaure o volume e o contorno mamários. A abordagem em dois tempos com "
                "expansor seguido de prótese é a conduta indicada quando o envelope cutâneo remanescente é "
                "insuficiente para a colocação imediata do implante definitivo."
            ),
            "justificativa_tecnica": (
                "O expansor tissular permite a distensão progressiva e controlada do complexo "
                "musculocutâneo, criando espaço adequado para a prótese definitiva de silicone. A prótese "
                "de superfície texturizada e alto índice de coesividade do gel reduz a incidência de "
                "contratura capsular e o risco de rippling, com melhor manutenção da forma e estabilidade "
                "do implante ao longo do tempo."
            ),
            "evidencia_cientifica": (
                "A reconstrução com expansor/implante apresenta elevada taxa de satisfação em comparação "
                "com técnicas alternativas (Tan et al., 2022). O uso de superfície texturizada associou-se "
                "a menor taxa de contratura capsular Baker III/IV frente a implantes lisos "
                "(Centurión-Rivas et al., 2021)."
            ),
            "risco_nao_realizacao": (
                "A não realização da reconstrução perpetua a deformidade torácica e o prejuízo funcional e "
                "psicológico decorrente da mastectomia, com repercussão sobre a autoimagem, a saúde mental "
                "e a reinserção social da paciente, comprometendo a integralidade do tratamento oncológico."
            ),
            "conclusao": _CONCLUSAO_PADRAO,
            "diagnostico_resumo": "Reconstrução mamária pós-mastectomia por neoplasia maligna da mama.",
            "base_legal": _BASE_LEGAL_PADRAO,
            "referencias": ["Tan et al., 2022", "Centurión-Rivas et al., 2021"],
        },
    },
    "ginecologia": {
        "user": (
            "Diagnóstico: Prolapso genital grau III (CID N81.2)\n"
            "Material: Tela de polipropileno para sacrocolpopexia\n"
            "Código TUSS: 31401070"
        ),
        "assistant": {
            "quadro_clinico": (
                "Paciente com prolapso genital grau III (CID N81.2) na classificação POP-Q, com cistocele "
                "e retocele associadas, sintomática com sensação de peso perineal, abaulamento vaginal e "
                "incontinência urinária de esforço. O enfraquecimento progressivo do assoalho pélvico e da "
                "fáscia endopélvica compromete o suporte dos órgãos pélvicos e tende a agravar-se sem "
                "correção estrutural."
            ),
            "falha_terapeutica": (
                "As medidas conservadoras — fisioterapia do assoalho pélvico e uso de pessário — foram "
                "insuficientes para o controle sintomático e a correção anatômica no grau de prolapso "
                "apresentado, caracterizando a indicação de correção cirúrgica com suporte protético."
            ),
            "justificativa_tecnica": (
                "A sacrocolpopexia com tela de polipropileno macroporosa tipo I oferece suporte apical "
                "durável e restauração do eixo vaginal fisiológico. A macroporosidade (poro superior a "
                "75 μm) permite infiltração fibroblástica, integração tecidual e colonização por "
                "macrófagos, reduzindo o risco de exposição e infecção da tela em comparação com materiais "
                "microporosos, com desempenho superior à colporrafia isolada."
            ),
            "evidencia_cientifica": (
                "A sacrocolpopexia com tela apresenta taxa de cura anatômica superior à colporrafia "
                "anterior isolada em seguimento de longo prazo (Maher et al., 2016). O perfil de "
                "integração e segurança das telas macroporosas foi descrito por Nygaard et al. (2013)."
            ),
            "risco_nao_realizacao": (
                "A progressão do prolapso sem correção evolui para exteriorização permanente, ulceração e "
                "infecção da mucosa exposta, agravamento da incontinência e necessidade futura de "
                "procedimento de maior morbidade."
            ),
            "conclusao": _CONCLUSAO_PADRAO,
            "diagnostico_resumo": "Prolapso genital grau III (POP-Q) sintomático com indicação de sacrocolpopexia.",
            "base_legal": _BASE_LEGAL_PADRAO,
            "referencias": ["Maher et al., 2016", "Nygaard et al., 2013"],
        },
    },
    "oftalmologia": {
        "user": (
            "Diagnóstico: Catarata senil nuclear grau III (CID H25.1)\n"
            "Material: Lente intraocular dobrável monofocal\n"
            "Código TUSS: 30401012"
        ),
        "assistant": {
            "quadro_clinico": (
                "Paciente com catarata senil nuclear grau III (CID H25.1), classificação LOCS III NO3-NC3, "
                "com acuidade visual corrigida de 20/80 no olho afetado, com impacto sobre atividades de "
                "vida diária e direção veicular. A opacificação progressiva do cristalino reduz a "
                "transmitância luminosa e a qualidade da imagem retiniana, evoluindo de forma irreversível "
                "sem tratamento cirúrgico."
            ),
            "falha_terapeutica": (
                "A catarata não possui tratamento clínico ou farmacológico capaz de reverter a "
                "opacificação do cristalino; a facoemulsificação com implante de lente intraocular é a "
                "única conduta resolutiva. A correção óptica externa não compensa o grau de opacidade "
                "apresentado, caracterizando a indicação cirúrgica."
            ),
            "justificativa_tecnica": (
                "A lente intraocular dobrável monofocal acrílica hidrofóbica apresenta baixa taxa de "
                "opacificação capsular posterior e excelente biocompatibilidade, com desenho de bordas "
                "quadradas que inibe a migração de células epiteliais. O perfil asférico compensa a "
                "aberração esférica positiva da córnea, otimizando a qualidade visual e a sensibilidade ao "
                "contraste — diferencial ausente em lentes esféricas de PMMA."
            ),
            "evidencia_cientifica": (
                "As lentes acrílicas hidrofóbicas apresentam menor taxa de opacificação capsular posterior "
                "frente a materiais alternativos (Findl et al., 2010). O benefício óptico do desenho "
                "asférico sobre a sensibilidade ao contraste foi descrito por Bellucci et al. (2012)."
            ),
            "risco_nao_realizacao": (
                "Sem intervenção, a progressão para catarata madura resulta em cegueira funcional "
                "reversível, com risco de complicações como glaucoma facomórfico ou facolítico e maior "
                "complexidade cirúrgica futura."
            ),
            "conclusao": _CONCLUSAO_PADRAO,
            "diagnostico_resumo": "Catarata senil nuclear grau III com baixa acuidade visual e indicação de facoemulsificação.",
            "base_legal": _BASE_LEGAL_PADRAO,
            "referencias": ["Findl et al., 2010", "Bellucci et al., 2012"],
        },
    },
    "otorrinolaringologia": {
        "user": (
            "Diagnóstico: Hipertrofia de cornetos inferiores refratária (CID J34.3)\n"
            "Material: Radiofrequência para turbinectomia submucosa\n"
            "Código TUSS: 30901016"
        ),
        "assistant": {
            "quadro_clinico": (
                "Paciente com hipertrofia de cornetos inferiores (CID J34.3), com obstrução nasal "
                "bilateral documentada por rinomanometria e repercussão sobre a qualidade do sono e o "
                "desempenho diurno. A hipertrofia crônica da mucosa e do estroma turbinal reduz a área "
                "respiratória nasal, mantendo resistência aumentada ao fluxo aéreo e respiração oral "
                "compensatória."
            ),
            "falha_terapeutica": (
                "O quadro mostrou-se refratário ao tratamento clínico com corticosteroide nasal tópico e "
                "anti-histamínicos por mais de 12 semanas, sem alívio sustentado da obstrução. O "
                "esgotamento da terapia clínica caracteriza a indicação de redução volumétrica cirúrgica "
                "do corneto."
            ),
            "justificativa_tecnica": (
                "A turbinectomia submucosa por radiofrequência bipolar promove redução volumétrica do "
                "corneto inferior preservando a mucosa superficial e a função ciliar mucociliar, "
                "diferencial fundamental em relação à turbinectomia parcial clássica. A técnica cursa com "
                "menor sangramento intraoperatório, menor crostificação pós-operatória e recuperação "
                "funcional mais rápida."
            ),
            "evidencia_cientifica": (
                "A radiofrequência submucosa demonstrou redução volumétrica efetiva do corneto inferior "
                "(Cavaliere et al., 2014), com menor morbidade pós-operatória em comparação com técnicas "
                "ablativas convencionais (Liu et al., 2009)."
            ),
            "risco_nao_realizacao": (
                "A obstrução nasal crônica sem tratamento perpetua a respiração oral, predispõe à síndrome "
                "da apneia obstrutiva do sono e, a longo prazo, associa-se a repercussões cardiovasculares "
                "e hipertensão pulmonar."
            ),
            "conclusao": _CONCLUSAO_PADRAO,
            "diagnostico_resumo": "Hipertrofia de cornetos inferiores refratária a tratamento clínico, com obstrução nasal documentada.",
            "base_legal": _BASE_LEGAL_PADRAO,
            "referencias": ["Cavaliere et al., 2014", "Liu et al., 2009"],
        },
    },
    "cirurgia_geral": {
        "user": (
            "Diagnóstico: Hérnia incisional recidivante (CID K43.1)\n"
            "Material: Tela de polipropileno macroporosa para herniorrafia\n"
            "Código TUSS: 31009107"
        ),
        "assistant": {
            "quadro_clinico": (
                "Paciente com hérnia incisional recidivante (CID K43.1), com defeito aponeurótico superior "
                "a 10 cm documentado por tomografia, após falha de reparo primário prévio. A perda de "
                "domicílio parcial do conteúdo abdominal e o enfraquecimento progressivo da parede "
                "comprometem a mecânica abdominal e elevam o risco de complicações agudas."
            ),
            "falha_terapeutica": (
                "O reparo primário prévio, sem reforço protético, evoluiu com recidiva do defeito, "
                "comprovando a insuficiência da sutura direta em defeitos amplos e caracterizando a "
                "indicação de reparo com tela em posição retromuscular."
            ),
            "justificativa_tecnica": (
                "A herniorrafia com tela de polipropileno macroporosa (poro superior a 1 mm, baixa "
                "gramatura) em posição retromuscular pela técnica de Rives-Stoppa distribui a tensão sobre "
                "a parede abdominal e favorece a integração tecidual. A macroporosidade promove "
                "infiltração celular e fibrose organizada, reduzindo o risco de encapsulamento, seroma "
                "crônico e infecção do material em relação a telas microporosas de alta densidade."
            ),
            "evidencia_cientifica": (
                "O reparo com tela reduz de forma significativa a recidiva em comparação com o reparo "
                "primário sem reforço (Luijendijk et al., 2000). O comportamento biológico das telas "
                "macroporosas de baixa gramatura foi descrito por Klinge et al. (2012)."
            ),
            "risco_nao_realizacao": (
                "A não correção resulta em progressão do defeito herniário, aumento do risco de "
                "encarceramento e estrangulamento visceral — condições de urgência com elevada morbidade e "
                "necessidade de cirurgia de maior porte."
            ),
            "conclusao": _CONCLUSAO_PADRAO,
            "diagnostico_resumo": "Hérnia incisional recidivante com defeito > 10 cm após falha de reparo primário.",
            "base_legal": _BASE_LEGAL_PADRAO,
            "referencias": ["Luijendijk et al., 2000", "Klinge et al., 2012"],
        },
    },

}

# Aliases para variações de nome de especialidade
# Exemplo neutro usado quando a especialidade não mapeia para nenhum dos 10
# exemplares acima. Propositalmente SEM mecanismo de ação de categoria alguma:
# ensina a estrutura das 6 seções, o encadeamento (propriedade → efeito →
# limitação da alternativa) e o padrão de citação, deixando o conteúdo técnico
# vir da ficha do produto e das evidências do caso.
_FALLBACK_KEY = "_generico"

EXAMPLES[_FALLBACK_KEY] = {
    "user": (
        "Diagnóstico: [patologia do paciente com estadiamento]\n"
        "CID: [código]\n"
        "Material: [produto solicitado]\n"
    ),
    "assistant": {
        "quadro_clinico": (
            "O paciente apresenta diagnóstico de [patologia] (CID [código]), em estágio "
            "[estadiamento conforme classificação aplicável], confirmado por [exame informado pelo médico]. "
            "O quadro cursa com [manifestações clínicas relatadas], com repercussão funcional "
            "documentada em [limitação descrita pelo médico]. A condição encontra-se em curso há "
            "[tempo informado], período em que houve progressão [do achado objetivo relatado]. "
            "A ausência de intervenção mantém ativo o processo [fisiopatológico próprio desta patologia, "
            "descrito em termos clínicos], cuja evolução esperada é a perda funcional progressiva do "
            "segmento acometido, com repercussão sobre [atividade funcional pertinente ao caso]."
        ),
        "falha_terapeutica": (
            "Foram esgotadas as alternativas conservadoras aplicáveis a este quadro. O paciente foi "
            "submetido a [tratamentos informados pelo médico], pelo período de [duração informada], "
            "sem obtenção de [desfecho esperado]. A ausência de resposta após [tempo] de conduta "
            "conservadora bem conduzida caracteriza refratariedade, e não insuficiência de tempo de "
            "tratamento. Mantida a conduta atual, não há expectativa de modificação do curso natural "
            "da doença, o que fundamenta a indicação da intervenção proposta."
        ),
        "justificativa_tecnica": (
            "O material solicitado apresenta [propriedade constante da ficha técnica], característica "
            "que determina [efeito biológico ou mecânico dessa propriedade no tecido-alvo deste "
            "diagnóstico]. Essa propriedade é o que permite [função clínica pretendida no caso]. "
            "Alternativas que não dispõem dessa característica não asseguram [função correspondente], "
            "o que neste paciente implicaria [consequência clínica concreta]. "
            "Adicionalmente, [segunda propriedade da ficha] confere [efeito correspondente], relevante "
            "porque [razão ligada ao quadro do paciente]. O conjunto dessas características define a "
            "adequação técnica do material a esta indicação específica, e não a uma categoria genérica."
        ),
        "evidencia_cientifica": (
            "A literatura disponível sustenta a indicação. [Achado do estudo fornecido] "
            "([Autor] et al., [ano]). O mesmo desfecho foi observado em [descrição do segundo estudo] "
            "([Autor] et al., [ano]). Os resultados são consistentes com o perfil do paciente descrito "
            "acima, no que se refere a [característica clínica comum]. Cada afirmação desta seção "
            "corresponde a uma evidência efetivamente fornecida, com autor e ano explícitos."
        ),
        "risco_nao_realizacao": (
            "A não realização do procedimento mantém o paciente exposto à progressão natural da "
            "patologia. Espera-se [evolução clínica esperada para esta condição], com agravamento de "
            "[manifestação atual] e perda funcional adicional. A progressão para estágio mais avançado "
            "tende a exigir procedimento de maior porte e morbidade, com recuperação mais prolongada e "
            "resultado funcional inferior ao esperado na intervenção realizada no momento atual."
        ),
        "conclusao": (
            "Pelo exposto, a indicação do material está fundamentada no quadro clínico documentado, na "
            "refratariedade ao tratamento conservador e nas propriedades técnicas do produto aplicáveis "
            "a esta condição. A substituição deste material por opção de menor desempenho técnico "
            "transfere à operadora de saúde a responsabilidade integral por eventuais complicações "
            "clínicas, reoperações ou insucesso do desfecho cirúrgico, conforme responsabilidade civil "
            "profissional. Certos de vossa presteza, aguardamos a liberação."
        ),
        "diagnostico_resumo": "[Patologia com estadiamento e lateralidade, conforme informado]",
        "base_legal": _BASE_LEGAL_PADRAO,
        "referencias": ["[Autor] et al., [ano]"],
    },
}


_SPECIALTY_ALIASES = {
    "ortopedia": "ortopedia",
    "traumatologia": "ortopedia",
    "ortopedia e traumatologia": "ortopedia",
    "neurocirurgia": "neurocirurgia",
    "neurologia": "neurocirurgia",
    "coluna": "neurocirurgia",
    "cirurgia vascular": "cirurgia_vascular",
    "vascular": "cirurgia_vascular",
    "angiologia": "cirurgia_vascular",
    "cirurgia cardiovascular": "cirurgia_cardiaca",
    "cardiologia": "cirurgia_cardiaca",
    "cardíaca": "cirurgia_cardiaca",
    "urologia": "urologia",
    "andrologia": "urologia",
    "cirurgia plástica": "cirurgia_plastica",
    "plástica": "cirurgia_plastica",
    "cirurgia plástica reparadora": "cirurgia_plastica",
    "mastologia": "cirurgia_plastica",
    "ginecologia": "ginecologia",
    "uroginecologia": "ginecologia",
    "ginecologia e obstetrícia": "ginecologia",
    "oftalmologia": "oftalmologia",
    "otorrinolaringologia": "otorrinolaringologia",
    "otorrino": "otorrinolaringologia",
    "orl": "otorrinolaringologia",
    "cirurgia geral": "cirurgia_geral",
    "cirurgia do aparelho digestivo": "cirurgia_geral",
    "cirurgia abdominal": "cirurgia_geral",
}


def get_few_shot_messages(especialidade: str = "") -> list[dict]:
    """
    Returns few-shot example messages for the Writer agent based on specialty.

    The assistant example is serialized as JSON matching the WriterOutput schema
    (6 sections + diagnostico_resumo + base_legal + referencias), so the model
    mimics the sectioned structure, citation style and technical depth.

    Returns a list with a single [user, assistant] message pair, or [] if the
    specialty has no example.
    """
    if not especialidade:
        return []

    key = _SPECIALTY_ALIASES.get(especialidade.lower().strip())
    if not key:
        # Try partial match
        esp_lower = especialidade.lower()
        for alias, mapped in _SPECIALTY_ALIASES.items():
            if alias in esp_lower or esp_lower in alias:
                key = mapped
                break

    if not key or key not in EXAMPLES:
        # Sem exemplo da especialidade, o Redator ficava SEM nenhum modelo de
        # profundidade — e é justamente aí que a seção longa vira padding
        # genérico. O fallback ensina a ESTRUTURA e o registro de linguagem sem
        # plantar mecanismo de nenhuma especialidade específica.
        key = _FALLBACK_KEY

    example = EXAMPLES[key]
    assistant_content = example["assistant"]
    # Backward-compat: if an example is still a plain string, wrap as-is.
    if isinstance(assistant_content, dict):
        assistant_content = json.dumps(assistant_content, ensure_ascii=False)

    return [
        {"role": "user", "content": example["user"]},
        {"role": "assistant", "content": assistant_content},
    ]
