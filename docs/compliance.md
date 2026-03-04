# Compliance Regulatório e LGPD – OPME Platform

Este documento descreve as bases legais, normativos aplicáveis e responsabilidades de compliance da plataforma OPME.

## 1. Bases Legais para Tratamento de Dados (LGPD)

A Lei Geral de Proteção de Dados (Lei 13.709/2018) estabelece que dados de saúde são **dados pessoais sensíveis** (Art. 5º, II) e requerem bases legais específicas para tratamento (Art. 11).

### 1.1 Bases Legais Aplicáveis

A plataforma OPME trata dados com fundamento nas seguintes bases legais:

| Base Legal | Artigo LGPD | Aplicação na Plataforma |
|------------|-------------|-------------------------|
| **Consentimento** | Art. 11, I | Funcionalidades opcionais, comunicações, preferências personalizadas |
| **Obrigação legal/regulatória** | Art. 11, II, "a" | Geração de guias TISS conforme exigido pela ANS |
| **Tutela da saúde** | Art. 11, II, "f" | Processamento para procedimentos de saúde por profissionais habilitados |
| **Proteção da vida** | Art. 11, II, "e" | Situações de urgência/emergência |
| **Execução de contrato** | Art. 11, II, "d" | Prestação de serviços contratados pelo distribuidor |

### 1.2 Direitos dos Titulares (Art. 18)

A plataforma deve garantir aos titulares:

- Confirmação da existência de tratamento (Art. 18, I)
- Acesso aos dados (Art. 18, II)
- Correção de dados incompletos, inexatos ou desatualizados (Art. 18, III)
- Anonimização, bloqueio ou eliminação de dados desnecessários (Art. 18, IV)
- Portabilidade dos dados (Art. 18, V)
- Eliminação dos dados tratados com consentimento (Art. 18, VI)
- Informação sobre compartilhamento (Art. 18, VII)
- Revogação do consentimento (Art. 18, IX)

### 1.3 Medidas de Segurança (Art. 46)

Conforme Art. 46 da LGPD, a plataforma implementa:

- Criptografia em trânsito (TLS) e em repouso
- Controle de acesso baseado em papéis (RBAC)
- Logs de auditoria para rastreabilidade
- Autenticação segura (OAuth2/JWT)
- Segregação de ambientes (dev/staging/prod)

---

## 2. Normativos TISS/TUSS (ANS)

### 2.1 Padrão TISS

O Padrão TISS (Troca de Informações na Saúde Suplementar) é **obrigatório** para comunicação entre operadoras e prestadores de serviços de saúde.

**Normativo vigente:** RN 501/2022 (e atualizações)

**Obrigações:**
- Troca eletrônica de informações no formato padronizado
- Uso de certificado digital ICP-Brasil quando exigido
- Vedação de exigir envio em papel do equivalente ao conteúdo trocado via TISS com certificado digital

### 2.2 Tabela TUSS

A Terminologia Unificada da Saúde Suplementar (TUSS) padroniza códigos de procedimentos, materiais e medicamentos.

**Normativo:** IN DIDES nº 44/2010

**Obrigação:** Operadoras e prestadores devem adotar obrigatoriamente a TUSS para identificação de procedimentos.

### 2.3 Penalidades (RN 489/2022)

O descumprimento das normas relativas ao padrão TISS pode acarretar:

| Penalidade | Dispositivo | Valor |
|------------|-------------|-------|
| Multa por descumprimento do padrão essencial obrigatório | Art. 47, RN 489/2022 | **R$ 35.000,00** |
| Multa diária | Art. 13, RN 489/2022 | **R$ 5.000,00/dia** |
| Advertência | Art. 47, RN 489/2022 | - |

**Nota:** Valores podem ser multiplicados conforme situação econômica do infrator e gravidade da infração.

---

## 3. Mapa de Papéis: Controlador e Operador

Conforme LGPD, **controlador** é quem toma decisões sobre o tratamento de dados, e **operador** é quem realiza o tratamento em nome do controlador.

### 3.1 Matriz de Responsabilidades

| Fluxo | Controlador | Operador | Base Legal Principal |
|-------|-------------|----------|----------------------|
| Médico gera relatório de solicitação | Médico / Clínica | Plataforma OPME | Obrigação legal (TISS) |
| Distribuidor oferece ferramenta a médicos | Distribuidor | Plataforma OPME | Consentimento + Obrigação legal |
| RPA coleta cotações em portais | Distribuidor | Plataforma OPME | Execução de contrato |
| Armazenamento de relatórios assinados | Médico / Clínica | Plataforma OPME | Obrigação legal (guarda documental) |
| Geração de orçamentos | Distribuidor | Plataforma OPME | Execução de contrato |
| Analytics e relatórios agregados | Plataforma OPME | - | Legítimo interesse (dados anonimizados) |

### 3.2 Obrigações por Papel

**Controlador (Médico/Clínica/Distribuidor):**
- Definir finalidades do tratamento
- Garantir base legal adequada
- Responder a solicitações de titulares
- Notificar incidentes à ANPD quando aplicável

**Operador (Plataforma OPME):**
- Tratar dados conforme instruções do controlador
- Implementar medidas de segurança
- Manter registros de operações
- Auxiliar controlador no atendimento a titulares

---

## 4. Assinatura Eletrônica e Digital

### 4.1 Marco Legal

- **MP 2.200-2/2001:** Institui a ICP-Brasil
- **Lei 14.063/2020:** Dispõe sobre assinaturas eletrônicas

### 4.2 Tipos de Assinatura

| Tipo | Características | Uso na Plataforma |
|------|-----------------|-------------------|
| Simples | Identificação básica | Aceite de termos |
| Avançada | Vinculação inequívoca ao signatário | Aprovação de orçamentos |
| Qualificada (ICP-Brasil) | Certificado digital | Assinatura de guias TISS |

### 4.3 Requisitos para Guias TISS

Conforme componente organizacional do padrão TISS, a mensagem de envio de documentos deve ser assinada com certificado digital quando exigido pela operadora ou normativo específico.

---

## 5. Governança de Dados

### 5.1 Minimização de Dados

A plataforma coleta apenas dados necessários para:
- Geração de relatórios e guias TISS
- Processamento de cotações
- Auditoria e rastreabilidade

### 5.2 Retenção de Dados

| Tipo de Dado | Período de Retenção | Fundamento |
|--------------|---------------------|------------|
| Relatórios assinados | 20 anos | Prazo prescricional saúde |
| Logs de auditoria | 5 anos | Compliance e investigação |
| Dados de cotações | 5 anos | Obrigações fiscais/comerciais |
| Dados de usuário | Enquanto ativo + 5 anos | Legítimo interesse |

### 5.3 Transferência Internacional

Se dados forem processados fora do Brasil (ex.: serviços de IA em nuvem), aplica-se Art. 33 da LGPD:
- Garantias contratuais (cláusulas-padrão)
- Consentimento específico para transferência
- País com nível adequado de proteção

---

## 6. Referências Normativas

| Normativo | Descrição |
|-----------|-----------|
| Lei 13.709/2018 | Lei Geral de Proteção de Dados (LGPD) |
| RN 501/2022 | Padrão TISS (ANS) |
| RN 489/2022 | Penalidades e sanções (ANS) |
| IN DIDES 44/2010 | Obrigatoriedade da TUSS |
| MP 2.200-2/2001 | ICP-Brasil |
| Lei 14.063/2020 | Assinaturas eletrônicas |

---

## 7. Contato para Questões de Privacidade

Para exercer direitos previstos na LGPD ou esclarecer dúvidas sobre tratamento de dados:

- **E-mail:** privacidade@opme-platform.com.br
- **Encarregado (DPO):** [A definir conforme Art. 41 LGPD]

---

*Documento atualizado em: Fevereiro/2026*
*Versão: 1.0*
