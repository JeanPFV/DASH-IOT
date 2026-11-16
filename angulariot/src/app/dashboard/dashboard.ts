import { Component, OnDestroy, OnInit, computed, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { SideBar } from '../side-bar/side-bar';
import { AcessoDia, AcessosService, DashboardAcessos } from '../services/acessos/acessos';

const DIAS_SEMANA = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];
const ATUALIZAR_A_CADA_MS = 10000;

@Component({
  selector: 'app-dashboard',
  imports: [SideBar, DatePipe],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css'
})
export class Dashboard implements OnInit, OnDestroy {

  readonly periodos = [7, 14, 30];
  readonly dias = signal(14);
  readonly dados = signal<DashboardAcessos | null>(null);
  readonly erro = signal('');
  readonly atualizadoEm = signal<Date | null>(null);
  readonly colunaEmFoco = signal<number | null>(null);
  readonly usuario: any = JSON.parse(sessionStorage.getItem('usuario') || '{}');

  // Escala do eixo Y com números redondos (0, 2, 4, 6...)
  readonly escala = computed(() => {
    const porDia = this.dados()?.por_dia ?? [];
    const maior = Math.max(1, ...porDia.map(d => d.sucesso + d.falha));
    const bruto = maior / 4;
    const potencia = Math.pow(10, Math.floor(Math.log10(bruto)));
    const passo = Math.max(1, [1, 2, 5, 10].map(m => m * potencia).find(p => p >= bruto) ?? 1);
    const topo = Math.ceil(maior / passo) * passo;
    const marcas: number[] = [];
    for (let v = 0; v <= topo; v += passo) marcas.push(v);
    return { topo, marcas };
  });

  readonly maiorRanking = computed(() =>
    Math.max(1, ...(this.dados()?.por_usuario ?? []).map(u => u.total))
  );

  private timer?: ReturnType<typeof setInterval>;

  constructor(private acessosService: AcessosService) {}

  ngOnInit() {
    this.carregar();
    this.timer = setInterval(() => this.carregar(), ATUALIZAR_A_CADA_MS);
  }

  ngOnDestroy() {
    clearInterval(this.timer);
  }

  mudarPeriodo(dias: number) {
    this.dias.set(dias);
    this.carregar();
  }

  carregar() {
    this.acessosService.getDashboard(this.dias()).subscribe({
      next: (res) => {
        this.dados.set(res);
        this.erro.set('');
        this.atualizadoEm.set(new Date());
      },
      error: (err) => {
        console.error(err);
        this.erro.set('Não foi possível carregar os acessos. O backend está rodando?');
      }
    });
  }

  // ---- gráfico ----

  altura(valor: number) {
    return (valor / this.escala().topo) * 100;
  }

  // '2026-11-05' -> '05/11' (sem new Date(iso), que joga o dia pra trás no fuso do Brasil)
  rotuloDia(iso: string) {
    const [, mes, dia] = iso.split('-');
    return `${dia}/${mes}`;
  }

  diaDaSemana(iso: string) {
    const [ano, mes, dia] = iso.split('-').map(Number);
    return DIAS_SEMANA[new Date(ano, mes - 1, dia).getDay()];
  }

  // Com muitos dias, mostra só alguns rótulos no eixo X (sempre inclui hoje)
  mostrarRotulo(indice: number, total: number) {
    const passo = total <= 7 ? 1 : total <= 14 ? 2 : 5;
    return (total - 1 - indice) % passo === 0;
  }

  descricaoColuna(d: AcessoDia) {
    return `${this.rotuloDia(d.dia)}: ${d.sucesso} liberados, ${d.falha} negados`;
  }

  // ---- ranking ----

  larguraRanking(total: number) {
    return (total / this.maiorRanking()) * 100;
  }

  taxaSucesso(d: DashboardAcessos) {
    return d.resumo.total ? Math.round((d.resumo.sucesso / d.resumo.total) * 100) : 0;
  }
}
