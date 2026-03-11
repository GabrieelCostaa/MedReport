import { apiRequest } from './client';

export interface QuestionOption {
  id: string;
  texto: string;
}

export interface PipelineQuestion {
  secao: string;
  pergunta: string;
  opcoes: QuestionOption[];
}

export interface AuditLogEntry {
  tipo: string;
  campo: string;
  original: string;
  corrigido: string;
  motivo: string;
}

export interface TokenAgentUsage {
  agent: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  cost_brl: number;
}

export interface PipelineUsage {
  agents: TokenAgentUsage[];
  totals: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cost_usd: number;
    cost_brl: number;
  };
}

export interface PipelineResult {
  session_id: string;
  step: 'questions' | 'done';
  questions?: PipelineQuestion[];
  justificativa?: string;
  aprovado?: boolean;
  checklist?: Record<string, boolean>;
  audit_log?: AuditLogEntry[];
  referencias?: string[];
  diagnostico_resumo?: string;
  falha_terapeutica?: string;
  risco_nao_realizacao?: string;
  base_legal?: string;
  sugestao_tuss?: string;
  especialidade?: string;
  report_id?: string;
  error?: string;
  usage?: PipelineUsage;
}

export interface ChecklistItem {
  ok: boolean;
  label: string;
}

export interface ChecklistResult {
  approved: boolean;
  checklist: Record<string, ChecklistItem>;
  missing: string[];
}

export const aiAssistantApi = {
  chat(message: string) {
    return apiRequest<{ reply: string; report_id?: string }>('/ai/chat', {
      method: 'POST',
      body: JSON.stringify({ message }),
    });
  },

  startReport(data: {
    product_id: string;
    paciente_nome: string;
    cid: string;
    diagnostico: string;
    surgery_description?: string;
    health_plan?: string;
    especialidade?: string;
  }) {
    return apiRequest<PipelineResult>('/ai/start-report', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  answer(session_id: string, answers: Record<string, string>) {
    return apiRequest<PipelineResult>('/ai/answer', {
      method: 'POST',
      body: JSON.stringify({ session_id, answers }),
    });
  },

  generate(data: {
    product_id: string;
    paciente_nome: string;
    cid: string;
    diagnostico: string;
    surgery_description?: string;
    health_plan?: string;
    especialidade?: string;
  }) {
    return apiRequest<PipelineResult>('/ai/generate', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  regenerate(session_id: string, report_id: string | null, adjustments: Record<string, string>) {
    return apiRequest<PipelineResult>('/ai/regenerate', {
      method: 'POST',
      body: JSON.stringify({ session_id, report_id, adjustments }),
    });
  },

  getChecklist(reportId: string) {
    return apiRequest<ChecklistResult>(`/ai/checklist/${reportId}`);
  },

  quickCheck(data: {
    justificativa_ia?: string;
    diagnostico?: string;
    falha_terapeutica?: string;
    risco_nao_realizacao?: string;
    base_legal_ans?: string;
    referencias_bib?: string[];
  }) {
    return apiRequest<{ approved: boolean; checklist: Record<string, ChecklistItem> }>('/ai/quick-check', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};
