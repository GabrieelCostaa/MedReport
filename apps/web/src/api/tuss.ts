import { apiRequest } from './client';

export const tussApi = {
  search(description: string) {
    return apiRequest<{ items: { code: string; term: string }[] }>(
      `/tuss/search?q=${encodeURIComponent(description)}`
    );
  },

  getByCode(code: string) {
    return apiRequest<{ code: string; term: string }>(`/tuss/code/${encodeURIComponent(code)}`);
  },
};
