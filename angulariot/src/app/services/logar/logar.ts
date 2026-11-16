import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { ApiUrl } from '../apiUrl/api-url';

@Injectable({
  providedIn: 'root'
})
export class Logar {

  private apiUrl: string;

  constructor (
    private http: HttpClient,
    private apiUrlService: ApiUrl
  ) {
    this.apiUrl = this.apiUrlService.apiUrl()
  }

  // Cadastro só com senha (sem digital)
  criarUsuario(nome: string, email: string, senha: string) {
    return this.http.post(`${this.apiUrl}/criarUsuario/`, { nome, email, senha });
  }

  // Cadastro com digital: o backend cria o usuário e pede ao ESP32 para gravar a digital
  criarUsuarioDigital(nome: string, email: string, senha: string) {
    return this.http.post<any>(`${this.apiUrl}/enroll/`, { nome, email, senha });
  }

  logarUsuario(email: string, senha: string) {
    return this.http.post(`${this.apiUrl}/login/`, { email, senha });
  }

  // Login com digital: o backend pede uma leitura ao ESP32 e devolve o usuário
  logarDigital() {
    return this.http.post<any>(`${this.apiUrl}/verify/`, {});
  }
}
