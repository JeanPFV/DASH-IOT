import { inject, provideAppInitializer } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import { App } from './app/app';
import { provideRouter } from '@angular/router';
import { routes } from './app/app.routes';
import { HttpClient, provideHttpClient, withFetch, withXsrfConfiguration } from '@angular/common/http';
import { IMAGE_CONFIG } from '@angular/common';
import { catchError, of } from 'rxjs';

const appConfig = {
  providers: [provideRouter(routes),
  // Lê o cookie csrftoken do Django e o envia no header X-CSRFToken em todo POST
  provideHttpClient(
    withFetch(),
    withXsrfConfiguration({ cookieName: 'csrftoken', headerName: 'X-CSRFToken' })
  ),
  // Antes de abrir a tela, pede ao Django o cookie CSRF (GET /api/csrf/).
  // Se o back-end estiver fora do ar, a tela abre mesmo assim (os POSTs falham com 403).
  provideAppInitializer(() => inject(HttpClient).get('/api/csrf/').pipe(catchError(() => of(null)))),
  {
    provide: IMAGE_CONFIG,
    useValue: {
      disableImageSizeWarning: true, 
      disableImageLazyLoadWarning: true
    }
  },]
};

bootstrapApplication(App, appConfig)
  .catch((err) => console.error(err));