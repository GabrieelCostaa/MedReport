import { apiRequest } from './client';

export type QuotesListParams = { portal?: string; status?: string };

export const quotesApi = {
  list(params: QuotesListParams = {}) {
    const sp = new URLSearchParams(params as Record<string, string>).toString();
    return apiRequest<{ items: { id: string; external_id: string; portal: string; description: string; status: string; deadline?: string; created_at: string }[] }>(
      `/quotes?${sp}`
    );
  },

  get(id: string) {
    return apiRequest<{
      id: string;
      portal: string;
      description: string;
      status: string;
      deadline?: string;
      created_at: string;
      items?: unknown[];
    }>(`/quotes/${id}`);
  },

  createBudget(quoteId: string, payload: { items: { product: string; price: number; qty: number }[]; notes?: string }) {
    return apiRequest<{ id: string }>(`/quotes/${quoteId}/budget`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  submitBudget(quoteId: string, budgetId: string) {
    return apiRequest<void>(`/quotes/${quoteId}/budget/${budgetId}/submit`, { method: 'POST' });
  },
};
