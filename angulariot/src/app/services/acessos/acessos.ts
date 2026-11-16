import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { ApiUrl } from '../apiUrl/api-url';

export interface AcessoDia {
  dia: string;        // 'AAAA-MM-DD' (dia local)
  sucesso: number;
  falha: number;
}

export interface AcessoRecente {
  id: number;
  quando: string;     // ISO com fuso
  usuario: string | null;
  email: string | null;
  metodo: 'digital' | 'senha';
  sucesso: boolean;
  confianca: number | null;
  detalhe: string | null;
}

export interface DashboardAcessos {
  dias: number;
  resumo: {
    total: number;
    sucesso: number;
    falha: number;
    por_digital: number;
    hoje: number;
    usuarios_distintos: number;
    usuarios_com_digital: number;
  };
  por_dia: AcessoDia[];
  por_usuario: { usuario_id: number; nome: string | null; total: number }[];
  ultimos: AcessoRecente[];
}

@Injectable({
  providedIn: 'root'
})
export class AcessosService {

  constructor(
    private http: HttpClient,
    private apiUrl: ApiUrl
  ) {}

  getDashboard(dias: number) {
    return this.http.get<DashboardAcessos>(`${this.apiUrl.apiUrl()}/acessos/?dias=${dias}`);
  }
}
