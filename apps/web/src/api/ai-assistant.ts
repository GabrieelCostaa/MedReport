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
  referencias?: (string | ReferenceItem)[];
  diagnostico_resumo?: string;
  falha_terapeutica?: string;
  risco_nao_realizacao?: string;
  base_legal?: string;
  sugestao_tuss?: string;
  especialidade?: string;
  report_id?: string;
  error?: string;
  usage?: PipelineUsage;
  // ANS Compliance
  approval_score?: number;
  approval_nivel?: string;
  approval_componentes?: Record<string, number | string>;
  approval_explicacao?: string[];
  approval_alertas?: string[];
  approval_gaps?: string[];
  compliance_mode?: string;
  stf_checklist?: Record<string, unknown>;
  dut_suggestions?: string[];
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

export interface ReferenceItem {
  texto: string;
  doi?: string;
  pmid?: string;
  link?: string;
  source?: string;
}

export const aiAssistantApi = {
  startReportStream(
    data: {
      product_id: string;
      paciente_nome: string;
      cid: string;
      diagnostico: string;
      surgery_description?: string;
      health_plan?: string;
      especialidade?: string;
    },
    onStep: (step: string, label: string) => void,
    onDone: (result: PipelineResult) => void,
    onError: (err: Error) => void,
  ) {
    const token = localStorage.getItem('token');
    const controller = new AbortController();

    fetch('/api/ai/start-report-stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(data),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error('Stream failed');
        const reader = response.body?.getReader();
        if (!reader) throw new Error('No reader');
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          let eventType = 'step';
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
              try {
                const parsed = JSON.parse(line.slice(6));
                if (eventType === 'done') {
                  onDone(parsed as PipelineResult);
                } else {
                  onStep(parsed.step || '', parsed.message || '');
                }
              } catch { /* skip malformed */ }
            }
          }
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') onError(err);
      });

    return controller;
  },

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

  answerStream(
    session_id: string,
    answers: Record<string, string>,
    onStep: (step: string, label: string) => void,
    onDone: (result: PipelineResult) => void,
    onError: (err: Error) => void,
  ) {
    const token = localStorage.getItem('token');
    const controller = new AbortController();

    fetch('/api/ai/answer-stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ session_id, answers }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error('Stream failed');
        const reader = response.body?.getReader();
        if (!reader) throw new Error('No reader');
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          let eventType = 'step';
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
              try {
                const parsed = JSON.parse(line.slice(6));
                if (eventType === 'done') {
                  onDone(parsed as PipelineResult);
                } else if (eventType === 'error') {
                  onError(new Error(parsed.error || 'Pipeline error'));
                } else {
                  onStep(parsed.step || '', parsed.message || '');
                }
              } catch { /* skip malformed */ }
            }
          }
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') onError(err);
      });

    return controller;
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

  saveEdit(data: {
    report_id: string;
    original_text: string;
    edited_text: string;
    especialidade?: string;
  }) {
    return apiRequest<{ saved: boolean; edit_type?: string; changes_count?: number }>('/ai/save-edit', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};
