"""
Few-shot examples per specialty for the Writer agent.

Each specialty has a compact example of an approved OPME justification
that demonstrates the expected tone, structure, and citation style.
The Writer uses these as context to mimic the writing pattern.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Specialty examples ───────────────────────────────────────────────────────
# Each entry: (user_message_summary, approved_output_excerpt)

EXAMPLES = {
    "ortopedia": {
        "user": (
            "Diagnóstico: Gonartrose primária bilateral (CID M17.0)\n"
            "Material: Synvisc-One (hialuronato de alto peso molecular)\n"
            "Código TUSS: 20104340"
        ),
        "assistant": (
            "Paciente apresenta diagnóstico de gonartrose primária bilateral (CID M17.0), "
            "classificada como grau III na escala de Kellgren-Lawrence, com comprometimento "
            "progressivo da função articular e falência das medidas conservadoras. "
            "O quadro inflamatório crônico intra-articular, dominado por citocinas "
            "pró-inflamatórias (IL-1β, TNF-α), resulta em degradação acelerada da "
            "matriz extracelular cartilaginosa e apoptose dos condrócitos remanescentes. "
            "A viscossuplementação com hialuronato de alto peso molecular (6.000 kDa) "
            "promove reestabelecimento da homeostase articular e viscoindução, restaurando "
            "as propriedades viscoelásticas do líquido sinovial (Altman et al., 2015). "
            "A rede tridimensional reticulada (cross-linked) confere resistência à "
            "degradação enzimática por hialuronidases, garantindo permanência intra-articular "
            "prolongada — diferencial técnico inexistente em formulações lineares de baixo "
            "peso molecular (Bannuru et al., 2019)."
        ),
    },
    "neurocirurgia": {
        "user": (
            "Diagnóstico: Hérnia discal lombar L4-L5 com radiculopatia (CID M51.1)\n"
            "Material: Cage intersomático PEEK\n"
            "Código TUSS: 30715016"
        ),
        "assistant": (
            "Paciente com diagnóstico de hérnia discal lombar L4-L5 com radiculopatia "
            "associada (CID M51.1), refratário à conduta clínica conservadora após 12 semanas "
            "de tratamento incluindo AINEs, corticoterapia oral, fisioterapia cinesioterapêutica "
            "e bloqueio foraminal guiado por fluoroscopia, sem melhora funcional sustentada. "
            "O cage intersomático em PEEK (poliéter-éter-cetona) apresenta módulo de elasticidade "
            "semelhante ao osso cortical (~3.5 GPa), minimizando o efeito stress-shielding que "
            "compromete a fusão em dispositivos metálicos. A geometria anatômica do implante "
            "restaura a lordose segmentar e a altura discal, com superfície de contato porosa "
            "que favorece a osteointegração (Nemoto et al., 2014). A manutenção da compressão "
            "radicular sem descompressão adequada resulta em desmielinização progressiva, "
            "com evolução para déficit motor permanente e síndrome da cauda equina "
            "(Kreiner et al., 2014)."
        ),
    },
    "cirurgia_vascular": {
        "user": (
            "Diagnóstico: Úlcera venosa crônica MIE (CID L97)\n"
            "Material: Kit de terapia por pressão negativa (VAC)\n"
            "Código TUSS: 30911036"
        ),
        "assistant": (
            "Paciente portador de úlcera venosa crônica em membro inferior esquerdo "
            "(CID L97), com evolução de 18 meses, refratária a desbridamentos seriados, "
            "terapia compressiva multicamadas e curativos bioativos. A terapia por pressão "
            "negativa (TPN) promove macro e microdeformação do leito da ferida, estimulando "
            "angiogênese, proliferação de fibroblastos e remoção contínua de exsudato "
            "contaminado (Argenta e Morykwas, 1997). Meta-análise demonstrou redução de "
            "43% no tempo de cicatrização em comparação com curativos convencionais "
            "(Dumville et al., 2015). A não intervenção resulta em expansão progressiva da "
            "área ulcerada, infecção secundária com potencial osteomielítico e necessidade "
            "futura de procedimento de maior morbidade, incluindo enxerto cutâneo ou "
            "amputação parcial (Clarke, 2013)."
        ),
    },
    "cirurgia_cardiaca": {
        "user": (
            "Diagnóstico: Estenose aórtica severa (CID I35.0)\n"
            "Material: Prótese valvar biológica\n"
            "Código TUSS: 30401011"
        ),
        "assistant": (
            "Paciente com diagnóstico de estenose aórtica severa (CID I35.0), "
            "área valvar < 1.0 cm², gradiente médio > 40 mmHg, com dispneia classe "
            "funcional III (NYHA) e episódio sincopal documentado. A prótese valvar "
            "biológica de pericárdio bovino com tratamento anti-calcificação apresenta "
            "durabilidade superior a 15 anos em pacientes > 65 anos, com perfil hemodinâmico "
            "otimizado que elimina a necessidade de anticoagulação oral permanente "
            "(Bourguignon et al., 2015). A história natural da estenose aórtica severa "
            "sintomática sem intervenção cursa com mortalidade de 50% em 2 anos e risco "
            "de morte súbita cardíaca (Otto et al., 2021). A progressão para insuficiência "
            "cardíaca descompensada e dano miocárdico irreversível torna mandatória a "
            "intervenção precoce."
        ),
    },
    "urologia": {
        "user": (
            "Diagnóstico: Doença de Peyronie com curvatura > 30° (CID N48.6)\n"
            "Material: Enxerto de pericárdio bovino para tunical grafting\n"
            "Código TUSS: 31301037"
        ),
        "assistant": (
            "Paciente portador de doença de Peyronie (CID N48.6) com curvatura "
            "peniana documentada > 30° ao ultrassom com Doppler, refratária ao "
            "tratamento conservador com injeções intralesionais de colagenase e "
            "verapamil por 12 meses. A tunical grafting com enxerto de pericárdio "
            "bovino permite correção da curvatura com preservação do comprimento "
            "peniano, apresentando taxa de sucesso de 85-92% na retificação "
            "(Levine et al., 2015). O scaffold colágeno do pericárdio bovino "
            "favorece a integração tecidual e neovascularização no sítio da placa "
            "fibrótica (Egydio et al., 2013). Sem intervenção, a progressão natural "
            "resulta em agravamento da curvatura, impossibilidade de relação sexual "
            "e impacto psicológico significativo."
        ),
    },
    "cirurgia_plastica": {
        "user": (
            "Diagnóstico: Cicatriz pós-mastectomia com reconstrução mamária (CID N60.9)\n"
            "Material: Expansor tissular e prótese de silicone\n"
            "Código TUSS: 30802060"
        ),
        "assistant": (
            "Paciente submetida a mastectomia radical modificada por neoplasia "
            "maligna da mama (CID N60.9), em programa de reconstrução mamária "
            "tardia. O expansor tissular permite distensão progressiva do complexo "
            "musculocutâneo, criando espaço para a prótese definitiva de silicone "
            "com superfície texturizada de alta coesividade. Meta-análise de Tan "
            "et al. (2022) demonstrou taxa de satisfação de 89% em reconstrução "
            "com expansor/implante versus 78% com retalho autólogo. A texturização "
            "da superfície reduz a taxa de contratura capsular (Baker III/IV) para "
            "3.8% versus 15% em implantes lisos (Centurión-Rivas et al., 2021). "
            "A não reconstrução impacta diretamente a autoimagem, qualidade de vida "
            "e reintegração social da paciente."
        ),
    },
    "ginecologia": {
        "user": (
            "Diagnóstico: Prolapso genital grau III (CID N81.2)\n"
            "Material: Tela de polipropileno para sacrocolpopexia\n"
            "Código TUSS: 31401070"
        ),
        "assistant": (
            "Paciente com diagnóstico de prolapso genital grau III (CID N81.2) "
            "na classificação POP-Q, com cistocele e retocele associadas, "
            "sintomática com sensação de peso perineal e incontinência urinária "
            "de esforço. A sacrocolpopexia com tela de polipropileno macroporosa "
            "tipo I apresenta taxa de cura anatômica de 91% em seguimento de 5 "
            "anos, superior à colporrafia anterior isolada (58%) conforme "
            "meta-análise de Maher et al. (2016). A macroporosidade (poro > 75μm) "
            "permite infiltração fibroblástica e integração tecidual adequada, "
            "reduzindo taxa de exposição de tela para < 4% (Nygaard et al., 2013). "
            "A progressão do prolapso sem correção evolui para ulceração, infecção "
            "e necessidade de procedimento de maior morbidade."
        ),
    },
    "oftalmologia": {
        "user": (
            "Diagnóstico: Catarata senil nuclear grau III (CID H25.1)\n"
            "Material: Lente intraocular dobrável monofocal\n"
            "Código TUSS: 30401012"
        ),
        "assistant": (
            "Paciente com diagnóstico de catarata senil nuclear grau III "
            "(CID H25.1), classificação LOCS III NO3-NC3, com acuidade visual "
            "corrigida de 20/80 no olho afetado, impactando atividades de vida "
            "diária e direção veicular. A facoemulsificação com implante de lente "
            "intraocular (LIO) dobrável monofocal acrílica hidrofóbica apresenta "
            "taxa de opacificação capsular posterior < 5% em 5 anos, versus 30% "
            "em LIOs de PMMA (Findl et al., 2010). O desenho asférico da LIO "
            "compensa a aberração esférica positiva da córnea, otimizando a "
            "qualidade visual e sensibilidade ao contraste (Bellucci et al., 2012). "
            "Sem intervenção, a progressão para catarata madura resulta em cegueira "
            "funcional reversível e risco de glaucoma facolítico."
        ),
    },
    "otorrinolaringologia": {
        "user": (
            "Diagnóstico: Hipertrofia de cornetos inferiores refratária (CID J34.3)\n"
            "Material: Radiofrequência para turbinectomia submucosa\n"
            "Código TUSS: 30901016"
        ),
        "assistant": (
            "Paciente com diagnóstico de hipertrofia de cornetos inferiores "
            "(CID J34.3), refratária ao tratamento clínico com corticosteroide "
            "nasal tópico e anti-histamínicos por mais de 12 semanas, com "
            "obstrução nasal bilateral documentada por rinomanometria. A "
            "turbinectomia submucosa por radiofrequência bipolar preserva a "
            "mucosa superficial e a função ciliar, com redução volumétrica de "
            "60-70% do corneto inferior (Cavaliere et al., 2014). Em comparação "
            "com a turbinectomia parcial, a radiofrequência apresenta menor "
            "sangramento intraoperatório e taxa de crostificação 75% menor "
            "(Liu et al., 2009). A obstrução nasal crônica sem tratamento evolui "
            "para respiração oral permanente, síndrome da apneia do sono e "
            "hipertensão pulmonar."
        ),
    },
    "cirurgia_geral": {
        "user": (
            "Diagnóstico: Hérnia incisional recidivante (CID K43.1)\n"
            "Material: Tela de polipropileno macroporosa para herniorrafia\n"
            "Código TUSS: 31009107"
        ),
        "assistant": (
            "Paciente com hérnia incisional recidivante (CID K43.1), com "
            "defeito aponeurótico > 10 cm documentado por tomografia, após "
            "falha de reparo primário prévio. A herniorrafia com tela de "
            "polipropileno macroporosa (poro > 1mm, gramatura < 50g/m²) em "
            "posição retromuscular (técnica de Rives-Stoppa) apresenta taxa de "
            "recidiva de 3-5% versus 30-50% no reparo primário sem tela "
            "(Luijendijk et al., 2000). A macroporosidade favorece infiltração "
            "celular e integração tecidual com formação de fibrose organizada, "
            "reduzindo risco de encapsulamento e infecção crônica "
            "(Klinge et al., 2012). A não correção resulta em progressão do "
            "defeito, risco de encarceramento e estrangulamento visceral."
        ),
    },

}

# Aliases para variações de nome de especialidade
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

    Returns list of [user, assistant] message pairs to inject between
    system prompt and the actual user message.
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
        return []

    example = EXAMPLES[key]
    return [
        {"role": "user", "content": example["user"]},
        {"role": "assistant", "content": example["assistant"]},
    ]
