import { apiRequest } from './client';

export interface Product {
  id: string;
  nome: string;
  linha: string;
  descricao_tecnica: string;
  diferenciais_clinicos: string;
  codigo_tuss_sugerido: string;
  registro_anvisa: string;
  indicacoes?: string;
  contraindicacoes?: string;
  viscosidade?: string;
  peso_molecular?: string;
  concentracao?: string;
  bula_url?: string;
  referencias_bibliograficas?: string[];
}

export const productsApi = {
  list(q?: string) {
    const params = q ? `?q=${encodeURIComponent(q)}` : '';
    return apiRequest<{ items: Product[] }>(`/products${params}`);
  },

  get(id: string) {
    return apiRequest<Product>(`/products/${id}`);
  },
};
