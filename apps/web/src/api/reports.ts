import { apiRequest, apiBlob } from './client';

export type ReportCreatePayload = {
  cid: string;
  diagnosis: string;
  surgery_description: string;
  materials?: string;
  health_plan?: string;
};

export const reportsApi = {
  list() {
    return apiRequest<{ id: string; status: string; created_at: string; patient_diagnosis?: string }[]>(
      '/reports'
    );
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

  sign(id: string) {
    return apiRequest<void>(`/reports/${id}/sign`, { method: 'POST' });
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
