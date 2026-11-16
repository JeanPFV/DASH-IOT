import { Component } from '@angular/core';
import { Router, RouterModule } from '@angular/router';

@Component({
  selector: 'app-side-bar',
  imports: [RouterModule],
  templateUrl: './side-bar.html',
  styleUrl: './side-bar.css'
})
export class SideBar {

  usuario: any = JSON.parse(sessionStorage.getItem('usuario') || 'null');

  constructor(private router: Router) {}

  logout() {
    sessionStorage.removeItem('usuario');
    this.router.navigate(['/login']);
  }
}
