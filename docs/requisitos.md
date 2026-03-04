# Requisitos e Personas – OPME Platform

## Personas

1. **Médico**  
   Preenche relatórios de solicitação de cirurgia para obter autorização do convênio. Precisa de suporte para códigos TUSS e guias TISS corretas para evitar glosas.

2. **Distribuidor OPME**  
   Acompanha relatórios dos médicos, responde cotações em vários portais de planos de saúde e precisa de central unificada e automação (RPA) para ganho de escala.

3. **Admin**  
   Gerencia usuários, planos (básico/premium) e configurações da plataforma.

## Portais de cotações (MVP)

Para o MVP, priorizar 2–3 portais conforme disponibilidade de acesso e estabilidade da interface:

- Definir em workshop com distribuidores: nomes dos portais, URLs de login e de listagem de cotações.
- Cada portal terá um script RPA específico (ex.: `services/rpa/portais/portal_x.py`) com seletores e fluxos de login/extração.

## Requisitos funcionais (resumo)

| Módulo | Requisito |
|--------|-----------|
| Auth | Cadastro, login (OAuth2/JWT), RBAC (médico, distribuidor, admin), termo de consentimento LGPD |
| Relatórios | Criação por formulário e por assistente (chat); sugestão TUSS; geração guia TISS XML/PDF; revisão (upload/texto); assinatura digital |
| TUSS | Consulta por código e por texto; atualização periódica a partir da ANS |
| Cotações | Listagem com filtros; ingestão via RPA; orçamentos (criar, aprovar, enviar); status (pendente, enviado, ganho, perdido) |
| ERP | Pull de preços e estoque; webhook de sincronização de cotações (mock disponível) |
| Notificações | Alertas para novas cotações e prazos (email/in-app); preferências por usuário |

## Requisitos não funcionais

- **Segurança**: TLS, criptografia em repouso, RBAC, logs de auditoria.
- **LGPD**: Bases legais conforme Art. 11 (não apenas consentimento):
  - Obrigação legal/regulatória (TISS/ANS) para geração de guias
  - Tutela da saúde para processamento de procedimentos
  - Consentimento para funcionalidades opcionais
  - Minimização de dados, direito de exclusão/portabilidade
  - Mapa de papéis controlador/operador por fluxo (ver [compliance.md](compliance.md))
- **TISS/TUSS**: Conformidade com RN 501/2022 e IN DIDES 44/2010. Penalidades: R$ 35.000,00 (Art. 47, RN 489/2022) e R$ 5.000,00/dia (Art. 13).
- **Disponibilidade**: Monitoramento de saúde dos serviços e dos robôs RPA.
