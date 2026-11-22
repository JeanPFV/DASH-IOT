import { Injectable } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class ApiUrl {
  
  // URL relativa: o ng serve repassa /api ao Django (proxy.conf.json). Assim a API fica na
  // mesma origem do site e o Angular consegue anexar o token CSRF nos POSTs.
  apiUrl() {
    return '/api'
  }

}
