import json
import logging
from datetime import timedelta

from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Acessos, Usuarios
from . import telegram_alertas as telegram
from .mqtt_sensor import SensorIndisponivel, enviar_comando
from .serializer import UsuariosSeriliazer

logger = logging.getLogger(__name__)

# O ESP32 desiste depois de 20 s (verificar) / 45 s (cadastrar); o backend espera um pouco mais
TEMPO_VERIFICAR = 25
TEMPO_CADASTRO = 50


def registrar_acesso(metodo, sucesso, usuario=None, confianca=None, detalhe=None):
    """Grava a tentativa de login na tabela acessos (Supabase). Nunca derruba o login."""
    try:
        Acessos.objects.create(
            usuario=usuario,
            metodo=metodo,
            sucesso=sucesso,
            confianca=confianca,
            detalhe=detalhe[:120] if detalhe else None,
        )
    except Exception:
        logger.exception('Não foi possível registrar o acesso')

    # Alerta no Telegram (roda em segundo plano; nunca derruba o login)
    if not telegram.configurado():
        return
    try:
        if sucesso:
            telegram.aviso_acesso_liberado(usuario, metodo, confianca)
        else:
            desde = timezone.now() - timedelta(minutes=telegram.NEGADOS_JANELA_MIN)
            negados = Acessos.objects.filter(sucesso=False, criado_em__gte=desde).count()
            telegram.alerta_acesso_negado(metodo, detalhe, usuario, confianca, negados)
    except Exception:
        logger.exception('Não foi possível enviar o alerta ao Telegram')


def senha_confere(usuario, senha):
    if not senha or not usuario.senha:
        return False
    try:
        identify_hasher(usuario.senha)
    except ValueError:
        # Senha antiga salva em texto puro: confere e já troca por hash
        if usuario.senha == senha:
            usuario.senha = make_password(senha)
            usuario.save(update_fields=['senha'])
            return True
        return False
    return check_password(senha, usuario.senha)


def primeiro_erro(errors):
    campo, mensagens = next(iter(errors.items()))
    return f'{campo}: {mensagens[0]}'


class UsuariosGET(APIView):

    def post(self, request):
        email = request.data.get('email')
        senha = request.data.get('senha')

        usuario = Usuarios.objects.filter(email=email).first()
        if usuario is None or not senha_confere(usuario, senha):
            detalhe = 'Senha incorreta' if usuario else f'E-mail não cadastrado: {email}'
            registrar_acesso('senha', False, usuario=usuario, detalhe=detalhe)
            return Response({"erro": "Usuário não encontrado"}, status=status.HTTP_404_NOT_FOUND)

        registrar_acesso('senha', True, usuario=usuario)
        serializer = UsuariosSeriliazer(usuario)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CriarUsuario(APIView):
    def post(self, request):
        serializer = UsuariosSeriliazer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"Sucesso": "Usuário salvo com sucesso!"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
def enroll_fingerprint(request):
    """Cria o usuário no Supabase e manda o ESP32 gravar a digital na posição = id do usuário."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método inválido'}, status=405)
    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    serializer = UsuariosSeriliazer(data={
        'nome': data.get('nome', ''),
        'email': data.get('email', ''),
        'senha': data.get('senha', ''),
    })
    if not serializer.is_valid():
        return JsonResponse({'status': 'error', 'message': primeiro_erro(serializer.errors)})
    usuario = serializer.save()

    try:
        resposta = enviar_comando('cadastrar', timeout=TEMPO_CADASTRO, id=usuario.id)
    except SensorIndisponivel as e:
        usuario.delete()
        telegram.alerta_sensor_indisponivel(str(e))
        return JsonResponse({'status': 'error', 'message': str(e)})

    if resposta.get('status') != 'ok':
        # Sem digital gravada: desfaz o cadastro para a pessoa poder tentar de novo
        usuario.delete()
        return JsonResponse({'status': 'error', 'message': resposta.get('msg', 'Falha ao cadastrar a digital')})

    usuario.digital = {'slot': usuario.id, 'cadastrada_em': timezone.now().isoformat()}
    usuario.save(update_fields=['digital'])
    telegram.aviso_digital_cadastrada(usuario)
    return JsonResponse({
        'status': 'success',
        'message': 'Digital cadastrada',
        'user': UsuariosSeriliazer(usuario).data,
    })


@csrf_exempt
def verify_fingerprint(request):
    """Pede uma leitura ao ESP32, identifica o usuário e registra o acesso no Supabase."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método inválido'}, status=405)

    try:
        resposta = enviar_comando('verificar', timeout=TEMPO_VERIFICAR)
    except SensorIndisponivel as e:
        telegram.alerta_sensor_indisponivel(str(e))
        return JsonResponse({'status': 'error', 'message': str(e)})

    if resposta.get('status') != 'ok':
        return JsonResponse({'status': 'error', 'message': resposta.get('msg', 'Falha na leitura')})

    if not resposta.get('match'):
        registrar_acesso('digital', False, detalhe='Digital não reconhecida')
        return JsonResponse({'status': 'success', 'match': False})

    slot = resposta.get('id')
    confianca = resposta.get('confianca')
    usuario = Usuarios.objects.filter(id=slot).first()
    if usuario is None:
        registrar_acesso('digital', False, confianca=confianca,
                         detalhe=f'Digital da posição {slot} sem usuário no banco')
        return JsonResponse({'status': 'error',
                             'message': 'Digital reconhecida, mas o usuário não existe mais no banco'})

    registrar_acesso('digital', True, usuario=usuario, confianca=confianca)
    return JsonResponse({
        'status': 'success',
        'match': True,
        'user': UsuariosSeriliazer(usuario).data,
    })


class AcessosDashboard(APIView):
    """GET /api/acessos/?dias=14 -> números, gráfico por dia, ranking e últimos acessos."""

    def get(self, request):
        try:
            dias = int(request.GET.get('dias', 14))
        except ValueError:
            dias = 14
        dias = max(1, min(dias, 90))

        hoje = timezone.localdate()
        inicio = hoje - timedelta(days=dias - 1)
        periodo = Acessos.objects.filter(criado_em__date__gte=inicio)

        # Os apelidos (n_...) não podem ter o mesmo nome de um campo do model
        # (ex.: "sucesso"), senão o Q(sucesso=...) seguinte passa a apontar pro Count.
        totais = periodo.aggregate(
            n_total=Count('id'),
            n_sucesso=Count('id', filter=Q(sucesso=True)),
            n_falha=Count('id', filter=Q(sucesso=False)),
            n_digital=Count('id', filter=Q(sucesso=True, metodo='digital')),
        )

        linhas = (periodo.annotate(dia=TruncDate('criado_em'))
                  .values('dia')
                  .annotate(n_sucesso=Count('id', filter=Q(sucesso=True)),
                            n_falha=Count('id', filter=Q(sucesso=False)))
                  .order_by())
        por_data = {linha['dia']: linha for linha in linhas}
        por_dia = []
        for i in range(dias):
            dia = inicio + timedelta(days=i)
            linha = por_data.get(dia, {})
            por_dia.append({'dia': dia.isoformat(),
                            'sucesso': linha.get('n_sucesso', 0),
                            'falha': linha.get('n_falha', 0)})

        ranking = (periodo.filter(sucesso=True, usuario__isnull=False)
                   .values('usuario_id', 'usuario__nome')
                   .annotate(total=Count('id'))
                   .order_by('-total')[:8])

        ultimos = Acessos.objects.select_related('usuario').order_by('-criado_em')[:30]

        return Response({
            'dias': dias,
            'resumo': {
                'total': totais['n_total'],
                'sucesso': totais['n_sucesso'],
                'falha': totais['n_falha'],
                'por_digital': totais['n_digital'],
                'hoje': periodo.filter(criado_em__date=hoje, sucesso=True).count(),
                'usuarios_distintos': periodo.filter(sucesso=True, usuario__isnull=False)
                                             .values('usuario_id').distinct().count(),
                'usuarios_com_digital': Usuarios.objects.filter(digital__isnull=False).count(),
            },
            'por_dia': por_dia,
            'por_usuario': [{'usuario_id': r['usuario_id'], 'nome': r['usuario__nome'], 'total': r['total']}
                            for r in ranking],
            'ultimos': [{
                'id': a.id,
                'quando': timezone.localtime(a.criado_em).isoformat(),
                'usuario': a.usuario.nome if a.usuario else None,
                'email': a.usuario.email if a.usuario else None,
                'metodo': a.metodo,
                'sucesso': a.sucesso,
                'confianca': a.confianca,
                'detalhe': a.detalhe,
            } for a in ultimos],
        })
