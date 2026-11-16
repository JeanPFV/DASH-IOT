import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

// Só deixa abrir a rota se alguém fez login (por digital ou senha)
export const authGuard: CanActivateFn = () => {
  if (sessionStorage.getItem('usuario')) {
    return true;
  }
  return inject(Router).createUrlTree(['/login']);
};
