const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat,
  HeadingLevel, BorderStyle, WidthType, ShadingType,
  PageNumber, PageBreak, TableOfContents,
  TabStopType, TabStopPosition,
} = require("docx");

// ─── helpers ───
const FONT = "Times New Roman";
const PAGE_W = 11906; // A4
const PAGE_H = 16838;
const MARGIN = { top: 1440, right: 1134, bottom: 1134, left: 1701 };
const CONTENT_W = PAGE_W - MARGIN.left - MARGIN.right;

const border = { style: BorderStyle.SINGLE, size: 1, color: "000000" };
const borders = { top: border, bottom: border, left: border, right: border };

function p(text, opts = {}) {
  const runs = [];
  if (typeof text === "string") {
    runs.push(new TextRun({ text, font: FONT, size: opts.size || 24, bold: !!opts.bold, italics: !!opts.italics }));
  } else if (Array.isArray(text)) {
    text.forEach(t => {
      if (typeof t === "string") runs.push(new TextRun({ text: t, font: FONT, size: opts.size || 24 }));
      else runs.push(new TextRun({ font: FONT, size: opts.size || 24, ...t }));
    });
  }
  return new Paragraph({
    alignment: opts.align || AlignmentType.JUSTIFIED,
    spacing: { after: opts.after !== undefined ? opts.after : 120, before: opts.before || 0, line: opts.line || 360 },
    indent: opts.indent ? { firstLine: 708 } : undefined,
    children: runs,
    ...(opts.heading ? { heading: opts.heading } : {}),
    ...(opts.pageBreakBefore ? { pageBreakBefore: true } : {}),
  });
}

function centerP(text, opts = {}) {
  return p(text, { ...opts, align: AlignmentType.CENTER });
}

function emptyP(count = 1) {
  const arr = [];
  for (let i = 0; i < count; i++) arr.push(new Paragraph({ children: [] }));
  return arr;
}

function heading1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 200 },
    children: [new TextRun({ text, font: FONT, size: 28, bold: true })],
  });
}

function heading2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 240, after: 160 },
    children: [new TextRun({ text, font: FONT, size: 26, bold: true })],
  });
}

function heading3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 120 },
    children: [new TextRun({ text, font: FONT, size: 24, bold: true })],
  });
}

function makeCell(text, opts = {}) {
  const runs = typeof text === "string"
    ? [new TextRun({ text, font: FONT, size: opts.headerCell ? 22 : 20, bold: !!opts.headerCell })]
    : text.map(t => new TextRun({ font: FONT, size: opts.headerCell ? 22 : 20, bold: !!opts.headerCell, ...t }));
  return new TableCell({
    borders,
    width: { size: opts.width || 2000, type: WidthType.DXA },
    shading: opts.headerCell ? { fill: "D9E2F3", type: ShadingType.CLEAR } : undefined,
    margins: { top: 40, bottom: 40, left: 80, right: 80 },
    verticalAlign: "center",
    children: [new Paragraph({ alignment: opts.align || AlignmentType.LEFT, children: runs })],
  });
}

// ─── Build Document ───

// Cover page
const coverChildren = [
  centerP("PONTIFÍCIA UNIVERSIDADE CATÓLICA DE CAMPINAS", { bold: true, size: 28 }),
  centerP("CENTRO DE CIÊNCIAS EXATAS, AMBIENTAIS E DE TECNOLOGIAS", { bold: true, size: 24 }),
  centerP("BACHARELADO DE ENGENHARIA DE SOFTWARE", { bold: true, size: 24 }),
  ...emptyP(3),
  centerP("12554 - Projeto Integrador V – Engenharia de Software", { size: 24 }),
  ...emptyP(4),
  centerP("MEDREPORT", { bold: true, size: 36 }),
  ...emptyP(1),
  centerP("PLATAFORMA DE GERAÇÃO AUTOMATIZADA DE JUSTIFICATIVAS TÉCNICAS DE OPME COM INTELIGÊNCIA ARTIFICIAL", { size: 24 }),
  ...emptyP(6),
  centerP("Gabriel Teixeira Costa – RA: 20123097", { size: 24 }),
  centerP("Henrique Vieira Monteiro – RA: [PREENCHER]", { size: 24 }),
  ...emptyP(2),
  centerP("Professora Orientadora: Sílvia C. de Matos Soares", { size: 24 }),
  ...emptyP(3),
  centerP("CAMPINAS", { bold: true, size: 24 }),
  centerP("1º Semestre de 2026", { size: 24 }),
];

// TOC page
const tocChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("Sumário"),
  new TableOfContents("Sumário", { hyperlink: true, headingStyleRange: "1-3" }),
];

// RESUMO
const resumoChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("Resumo"),
  p("O projeto MedReport consiste em uma plataforma SaaS B2B para geração automatizada de justificativas técnicas de OPME (Órteses, Próteses e Materiais Especiais) destinada ao mercado de saúde suplementar brasileiro. O sistema utiliza um pipeline de Inteligência Artificial multi-agente composto por quatro camadas — Pesquisador, Redator, Auditor e Validador — que trabalham em sequência para gerar relatórios médicos persuasivos, fundamentados em evidências científicas verificadas (PubMed) e em conformidade com a legislação vigente (RN 395/ANS, padrão TISS/TUSS). A metodologia de desenvolvimento adotada foi o SCRUM, com sprints quinzenais. Os principais resultados obtidos incluem a redução significativa do tempo de elaboração de relatórios (de horas para minutos), minimização de glosas de convênios médicos através de validação automatizada em múltiplas camadas, e a implementação de assinatura eletrônica com hash SHA-256 e QR Code para verificação pública de autenticidade.", { indent: true }),
  p([
    { text: "Palavras-chave: ", bold: true },
    { text: "Inteligência Artificial; Engenharia de Software; OPME; Saúde Suplementar; Pipeline Multi-Agente; Processamento de Linguagem Natural." },
  ]),
];

// 1. INTRODUÇÃO
const introChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("1. Introdução"),
  p("O mercado de saúde suplementar brasileiro enfrenta um desafio crítico na autorização de procedimentos que envolvem OPME (Órteses, Próteses e Materiais Especiais). Médicos e distribuidores precisam elaborar justificativas técnicas detalhadas para obter a autorização dos convênios médicos, um processo que frequentemente demanda horas de trabalho e resulta em altas taxas de rejeição (glosas) devido à insuficiência de evidências ou não conformidade regulatória.", { indent: true }),
  p("A motivação para o desenvolvimento do MedReport surge da necessidade real de automatizar e qualificar esse processo. Profissionais de saúde gastam tempo excessivo em tarefas burocráticas que poderiam ser dedicadas ao atendimento de pacientes. Além disso, a complexidade regulatória envolvendo normas da ANS (RN 395, RN 501/2022), padrões TISS/TUSS e exigências de evidências científicas torna o processo propenso a erros quando realizado manualmente.", { indent: true }),
  p("A solução proposta é uma plataforma web que utiliza Inteligência Artificial multi-agente para gerar justificativas técnicas completas em minutos. O diferencial do MedReport está no seu pipeline de quatro camadas que inclui um Pesquisador (busca evidências científicas no PubMed e base interna), um Redator (gera o texto da justificativa), um Auditor (confronta dados com a base oficial do produto) e um Validador hard-coded (regex e Python puro, sem IA) que serve como última barreira contra alucinações. Essa arquitetura garante que nenhuma informação fabricada pela IA chegue ao documento final.", { indent: true }),

  heading2("Círculo Dourado"),
  p([{ text: "Por quê? (Why): ", bold: true }, { text: "Porque médicos e distribuidores perdem horas elaborando justificativas técnicas que frequentemente são rejeitadas pelos convênios, causando atrasos no tratamento dos pacientes e prejuízos financeiros." }], { indent: true }),
  p([{ text: "Como? (How): ", bold: true }, { text: "Através de um pipeline de IA multi-agente com quatro camadas de validação que pesquisa evidências científicas automaticamente, gera textos técnicos persuasivos e valida cada informação contra dados oficiais dos produtos." }], { indent: true }),
  p([{ text: "O quê? (What): ", bold: true }, { text: "O MedReport é uma plataforma SaaS B2B que gera justificativas técnicas de OPME automatizadas, com evidências científicas verificáveis, conformes com a legislação ANS e protegidas por assinatura eletrônica." }], { indent: true }),

  heading2("Escopo do Projeto"),
  p([{ text: "O que o software faz: ", bold: true }, { text: "Gera justificativas técnicas de OPME com IA multi-agente; busca evidências científicas automaticamente no PubMed; valida conformidade com normas TISS/TUSS e ANS; exporta relatórios em PDF, DOCX e XML (Guia TISS); aplica assinatura eletrônica SHA-256 com QR Code; oferece sistema de perguntas A/B/C quando há lacunas clínicas; captura edições do médico para aprendizagem contínua." }], { indent: true }),
  p([{ text: "O que o software não faz: ", bold: true }, { text: "Não substitui o julgamento clínico do médico; não realiza diagnósticos; não se comunica diretamente com operadoras de saúde; não implementa assinatura qualificada ICP-Brasil (versão atual usa assinatura avançada SHA-256); não oferece suporte multilinguagem (apenas português)." }], { indent: true }),
];

// 2. OBJETIVOS
const objetivosChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("2. Objetivos"),
  heading2("2.1 Objetivo Geral"),
  p("Desenvolver uma plataforma SaaS B2B que automatize a geração de justificativas técnicas de OPME utilizando Inteligência Artificial multi-agente, reduzindo o tempo de elaboração e minimizando rejeições (glosas) de convênios médicos.", { indent: true }),

  heading2("2.2 Objetivos Específicos"),
  p("a) Implementar um pipeline de IA com quatro camadas (Pesquisador, Redator, Auditor e Validador) que garanta a qualidade e veracidade das justificativas geradas;"),
  p("b) Integrar busca automática de evidências científicas via PubMed E-utilities API com sistema de cache progressivo;"),
  p("c) Desenvolver mecanismo de imunidade a alucinações utilizando validador hard-coded (Python puro/regex) que confronta dados técnicos com a base oficial dos produtos;"),
  p("d) Implementar sistema de exportação profissional em PDF (com QR Code e assinatura SHA-256), DOCX e XML (Guia TISS);"),
  p("e) Criar interface web responsiva com geração em tempo real via Server-Sent Events (SSE) e escrita ao vivo (word-by-word);"),
  p("f) Implementar sistema de conformidade regulatória (TISS/TUSS, ANS, LGPD) integrado ao pipeline de geração;"),
  p("g) Desenvolver módulo de captura de edições médicas para aprendizagem contínua (learning loop) por especialidade;"),
  p("h) Implementar autenticação segura com OAuth2/JWT e controle de acesso baseado em papéis (RBAC)."),
];

// 3. REPRESENTANTES COMUNIDADE EXTERNA
const comunidadeChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("3. Representantes da Comunidade Externa"),
  p("Os representantes da comunidade externa são profissionais que participam da definição de requisitos, validação de protótipos e aceite final do projeto. Esses profissionais contribuem com 62 horas de extensão ao longo do semestre.", { indent: true }),
  ...emptyP(1),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [2500, 3000, 2000, 1571],
    rows: [
      new TableRow({ children: [
        makeCell("Nome", { headerCell: true, width: 2500 }),
        makeCell("E-mail", { headerCell: true, width: 3000 }),
        makeCell("Cargo/Função", { headerCell: true, width: 2000 }),
        makeCell("Organização", { headerCell: true, width: 1571 }),
      ]}),
      new TableRow({ children: [
        makeCell("Hugo Fernando da Silva Farias", { width: 2500 }),
        makeCell("hugomkt.r2m@actionplan.net.br", { width: 3000 }),
        makeCell("Representante Comercial", { width: 2000 }),
        makeCell("Rastriall (CNPJ: 06.321.563/0001-68)", { width: 1571 }),
      ]}),
      new TableRow({ children: [
        makeCell("[A definir]", { width: 2500 }),
        makeCell("[A definir]", { width: 3000 }),
        makeCell("[A definir]", { width: 2000 }),
        makeCell("[A definir]", { width: 1571 }),
      ]}),
    ],
  }),
];

// 4. FUNDAMENTAÇÃO TEÓRICA
const fundamentacaoChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("4. Fundamentação Teórica"),
  p("Este capítulo apresenta os conceitos teóricos que embasam o desenvolvimento do MedReport, abrangendo tanto os fundamentos de Inteligência Artificial quanto os princípios de Engenharia de Software aplicados.", { indent: true }),

  heading2("4.1 Inteligência Artificial e Processamento de Linguagem Natural"),
  p("A Inteligência Artificial (IA) é o campo da ciência da computação dedicado a criar sistemas capazes de realizar tarefas que normalmente requerem inteligência humana. No contexto do MedReport, a IA é aplicada principalmente através de técnicas de Processamento de Linguagem Natural (PLN), que permitem ao sistema compreender, gerar e validar textos médicos complexos.", { indent: true }),
  p("O modelo de linguagem utilizado é o GPT-4o da OpenAI, um Large Language Model (LLM) baseado na arquitetura Transformer (VASWANI et al., 2017). Os Transformers utilizam mecanismos de atenção (self-attention) que permitem ao modelo ponderar a relevância de cada palavra em relação às demais no contexto, gerando textos coerentes e contextualmente apropriados.", { indent: true }),

  heading2("4.2 Retrieval-Augmented Generation (RAG)"),
  p("O MedReport implementa a técnica de RAG (Retrieval-Augmented Generation), proposta por Lewis et al. (2020), que combina a capacidade generativa de LLMs com a recuperação de informações de fontes externas verificáveis. No sistema, o agente Pesquisador busca evidências na base interna de estudos clínicos e no PubMed antes de enviar o contexto ao agente Redator, garantindo que as informações geradas sejam fundamentadas em evidências reais.", { indent: true }),

  heading2("4.3 Sistemas Multi-Agente"),
  p("A arquitetura multi-agente é um paradigma onde múltiplos agentes autônomos colaboram para resolver problemas complexos (WOOLDRIDGE, 2009). O MedReport implementa um pipeline sequencial de quatro agentes especializados, cada um com papel bem definido: pesquisa, redação, auditoria e validação. Essa abordagem permite separação de responsabilidades e facilita a detecção e correção de erros em cada etapa.", { indent: true }),

  heading2("4.4 Prevenção de Alucinações em LLMs"),
  p("Alucinações em LLMs são respostas que parecem plausíveis mas contêm informações fabricadas (JI et al., 2023). O MedReport aborda esse problema com uma estratégia em múltiplas camadas: (1) RAG para fundamentar respostas em dados reais; (2) agente Auditor que confronta cada dado técnico com a base oficial do produto; (3) validador hard-coded (Python puro, sem IA) que extrai entidades técnicas via regex e compara com dados oficiais, bloqueando a geração do PDF caso haja discrepâncias críticas.", { indent: true }),

  heading2("4.5 Engenharia de Software e Metodologias Ágeis"),
  p("O desenvolvimento do MedReport segue os princípios do SCRUM (SCHWABER; SUTHERLAND, 2020), um framework ágil que organiza o trabalho em sprints com entregas incrementais. A arquitetura do sistema segue o padrão de microsserviços, com separação clara entre frontend (React), backend (FastAPI) e serviços auxiliares (RPA), orquestrados via Docker Compose e Turborepo.", { indent: true }),
];

// 5. REQUISITOS
const requisitosChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("5. Levantamento e Análise de Requisitos"),

  heading2("5.1 Requisitos Funcionais"),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [1000, 2000, 6071],
    rows: [
      new TableRow({ children: [
        makeCell("ID", { headerCell: true, width: 1000 }),
        makeCell("Módulo", { headerCell: true, width: 2000 }),
        makeCell("Descrição", { headerCell: true, width: 6071 }),
      ]}),
      ...([
        ["RF01", "Auth", "Cadastro de usuário com e-mail, senha, nome, CRM e UF"],
        ["RF02", "Auth", "Login com autenticação OAuth2/JWT e RBAC (médico, distribuidor, admin)"],
        ["RF03", "Auth", "Aceite de termo de ciência de bases legais (LGPD Art. 11)"],
        ["RF04", "Relatórios", "Criação de relatório via formulário em 4 etapas (diagnóstico, paciente/OPME, geração IA, revisão)"],
        ["RF05", "Relatórios", "Geração automatizada de justificativa técnica via pipeline multi-agente"],
        ["RF06", "Relatórios", "Sistema de perguntas A/B/C quando o Pesquisador identifica lacunas clínicas"],
        ["RF07", "Relatórios", "Progresso em tempo real via Server-Sent Events (SSE)"],
        ["RF08", "Relatórios", "Exportação em PDF (com QR Code), DOCX e XML (Guia TISS)"],
        ["RF09", "Relatórios", "Assinatura eletrônica SHA-256 com snapshot dos dados do médico"],
        ["RF10", "Relatórios", "Verificação pública de autenticidade via QR Code (endpoint sem autenticação)"],
        ["RF11", "Produtos", "Cadastro e busca de produtos OPME com dados técnicos imutáveis"],
        ["RF12", "TUSS", "Consulta de códigos TUSS por código e por texto (procedimentos e materiais)"],
        ["RF13", "IA", "Busca automática de evidências científicas no PubMed com cache progressivo"],
        ["RF14", "IA", "Checklist de conformidade reativo (6 itens, sem IA)"],
        ["RF15", "IA", "Captura de edições do médico para learning loop por especialidade"],
        ["RF16", "Cotações", "Listagem, filtragem e acompanhamento de cotações de OPME"],
      ]).map(([id, mod, desc]) => new TableRow({ children: [
        makeCell(id, { width: 1000 }),
        makeCell(mod, { width: 2000 }),
        makeCell(desc, { width: 6071 }),
      ]})),
    ],
  }),

  ...emptyP(1),
  heading2("5.2 Requisitos Não Funcionais"),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [1000, 2000, 6071],
    rows: [
      new TableRow({ children: [
        makeCell("ID", { headerCell: true, width: 1000 }),
        makeCell("Categoria", { headerCell: true, width: 2000 }),
        makeCell("Descrição", { headerCell: true, width: 6071 }),
      ]}),
      ...([
        ["RNF01", "Segurança", "TLS em trânsito, criptografia em repouso, senhas com bcrypt"],
        ["RNF02", "Segurança", "Autenticação JWT com expiração e refresh token"],
        ["RNF03", "LGPD", "Bases legais conforme Art. 11 (obrigação legal, tutela da saúde, consentimento)"],
        ["RNF04", "LGPD", "Minimização de dados, direito de exclusão e portabilidade"],
        ["RNF05", "Conformidade", "Aderência ao padrão TISS (RN 501/2022) e TUSS (IN DIDES 44/2010)"],
        ["RNF06", "Desempenho", "Geração de relatório completo em menos de 60 segundos"],
        ["RNF07", "Usabilidade", "Interface responsiva com feedback visual em tempo real (SSE)"],
        ["RNF08", "Disponibilidade", "Monitoramento de saúde dos serviços via health checks"],
        ["RNF09", "Escalabilidade", "Arquitetura baseada em Docker Compose com serviços independentes"],
        ["RNF10", "Auditoria", "Logs de todas as operações com rastreabilidade completa"],
      ]).map(([id, cat, desc]) => new TableRow({ children: [
        makeCell(id, { width: 1000 }),
        makeCell(cat, { width: 2000 }),
        makeCell(desc, { width: 6071 }),
      ]})),
    ],
  }),

  ...emptyP(1),
  heading2("5.3 Requisitos Específicos de Inteligência Artificial"),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [1200, 3000, 4871],
    rows: [
      new TableRow({ children: [
        makeCell("ID", { headerCell: true, width: 1200 }),
        makeCell("Métrica", { headerCell: true, width: 3000 }),
        makeCell("Critério", { headerCell: true, width: 4871 }),
      ]}),
      ...([
        ["RIA01", "Acurácia de evidências", "100% das referências devem possuir PMID/DOI verificável"],
        ["RIA02", "Tempo de resposta", "Pipeline completo (4 agentes) em menos de 60 segundos"],
        ["RIA03", "Taxa de alucinações", "0% de dados técnicos fabricados no documento final (validador hard-coded)"],
        ["RIA04", "Cobertura de checklist", "6/6 itens obrigatórios validados antes da aprovação"],
        ["RIA05", "Cache hit rate", "Acima de 70% após período de aquecimento (PubMed cache TTL: 180 dias)"],
        ["RIA06", "Qualidade textual", "Tom persuasivo técnico validado por profissionais da área médica"],
      ]).map(([id, met, crit]) => new TableRow({ children: [
        makeCell(id, { width: 1200 }),
        makeCell(met, { width: 3000 }),
        makeCell(crit, { width: 4871 }),
      ]})),
    ],
  }),
];

// 6. BENCHMARKING
const benchChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("6. Benchmarking"),
  p("A tabela a seguir compara as funcionalidades do MedReport com softwares já existentes no mercado de justificativas médicas e gestão de OPME.", { indent: true }),
  ...emptyP(1),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [2800, 1568, 1568, 1568, 1568],
    rows: [
      new TableRow({ children: [
        makeCell("Funcionalidade", { headerCell: true, width: 2800 }),
        makeCell("MedReport", { headerCell: true, width: 1568, align: AlignmentType.CENTER }),
        makeCell("Lauduz", { headerCell: true, width: 1568, align: AlignmentType.CENTER }),
        makeCell("Feegow", { headerCell: true, width: 1568, align: AlignmentType.CENTER }),
        makeCell("Smart OPME", { headerCell: true, width: 1568, align: AlignmentType.CENTER }),
      ]}),
      ...[
        ["Geração de justificativa com IA", "V", "X", "X", "X"],
        ["Pipeline multi-agente (4 camadas)", "V", "X", "X", "X"],
        ["Busca automática PubMed", "V", "X", "X", "X"],
        ["Validador anti-alucinação (hard-coded)", "V", "X", "X", "X"],
        ["Exportação PDF/DOCX/XML TISS", "V", "V", "V", "V"],
        ["Assinatura eletrônica SHA-256", "V", "X", "V", "X"],
        ["QR Code para verificação pública", "V", "X", "X", "X"],
        ["Conformidade TISS/TUSS automática", "V", "P", "V", "V"],
        ["Escrita ao vivo (SSE/streaming)", "V", "X", "X", "X"],
        ["Learning loop por especialidade", "V", "X", "X", "X"],
        ["Gestão de cotações com RPA", "V", "X", "X", "V"],
      ].map(([func, ...vals]) => new TableRow({ children: [
        makeCell(func, { width: 2800 }),
        ...vals.map(v => makeCell(v === "V" ? "\u2713" : v === "P" ? "Parcial" : "X", { width: 1568, align: AlignmentType.CENTER })),
      ]})),
    ],
  }),
  ...emptyP(1),
  p("Legenda: \u2713 = Possui | X = Não possui | Parcial = Implementação limitada", { size: 20, italics: true }),
  ...emptyP(1),
  p("O principal diferencial do MedReport é a combinação de geração automatizada por IA multi-agente com um sistema robusto de prevenção de alucinações. Enquanto os concorrentes oferecem funcionalidades isoladas (como templates de relatórios ou gestão de OPME), o MedReport integra todo o fluxo — da pesquisa científica à assinatura eletrônica — em uma única plataforma. O caráter inovador reside no pipeline de quatro camadas com validador hard-coded, uma abordagem que nenhum concorrente implementa atualmente.", { indent: true }),
];

// 7. PERSONAS
const personasChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("7. Definição das Personas"),

  heading2("Persona 1: Dr. Ricardo (Médico Ortopedista)"),
  p([{ text: "Perfil: ", bold: true }, { text: "Médico com 15 anos de experiência, atende em clínica particular e hospital conveniado. Realiza cirurgias que frequentemente necessitam de OPME (próteses, parafusos, placas)." }], { indent: true }),
  p([{ text: "Dor principal: ", bold: true }, { text: "Gasta em média 2 horas por justificativa técnica, e cerca de 30% são rejeitadas (glosadas) pelo convênio na primeira submissão, gerando retrabalho." }], { indent: true }),
  p([{ text: "Necessidade: ", bold: true }, { text: "Uma ferramenta que gere justificativas técnicas completas, com evidências científicas e em conformidade com as normas, reduzindo o tempo gasto e a taxa de glosas." }], { indent: true }),

  heading2("Persona 2: Marcos (Distribuidor de OPME)"),
  p([{ text: "Perfil: ", bold: true }, { text: "Gerente comercial de distribuidora de OPME, responsável por atender médicos e responder cotações em múltiplos portais de planos de saúde." }], { indent: true }),
  p([{ text: "Dor principal: ", bold: true }, { text: "Precisa acompanhar cotações em diversos portais manualmente, perdendo oportunidades por falta de agilidade. Também auxilia médicos com justificativas técnicas." }], { indent: true }),
  p([{ text: "Necessidade: ", bold: true }, { text: "Central unificada de cotações com automação (RPA) e ferramenta que ajude a gerar justificativas técnicas de alta qualidade para os médicos parceiros." }], { indent: true }),

  heading2("Persona 3: Ana (Administradora da Plataforma)"),
  p([{ text: "Perfil: ", bold: true }, { text: "Profissional de TI responsável pela gestão da plataforma, usuários e configurações do sistema." }], { indent: true }),
  p([{ text: "Dor principal: ", bold: true }, { text: "Necessidade de monitorar o uso do sistema, gerenciar permissões e garantir conformidade regulatória." }], { indent: true }),
  p([{ text: "Necessidade: ", bold: true }, { text: "Painel administrativo com métricas de uso, gestão de usuários (RBAC) e monitoramento dos serviços." }], { indent: true }),
];

// 8. PROTÓTIPOS
const prototChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("8. Protótipos das Interfaces"),
  p("Os protótipos das interfaces foram desenvolvidos diretamente em código (React + Chakra UI), servindo simultaneamente como protótipo funcional e interface final. As principais telas do sistema são:", { indent: true }),
  ...emptyP(1),
  p([{ text: "Tela de Login: ", bold: true }, { text: "Formulário de autenticação com campos de e-mail e senha, opção de cadastro." }]),
  p([{ text: "Tela de Cadastro: ", bold: true }, { text: "Registro com nome completo, CRM, UF, e-mail e senha." }]),
  p([{ text: "Dashboard: ", bold: true }, { text: "Lista de relatórios criados pelo usuário com status e opções de ação." }]),
  p([{ text: "Criação de Relatório (Etapa 1 – Diagnóstico): ", bold: true }, { text: "Seleção de CID e descrição do quadro clínico." }]),
  p([{ text: "Criação de Relatório (Etapa 2 – Paciente e OPME): ", bold: true }, { text: "Nome do paciente, seleção de produto OPME, códigos TUSS." }]),
  p([{ text: "Criação de Relatório (Etapa 3 – Geração IA): ", bold: true }, { text: "Pipeline em execução com progresso em tempo real (SSE), escrita ao vivo word-by-word." }]),
  p([{ text: "Criação de Relatório (Etapa 4 – Revisão): ", bold: true }, { text: "Texto completo da justificativa, checklist de conformidade, opções de download (PDF/DOCX/XML) e assinatura eletrônica." }]),
  ...emptyP(1),
  p([{ text: "Link do repositório: ", bold: true }, { text: "https://github.com/[REPOSITÓRIO]" }]),
  p("[Inserir prints das telas aqui]", { italics: true, align: AlignmentType.CENTER }),
  ...emptyP(1),
  p("Validação/aceite dos protótipos será realizada com os representantes da comunidade externa listados na seção 3.", { indent: true }),
];

// 9. MODELO DE DADOS
const modeloChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("9. Modelo de Dados"),
  p("O MedReport utiliza banco de dados relacional PostgreSQL 16. O modelo entidade-relacionamento contempla as seguintes entidades principais:", { indent: true }),
  ...emptyP(1),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [3000, 6071],
    rows: [
      new TableRow({ children: [
        makeCell("Entidade", { headerCell: true, width: 3000 }),
        makeCell("Descrição", { headerCell: true, width: 6071 }),
      ]}),
      ...[
        ["users", "Médicos, distribuidores e administradores com dados de autenticação e perfil profissional (CRM, UF)"],
        ["products", "Produtos OPME com dados técnicos imutáveis (viscosidade, peso molecular, registro ANVISA) – fonte de verdade para o Auditor"],
        ["reports", "Relatórios gerados com justificativa IA, auditoria, checklist, assinatura SHA-256 e PDF selado"],
        ["clinical_evidences", "Evidências científicas pré-validadas por CID × Produto (prioridade máxima na pesquisa)"],
        ["pubmed_cache", "Cache permanente de artigos PubMed com TTL de 180 dias"],
        ["report_templates", "Templates DNA de relatórios aprovados (tom, estrutura, referências padrão)"],
        ["report_edits", "Edições do médico capturadas para learning loop por especialidade"],
        ["tuss_procedures", "Tabela 22 TUSS – Procedimentos (fonte: FTP ANS)"],
        ["tuss_materials", "Tabela 19 TUSS – Materiais OPME (fonte: FTP ANS)"],
        ["product_tuss_mappings", "Mapeamento N:N entre produtos e códigos TUSS aplicáveis"],
        ["rol_procedures", "Procedimentos do Rol da ANS (cobertura obrigatória por segmentação)"],
        ["dut_rules", "Diretrizes de Utilização Terapêutica (critérios condicionantes de cobertura)"],
        ["anvisa_products", "Registros de produtos na ANVISA (status, validade, classe de risco)"],
        ["quotes", "Cotações capturadas de portais de planos de saúde"],
        ["quote_items", "Itens de cotação (produtos solicitados)"],
      ].map(([ent, desc]) => new TableRow({ children: [
        makeCell(ent, { width: 3000 }),
        makeCell(desc, { width: 6071 }),
      ]})),
    ],
  }),
  ...emptyP(1),
  p("[Inserir diagrama MER aqui]", { italics: true, align: AlignmentType.CENTER }),
];

// 10. ARQUITETURA E TECNOLOGIAS
const arqChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("10. Arquitetura e Tecnologias"),

  heading2("10.1 Arquitetura Geral"),
  p("O MedReport segue uma arquitetura de monorepo orquestrada pelo Turborepo, com separação clara entre frontend, backend e serviços auxiliares. A comunicação entre frontend e backend ocorre via API REST (JSON) e Server-Sent Events (SSE) para atualizações em tempo real.", { indent: true }),
  ...emptyP(1),
  p("Estrutura do monorepo:", { bold: true }),
  p("apps/web/ – Frontend React + Chakra UI (Vite)"),
  p("services/api/ – Backend FastAPI (Python)"),
  p("services/rpa/ – Robô de captura de cotações (Playwright)"),
  p("docker-compose.yml – PostgreSQL + Redis + Elasticsearch"),
  ...emptyP(1),

  heading2("10.2 Tecnologias Utilizadas"),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [2500, 6571],
    rows: [
      new TableRow({ children: [
        makeCell("Camada", { headerCell: true, width: 2500 }),
        makeCell("Tecnologias", { headerCell: true, width: 6571 }),
      ]}),
      ...[
        ["Frontend", "React 18, TypeScript, Chakra UI, Vite, React Router, Framer Motion, Emotion"],
        ["Backend", "FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, Uvicorn, Python 3.11+"],
        ["Inteligência Artificial", "OpenAI GPT-4o, pipeline multi-agente, RAG, PubMed E-utilities API"],
        ["Banco de Dados", "PostgreSQL 16 (principal), Redis 7 (cache), Elasticsearch 8.11 (busca)"],
        ["Geração de Documentos", "WeasyPrint (PDF), python-docx (DOCX), Jinja2 (templates), qrcode (QR)"],
        ["RPA", "Playwright (automação de navegador para captura de cotações)"],
        ["Infraestrutura", "Docker Compose, Turborepo, GitHub Actions"],
        ["Autenticação", "OAuth2 + JWT, bcrypt (hash de senhas)"],
        ["Protótipos/UX", "React + Chakra UI (protótipo funcional = interface final)"],
        ["Gerenciamento", "GitHub Projects, SCRUM (sprints quinzenais)"],
      ].map(([cam, tec]) => new TableRow({ children: [
        makeCell(cam, { width: 2500 }),
        makeCell(tec, { width: 6571 }),
      ]})),
    ],
  }),

  ...emptyP(1),
  heading2("10.3 Pipeline Multi-Agente (Diagrama)"),
  p("O pipeline de IA do MedReport é composto por quatro camadas sequenciais:", { indent: true }),
  ...emptyP(1),
  p("Camada 1 – Pesquisador (Agente A): Busca evidências na base interna (clinical_evidences) e no PubMed. Identifica lacunas (críticas e de fortalecimento) e gera perguntas A/B/C para o médico.", { indent: true }),
  p("Camada 2 – Redator (Agente B): Consolida pesquisa + respostas do médico + template DNA. Gera justificativa técnica completa com citações nominais e tom persuasivo.", { indent: true }),
  p("Camada 3 – Auditor (Agente C): Confronta rascunho com dados oficiais do produto (viscosidade, peso molecular, registro ANVISA). Gera log de auditoria com correções antes/depois.", { indent: true }),
  p("Camada 4 – Validador (Python puro): Extrai entidades técnicas via regex e confronta com dados oficiais. Bloqueia geração de PDF se houver discrepâncias críticas. Nenhuma IA envolvida nesta camada.", { indent: true }),
];

// 11. DESCRIÇÃO DA SOLUÇÃO DE IA
const iaChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("11. Descrição da Solução de Inteligência Artificial"),

  heading2("11.1 Base de Dados"),
  p("A solução de IA do MedReport utiliza duas fontes principais de dados:", { indent: true }),
  p([{ text: "Base interna (clinical_evidences): ", bold: true }, { text: "Evidências científicas pré-validadas, organizadas por CID (Classificação Internacional de Doenças) e produto OPME. Cada evidência contém snippet, autor, referência completa, ano, tipo (meta-análise, RCT, revisão, coorte) e nível de relevância. Atualmente a base cobre áreas como Lipedema, Ortopedia, Reconstrução Mamária e Medicina Regenerativa." }], { indent: true }),
  p([{ text: "PubMed (NCBI): ", bold: true }, { text: "Artigos científicos acessados via E-utilities API com fallback para Europe PMC. O sistema mapeia mais de 60 códigos CID para descritores MeSH, permitindo buscas precisas. Os resultados são armazenados em cache permanente (tabela pubmed_cache) com TTL de 180 dias." }], { indent: true }),

  heading2("11.2 Pré-processamento dos Dados"),
  p("O pré-processamento ocorre em múltiplas etapas:", { indent: true }),
  p([{ text: "Mapeamento CID–MeSH: ", bold: true }, { text: "Mais de 60 códigos CID são mapeados para descritores MeSH correspondentes, permitindo buscas precisas no PubMed." }]),
  p([{ text: "Estratégia de busca em cascata: ", bold: true }, { text: "Inicia com busca específica (produto + MeSH + filtro RCT), amplia se insuficiente, e generaliza como último recurso." }]),
  p([{ text: "Inferência de nível de evidência: ", bold: true }, { text: "A partir do abstract de cada artigo, o sistema infere o nível de evidência (meta-análise, RCT, coorte, caso-controle, série de casos)." }]),
  p([{ text: "Normalização de dados de produto: ", bold: true }, { text: "Dados técnicos dos produtos (viscosidade, peso molecular, concentração) são normalizados e armazenados como fonte de verdade imutável." }]),

  heading2("11.3 Modelos de IA Utilizados"),
  p("O MedReport utiliza o modelo GPT-4o da OpenAI como engine principal para três dos quatro agentes do pipeline:", { indent: true }),
  p([{ text: "Agente Pesquisador: ", bold: true }, { text: "Recebe o contexto clínico (CID, diagnóstico, produto) e as evidências recuperadas. Analisa lacunas e gera perguntas estruturadas (A/B/C) para o médico. System prompt altamente especializado com instruções de priorização de evidências." }]),
  p([{ text: "Agente Redator: ", bold: true }, { text: "Recebe pesquisa + respostas do médico + template DNA de relatórios aprovados. Gera justificativa técnica completa mimetizando o tom e a estrutura de relatórios previamente aprovados." }]),
  p([{ text: "Agente Auditor: ", bold: true }, { text: "Recebe rascunho + dados oficiais do produto. Confronta cada informação técnica e gera log de auditoria detalhado com correções." }]),
  p([{ text: "Validador (sem IA): ", bold: true }, { text: "Implementado integralmente em Python com regex. Extrai entidades técnicas do texto (viscosidade, peso molecular, registro ANVISA) e compara com dados oficiais. Classificação de severidade: crítica (bloqueia PDF), aviso (permite com alerta), informativo." }]),

  heading2("11.4 Treinamento e Validação"),
  p("O MedReport não realiza treinamento de modelos proprietários — utiliza o GPT-4o pré-treinado da OpenAI com prompts altamente especializados (prompt engineering). A validação do sistema ocorre em múltiplos níveis:", { indent: true }),
  p([{ text: "Validação por camada: ", bold: true }, { text: "Cada agente do pipeline tem testes unitários e de integração específicos." }]),
  p([{ text: "Validação por confrontação: ", bold: true }, { text: "O Auditor (Agente C) confronta cada dado técnico do rascunho com a base oficial do produto, gerando log de correções." }]),
  p([{ text: "Validação hard-coded: ", bold: true }, { text: "O Validador (Camada 4) utiliza regex para extrair e verificar entidades técnicas contra dados oficiais, sem depender de IA." }]),
  p([{ text: "Validação humana (human-in-the-loop): ", bold: true }, { text: "O médico revisa o texto final antes de assinar, podendo editar qualquer trecho. As edições são capturadas para o learning loop." }]),

  heading2("11.5 Métricas de Avaliação"),
  p("As métricas utilizadas para avaliar o desempenho da solução de IA são:", { indent: true }),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [3000, 3000, 3071],
    rows: [
      new TableRow({ children: [
        makeCell("Métrica", { headerCell: true, width: 3000 }),
        makeCell("Meta", { headerCell: true, width: 3000 }),
        makeCell("Justificativa", { headerCell: true, width: 3071 }),
      ]}),
      ...[
        ["Taxa de alucinações", "0%", "Dados fabricados são inaceitáveis em documentos médicos"],
        ["Referências verificáveis", "100%", "Toda citação deve ter PMID ou DOI rastreável"],
        ["Tempo de pipeline", "< 60s", "Viabilidade de uso em contexto clínico real"],
        ["Checklist compliance", "6/6 itens", "Conformidade regulatória obrigatória"],
        ["Satisfação do médico", "> 4/5", "Avaliação subjetiva de qualidade textual"],
        ["PubMed cache hit", "> 70%", "Eficiência de busca após aquecimento"],
      ].map(([met, meta, just]) => new TableRow({ children: [
        makeCell(met, { width: 3000 }),
        makeCell(meta, { width: 3000 }),
        makeCell(just, { width: 3071 }),
      ]})),
    ],
  }),
];

// 12. TESTES E VALIDAÇÃO
const testesChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("12. Testes e Validação do Sistema"),
  p("A estratégia de testes do MedReport abrange testes unitários, de integração e validação do modelo de IA.", { indent: true }),

  heading2("12.1 Testes Unitários"),
  p("Testes unitários cobrem os componentes críticos do sistema:", { indent: true }),
  p("– Serviço PubMed: validação de busca, parsing de resultados, cache e mapeamento CID–MeSH (test_pubmed_unit.py)"),
  p("– Agentes do pipeline: validação de entradas/saídas de cada agente"),
  p("– Modelos de dados: integridade de campos e relacionamentos"),
  p("– Rotas da API: testes de endpoints de autenticação, relatórios e produtos"),

  heading2("12.2 Testes de Integração"),
  p("Os testes de integração validam o fluxo completo do pipeline:", { indent: true }),
  p("– Pipeline multi-agente end-to-end: geração de relatório completo (test_pubmed_integration.py)"),
  p("– Testes de integração da API: fluxo de autenticação, criação e assinatura de relatórios"),
  p("– Importação ANVISA: validação do processo de ingestão de dados regulatórios"),

  heading2("12.3 Testes do Modelo de IA"),
  p("A validação específica do modelo de IA inclui:", { indent: true }),
  p("– Verificação de que o Validador (Camada 4) detecta e bloqueia dados fabricados"),
  p("– Confrontação de dados técnicos gerados pelo Redator com a base oficial via Auditor"),
  p("– Validação de que todas as referências incluem PMID/DOI verificáveis"),
  p("– Testes de geração em lote (test_generate.py) com diferentes combinações de CID e produto"),
];

// 13. GESTÃO DO PROJETO
const gestaoChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("13. Gestão do Projeto"),

  heading2("13.1 Metodologia"),
  p("O projeto MedReport foi desenvolvido utilizando a metodologia SCRUM, com sprints de duas semanas. As cerimônias incluem planning, daily stand-ups, review e retrospectiva.", { indent: true }),

  heading2("13.2 Product Backlog"),
  new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [800, 5271, 1500, 1500],
    rows: [
      new TableRow({ children: [
        makeCell("ID", { headerCell: true, width: 800 }),
        makeCell("História de Usuário", { headerCell: true, width: 5271 }),
        makeCell("Prioridade", { headerCell: true, width: 1500 }),
        makeCell("Status", { headerCell: true, width: 1500 }),
      ]}),
      ...[
        ["PB01", "Como médico, quero me cadastrar com meu CRM e UF para que minha identidade profissional seja verificada", "Alta", "Concluído"],
        ["PB02", "Como médico, quero fazer login seguro para acessar meus relatórios", "Alta", "Concluído"],
        ["PB03", "Como médico, quero criar um relatório informando CID e produto OPME", "Alta", "Concluído"],
        ["PB04", "Como médico, quero que a IA gere uma justificativa técnica automaticamente", "Alta", "Concluído"],
        ["PB05", "Como médico, quero responder perguntas A/B/C para complementar lacunas clínicas", "Alta", "Concluído"],
        ["PB06", "Como médico, quero ver o progresso da geração em tempo real", "Média", "Concluído"],
        ["PB07", "Como médico, quero exportar o relatório em PDF com QR Code", "Alta", "Concluído"],
        ["PB08", "Como médico, quero assinar eletronicamente o relatório", "Alta", "Concluído"],
        ["PB09", "Como médico, quero verificar a autenticidade via QR Code", "Média", "Concluído"],
        ["PB10", "Como distribuidor, quero acompanhar cotações de OPME", "Média", "Em progresso"],
        ["PB11", "Como admin, quero gerenciar usuários e permissões", "Baixa", "Pendente"],
      ].map(([id, hist, pri, st]) => new TableRow({ children: [
        makeCell(id, { width: 800 }),
        makeCell(hist, { width: 5271 }),
        makeCell(pri, { width: 1500 }),
        makeCell(st, { width: 1500 }),
      ]})),
    ],
  }),

  ...emptyP(1),
  heading2("13.3 Cronograma de Sprints"),
  p("[Inserir cronograma planejado e real das sprints com tarefas e responsáveis]", { italics: true }),
];

// 14. RESULTADOS E DISCUSSÃO
const resultadosChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("14. Resultados e Discussão"),
  p("Os resultados obtidos até o momento demonstram que o MedReport atende aos objetivos propostos de forma significativa.", { indent: true }),

  heading2("14.1 Facilidades e Melhorias"),
  p("– Redução do tempo de elaboração de justificativas técnicas de horas para menos de 1 minuto"),
  p("– Fundamentação automática em evidências científicas verificáveis (PubMed)"),
  p("– Eliminação de dados fabricados através do validador hard-coded (camada 4)"),
  p("– Interface intuitiva com feedback em tempo real (escrita ao vivo)"),
  p("– Exportação profissional em múltiplos formatos (PDF/DOCX/XML)"),
  p("– Rastreabilidade completa com assinatura SHA-256 e verificação via QR Code"),

  heading2("14.2 Objetivos Atendidos"),
  p("Os objetivos específicos (a) a (h) foram atendidos conforme descrito na seção 2. O pipeline multi-agente está funcional, a integração com PubMed operacional, e o sistema de assinatura eletrônica implementado.", { indent: true }),

  heading2("14.3 Objetivos em Andamento"),
  p("– Módulo completo de gestão de cotações com RPA (parcialmente implementado)"),
  p("– Integração com ERP para sincronização de preços e estoque (mock disponível)"),
  p("– Assinatura qualificada ICP-Brasil (atualmente usa SHA-256, assinatura avançada)"),

  heading2("14.4 Considerações Éticas, de Privacidade e Impacto Social"),
  p([{ text: "LGPD e Dados Sensíveis: ", bold: true }, { text: "O sistema trata dados de saúde (dados pessoais sensíveis conforme Art. 5º, II da LGPD) com bases legais específicas: obrigação legal/regulatória (TISS/ANS), tutela da saúde e consentimento para funcionalidades opcionais. Implementa minimização de dados, direito de exclusão e política de retenção (20 anos para relatórios, 5 anos para logs)." }], { indent: true }),
  p([{ text: "Transferência Internacional: ", bold: true }, { text: "Os dados são processados pela API da OpenAI (servidores nos EUA), configurando transferência internacional de dados. O sistema implementa garantias contratuais conforme Art. 33 da LGPD." }], { indent: true }),
  p([{ text: "Vieses e IA Responsável: ", bold: true }, { text: "O pipeline multi-agente com validador hard-coded minimiza o risco de vieses da IA, pois cada informação técnica é confrontada com dados oficiais verificáveis. O médico sempre tem a palavra final (human-in-the-loop)." }], { indent: true }),
  p([{ text: "Impacto Social: ", bold: true }, { text: "O MedReport tem potencial de democratizar o acesso a justificativas técnicas de alta qualidade, beneficiando pacientes que dependem de autorização de convênios para procedimentos com OPME. Ao reduzir glosas, o sistema contribui para agilizar o acesso ao tratamento." }], { indent: true }),
];

// 15. CONCLUSÃO
const conclusaoChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("15. Conclusão e Trabalhos Futuros"),
  p("O MedReport demonstrou ser uma solução viável e eficaz para a automação de justificativas técnicas de OPME utilizando Inteligência Artificial. O pipeline multi-agente com quatro camadas de validação — incluindo um validador hard-coded que opera sem IA — provou ser uma abordagem robusta para prevenir alucinações em documentos médicos críticos.", { indent: true }),
  p("As principais contribuições do projeto são: (1) a arquitetura multi-agente com separação clara de responsabilidades; (2) a estratégia de imunidade a alucinações combinando RAG, auditoria por IA e validação determinística; (3) a integração automática com PubMed para fundamentação científica; e (4) o sistema de assinatura eletrônica com verificação pública.", { indent: true }),

  heading2("Limitações"),
  p("– Assinatura qualificada ICP-Brasil ainda não implementada (usa SHA-256)"),
  p("– Integração real com portais de cotação ainda limitada (RPA com portal demo)"),
  p("– Base de evidências internas concentrada em algumas especialidades"),
  p("– Suporte apenas em português"),

  heading2("Trabalhos Futuros"),
  p("– Implementação de assinatura qualificada ICP-Brasil para conformidade plena com o padrão TISS"),
  p("– Expansão das integrações RPA para portais reais de planos de saúde"),
  p("– Ampliação da base de evidências clínicas para mais especialidades"),
  p("– Implementação de DUT (Diretrizes de Utilização Terapêutica) para validação automática de cobertura"),
  p("– Motor de scoring de aprovação baseado em dados históricos de glosas"),
  p("– Suporte multilinguagem para expansão internacional"),
];

// 16. ACEITE FINAL
const aceiteChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("16. Aceite Final do Projeto"),
  p("[A ser preenchido pela comunidade externa ao final do projeto]", { italics: true }),
  ...emptyP(3),
  p("Eu, _____________________________, representante da comunidade externa, declaro que participei das etapas de definição de requisitos, validação de protótipos e/ou validação final do projeto MedReport, e que o sistema atende às expectativas e necessidades apresentadas."),
  ...emptyP(3),
  p("Data: ____/____/________"),
  ...emptyP(2),
  p("Assinatura: ___________________________"),
  p("Nome: ___________________________"),
  p("Organização: ___________________________"),
];

// REFERÊNCIAS
const refChildren = [
  new Paragraph({ children: [new PageBreak()] }),
  heading1("Referências"),
  p("BRASIL. Lei nº 13.709, de 14 de agosto de 2018. Lei Geral de Proteção de Dados Pessoais (LGPD). Diário Oficial da União, Brasília, DF, 15 ago. 2018."),
  ...emptyP(0),
  p("BRASIL. Lei nº 14.063, de 23 de setembro de 2020. Dispõe sobre o uso de assinaturas eletrônicas em interações com entes públicos. Diário Oficial da União, Brasília, DF, 24 set. 2020."),
  ...emptyP(0),
  p("BRASIL. Medida Provisória nº 2.200-2, de 24 de agosto de 2001. Institui a Infraestrutura de Chaves Públicas Brasileira (ICP-Brasil). Diário Oficial da União, Brasília, DF, 27 ago. 2001."),
  ...emptyP(0),
  p("AGÊNCIA NACIONAL DE SAÚDE SUPLEMENTAR (ANS). Resolução Normativa nº 501, de 30 de março de 2022. Dispõe sobre o Padrão TISS. Brasília: ANS, 2022."),
  ...emptyP(0),
  p("AGÊNCIA NACIONAL DE SAÚDE SUPLEMENTAR (ANS). Resolução Normativa nº 489, de 7 de julho de 2022. Dispõe sobre sanções administrativas. Brasília: ANS, 2022."),
  ...emptyP(0),
  p("JI, Z. et al. Survey of hallucination in natural language generation. ACM Computing Surveys, v. 55, n. 12, p. 1-38, 2023."),
  ...emptyP(0),
  p("LEWIS, P. et al. Retrieval-augmented generation for knowledge-intensive NLP tasks. Advances in Neural Information Processing Systems, v. 33, p. 9459-9474, 2020."),
  ...emptyP(0),
  p("SCHWABER, K.; SUTHERLAND, J. The Scrum Guide: the definitive guide to Scrum: the rules of the game. 2020. Disponível em: https://scrumguides.org. Acesso em: 15 mar. 2026."),
  ...emptyP(0),
  p("VASWANI, A. et al. Attention is all you need. Advances in Neural Information Processing Systems, v. 30, 2017."),
  ...emptyP(0),
  p("WOOLDRIDGE, M. An introduction to multiagent systems. 2. ed. Chichester: John Wiley & Sons, 2009."),
];

// ─── Assemble Document ───
const doc = new Document({
  styles: {
    default: {
      document: { run: { font: FONT, size: 24 } },
    },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: FONT },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: FONT },
        paragraph: { spacing: { before: 240, after: 160 }, outlineLevel: 1 },
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: FONT },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
    ],
  },
  sections: [
    {
      properties: {
        page: { size: { width: PAGE_W, height: PAGE_H }, margin: MARGIN },
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            children: [new TextRun({ text: "MedReport – Documentação do Projeto", font: FONT, size: 18, italics: true, color: "808080" })],
          })],
        }),
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [
              new TextRun({ text: "Página ", font: FONT, size: 18 }),
              new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18 }),
            ],
          })],
        }),
      },
      children: [
        ...coverChildren,
        ...tocChildren,
        ...resumoChildren,
        ...introChildren,
        ...objetivosChildren,
        ...comunidadeChildren,
        ...fundamentacaoChildren,
        ...requisitosChildren,
        ...benchChildren,
        ...personasChildren,
        ...prototChildren,
        ...modeloChildren,
        ...arqChildren,
        ...iaChildren,
        ...testesChildren,
        ...gestaoChildren,
        ...resultadosChildren,
        ...conclusaoChildren,
        ...aceiteChildren,
        ...refChildren,
      ],
    },
  ],
});

const OUTPUT = "/Users/gabrielcosta/Documents/GitHub/MedReport/docs/MedReport_Documentacao.docx";
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUTPUT, buf);
  console.log("Documento gerado:", OUTPUT);
});
