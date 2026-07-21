import { apiRequest, apiBlob } from './client';

export type ReportCreatePayload = {
  cid: string;
  diagnosis: string;
  surgery_description: string;
  materials?: string;
  health_plan?: string;
};

export type Outcome = 'pendente' | 'aprovado' | 'glosado' | 'parcial';

export type Report = {
  id: string;
  status: string;
  created_at: string;
  patient_diagnosis?: string;
  health_plan?: string;
  outcome?: Outcome;
};

export type ApprovalStats = {
  total: number;
  com_desfecho: number;
  pendentes: number;
  aprovados: number;
  glosados: number;
  parciais: number;
  taxa_aprovacao: number | null;
  calibracao_score: { faixa: string; n: number; aprovados: number; taxa: number | null }[];
  por_especialidade: { chave: string; n: number; taxa: number | null }[];
  por_operadora: { chave: string; n: number; taxa: number | null }[];
  top_motivos_glosa: { codigo: string; descricao: string; n: number }[];
};

export type PaginatedReports = {
  items: Report[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
};

export const reportsApi = {
  list(page = 1, perPage = 20) {
    return apiRequest<PaginatedReports>(
      `/reports?page=${page}&per_page=${perPage}`
    );
  },

  /** Fetch all reports (for Home dashboard stats) */
  listAll() {
    return apiRequest<PaginatedReports>('/reports?page=1&per_page=1000');
  },

  get(id: string) {
    return apiRequest<{
      id: string;
      status: string;
      cid?: string;
      diagnosis?: string;
      surgery_description?: string;
      materials?: string;
      health_plan?: string;
      created_at: string;
      inconsistencies?: { field: string; message: string }[];
    }>(`/reports/${id}`);
  },

  create(payload: ReportCreatePayload) {
    return apiRequest<{ id: string }>('/reports', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /** Registra o desfecho real do laudo na operadora (loop de prova de valor) */
  markOutcome(id: string, outcome: Outcome, motivo_codigo?: string, notes?: string) {
    return apiRequest<{ id: string; outcome: Outcome; outcome_at: string | null }>(
      `/reports/${id}/outcome`,
      { method: 'PATCH', body: JSON.stringify({ outcome, motivo_codigo, notes }) }
    );
  },

  approvalStats() {
    return apiRequest<ApprovalStats>('/reports/stats/approval');
  },

  sign(id: string) {
    return apiRequest<{
      signed_at: string;
      signature_hash: string;
      medico_nome: string;
      medico_crm: string;
      medico_crm_uf: string;
    }>(`/reports/${id}/sign`, { method: 'POST' });
  },

  downloadPdf(id: string) {
    return apiBlob(`/reports/${id}/download?format=pdf`);
  },

  downloadXml(id: string) {
    return apiBlob(`/reports/${id}/download?format=xml`);
  },

  downloadDocx(id: string) {
    return apiBlob(`/reports/${id}/download?format=docx`);
  },

  reviewUpload(file: File) {
    const form = new FormData();
    form.append('file', file);
    const token = localStorage.getItem('token');
    return fetch('/api/reports/review/upload', {
      method: 'POST',
      body: form,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }).then((r) => {
      if (!r.ok) throw new Error('Upload failed');
      return r.json();
    });
  },
};
