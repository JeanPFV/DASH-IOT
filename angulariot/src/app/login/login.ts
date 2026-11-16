import { Component } from '@angular/core';
import { Router, RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatSnackBar, MatSnackBarModule, MatSnackBarConfig } from '@angular/material/snack-bar';
import { Logar } from '../services/logar/logar';

@Component({
  selector: 'app-login',
  imports: [RouterModule, FormsModule, MatSnackBarModule],
  templateUrl: './login.html',
  styleUrl: './login.css'
})
export class Login {

  email = '';
  senha = '';
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

  private entrar(usuario: any) {
    sessionStorage.setItem('usuario', JSON.stringify(usuario));
    this.notificar(`Bem-vindo(a), ${usuario?.nome ?? ''}!`, 'success', 3000);
    this.router.navigate(['/dashboard']);
  }

  // Login com e-mail e senha
  login() {
    this.logarService.logarUsuario(this.email, this.senha).subscribe({
      next: (res) => this.entrar(res),
      error: (err) => {
        console.error(err);
        this.notificar('E-mail ou senha incorretos.', 'error');
      }
    });
  }

  // Login com digital: o ESP32 espera o dedo por até 20 s
  loginDigital() {
    if (this.aguardandoDigital) return;
    this.aguardandoDigital = true;
    this.notificar('Coloque o dedo no sensor...', 'info', 0);

    this.logarService.logarDigital().subscribe({
      next: (res) => {
        this.aguardandoDigital = false;
        this.snackBar.dismiss();
        if (res.status === 'success' && res.match) {
          this.entrar(res.user);
        } else if (res.status === 'success') {
          this.notificar('Digital não reconhecida. A tentativa foi registrada.', 'error');
        } else {
          this.notificar(res.message, 'error');
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
}
