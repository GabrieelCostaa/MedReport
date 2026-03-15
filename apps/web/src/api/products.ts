import { apiRequest } from './client';

export interface Product {
  id: string;
  nome: string;
  linha: string;
  descricao_tecnica: string;
  diferenciais_clinicos: string;
  codigo_tuss_sugerido: string;
  registro_anvisa: string;
  classe_risco?: string;
  source?: 'catalog' | 'anvisa';
  indicacoes?: string;
  contraindicacoes?: string;
  viscosidade?: string;
  peso_molecular?: string;
  concentracao?: string;
  bula_url?: string;
  referencias_bibliograficas?: string[];
}

export type QuickProductPayload = {
  nome: string;
  registro_anvisa?: string;
  fabricante?: string;
  codigo_tuss_sugerido?: string;
};

export const productsApi = {
  list(q?: string) {
    const params = q ? `?q=${encodeURIComponent(q)}` : '';
    return apiRequest<{ items: Product[] }>(`/products${params}`);
  },

  get(id: string) {
    return apiRequest<Product>(`/products/${id}`);
  },

  /** Cadastro rápido de produto */
  create(payload: QuickProductPayload) {
    return apiRequest<{ id: string; nome: string; registro_anvisa?: string; codigo_tuss_sugerido?: string }>(
      '/products',
      { method: 'POST', body: JSON.stringify(payload) },
    );
  },

  /** Cria produto no catálogo a partir de registro ANVISA */
  createFromAnvisa(registro: string) {
    return apiRequest<{ id: string; nome: string; linha?: string; registro_anvisa?: string; codigo_tuss_sugerido?: string; already_exists?: boolean }>(
      `/products/from-anvisa/${registro}`,
      { method: 'POST' },
    );
  },
};
