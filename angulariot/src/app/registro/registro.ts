import { Component } from '@angular/core';
import { Router, RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatSnackBar, MatSnackBarModule, MatSnackBarConfig } from '@angular/material/snack-bar';
import { Logar } from '../services/logar/logar';

@Component({
  selector: 'app-registro',
  imports: [RouterModule, FormsModule, MatSnackBarModule],
  templateUrl: './registro.html',
  styleUrls: ['../login/login.css', './registro.css']
})
export class Registro {

  nome = '';
  email = '';
  senha = '';
  senhaConfirmar = '';
  aguardandoDigital = false;

  constructor(
    private logarService: Logar,
    private router: Router,
    private snackBar: MatSnackBar
  ) {}

  private notificar(mensagem: string, tipo: 'success' | 'error' | 'info' = 'info', duracao = 5000) {
    const config: MatSnackBarConfig = {
      duration: duracao,
      horizontalPosition: 'end',
      verticalPosition: 'top',
      panelClass: [`snackbar-${tipo}`]
    };
    this.snackBar.open(mensagem, 'OK', config);
  }

  private dadosValidos() {
    if (!this.nome || !this.email || !this.senha) {
      this.notificar('Preencha nome, e-mail e senha.', 'error');
      return false;
    }
    if (this.senha !== this.senhaConfirmar) {
      this.notificar('As senhas precisam ser iguais.', 'error');
      return false;
    }
    return true;
  }

  // Cadastro com digital: o ESP32 pede o dedo duas vezes (até 45 s)
  cadastrarComDigital() {
    if (this.aguardandoDigital || !this.dadosValidos()) return;
    this.aguardandoDigital = true;
    this.notificar('Coloque o dedo no sensor, tire e coloque o MESMO dedo de novo.', 'info', 0);

    this.logarService.criarUsuarioDigital(this.nome, this.email, this.senha).subscribe({
      next: (res) => {
        this.aguardandoDigital = false;
        this.snackBar.dismiss();
        if (res.status === 'success') {
          this.notificar('Digital cadastrada! Agora entre usando a digital.', 'success', 4000);
          this.router.navigate(['/login']);
        } else {
          this.notificar('Não foi possível cadastrar: ' + res.message, 'error', 7000);
        }
      },
      error: (err) => {
        this.aguardandoDigital = false;
        this.snackBar.dismiss();
        console.error(err);
        this.notificar('Falha na comunicação com o servidor.', 'error');
      }
    });
  }

  // Cadastro só com e-mail e senha (sem digital)
  cadastrarSomenteSenha() {
    if (!this.dadosValidos()) return;
    this.logarService.criarUsuario(this.nome, this.email, this.senha).subscribe({
      next: () => {
        this.notificar('Usuário cadastrado! Entre com e-mail e senha.', 'success', 3000);
        this.router.navigate(['/login']);
      },
      error: (err) => {
        console.error(err);
        this.notificar('Falha no cadastro. Esse e-mail pode já estar em uso.', 'error');
      }
    });
  }
}
