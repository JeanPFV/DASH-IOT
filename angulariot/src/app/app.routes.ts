import { Routes } from '@angular/router';
import { authGuard } from './services/auth/auth-guard';

export const routes: Routes = [
    {
        path: 'login',
        loadComponent: () => import('./login/login').then(m => m.Login),
    },
    {
        path: 'registro',
        loadComponent: () => import('./registro/registro').then(m => m.Registro)
    },
    {
        path: 'dashboard',
        canActivate: [authGuard],
        loadComponent: () => import('./dashboard/dashboard').then(m => m.Dashboard)
    },
    // Sem login o guard manda para /login
    { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
    { path: '**', redirectTo: 'dashboard' }
];
