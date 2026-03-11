import { apiRequest } from './client';

export interface EvidencePreviewItem {
  autor: string;
  ano: string;
  tipo: string;
  titulo_curto: string;
  pmid: string;
}

export interface EvidencesPreview {
  cid: string;
  internal_count: number;
  pubmed_count: number;
  total_count: number;
  preview: EvidencePreviewItem[];
}

export const evidencesApi = {
  preview(cid: string, productName?: string) {
    const params = new URLSearchParams({ cid });
    if (productName) params.set('product_name', productName);
    return apiRequest<EvidencesPreview>(`/ai/evidences-preview?${params}`);
  },
};
