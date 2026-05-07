const API_BASE = '/api';

function formatErrorDetail(detail: unknown): string | null {
  if (detail == null) return null;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (typeof d === 'string') return d;
        if (d && typeof d === 'object' && 'msg' in d) return String((d as { msg: unknown }).msg);
        return JSON.stringify(d);
      })
      .join('; ');
  }
  if (typeof detail === 'object' && 'msg' in detail) return String((detail as { msg: unknown }).msg);
  return JSON.stringify(detail);
}

function getToken(): string | null {
  return localStorage.getItem('token');
}

function handleUnauthorized() {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  if (!window.location.pathname.startsWith('/login')) {
    window.location.href = '/login';
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    handleUnauthorized();
    throw new Error('Sessão expirada. Faça login novamente.');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatErrorDetail((err as { detail?: unknown }).detail) ?? 'Request failed');
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function apiBlob(path: string): Promise<Blob> {
  const token = getToken();
  const headers: HeadersInit = {};
  if (token) (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, { headers });
  if (res.status === 401) {
    handleUnauthorized();
    throw new Error('Sessão expirada. Faça login novamente.');
  }
  if (!res.ok) throw new Error('Download failed');
  return res.blob();
}
