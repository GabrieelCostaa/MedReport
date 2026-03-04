import { apiRequest } from './client';

export const aiAssistantApi = {
  chat(message: string) {
    return apiRequest<{ reply: string; report_id?: string }>('/ai/chat', {
      method: 'POST',
      body: JSON.stringify({ message }),
    });
  },
};
