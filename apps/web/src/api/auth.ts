import { apiRequest } from './client';

export type User = {
  id: string;
  email: string;
  role: 'medico' | 'distribuidor' | 'admin';
  legal_basis_acknowledged: boolean;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  user: User;
};

export const authApi = {
  login(email: string, password: string) {
    const body = new URLSearchParams({ username: email, password });
    return fetch('/auth/token', {
      method: 'POST',
      body: body.toString(),
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        Accept: 'application/json',
      },
    }).then(async (r) => {
      if (!r.ok) throw new Error('Login failed');
      const data = await r.json();
      const user = data.user ?? (await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${data.access_token}` },
      }).then((res) => res.json()));
      return { ...data, user } as LoginResponse;
    });
  },

  register(email: string, password: string) {
    return apiRequest<LoginResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },

  acknowledgeLegalBasis() {
    return apiRequest<void>('/auth/legal-basis', { method: 'POST' });
  },

  me() {
    return apiRequest<User>('/auth/me');
  },
};
