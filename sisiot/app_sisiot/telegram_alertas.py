"""
Alertas do sistema IOT no Telegram (Bot API).

Configuração no sisiot/.env:
    TELEGRAM_TOKEN=123456:ABC...      -> token do bot, dado pelo @BotFather
    TELEGRAM_CHAT_ID=123456789        -> para onde mandar (vários: separe por vírgula; grupo começa com -)
    TELEGRAM_NOTIFICAR_LIBERADOS=0    -> 1 = também avisa cada login liberado

O que é avisado:
    - acesso negado (digital não reconhecida, senha errada, e-mail não cadastrado...)
    - possível invasão: 3 ou mais negações em 10 minutos
    - nova digital cadastrada
    - sensor indisponível (no máximo 1 aviso a cada 5 minutos)
    - acesso liberado (só se TELEGRAM_NOTIFICAR_LIBERADOS=1)

Os envios rodam em segundo plano: se o Telegram estiver fora do ar ou mal configurado,
o login continua funcionando normalmente e o erro aparece só no log do Django.
"""
import html
import json
import logging
import threading
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

NEGADOS_JANELA_MIN = 10          # janela para contar negações seguidas
NEGADOS_LIMITE_INVASAO = 3       # a partir daqui o alerta vira "possível invasão"
INTERVALO_SENSOR_S = 300         # no máximo 1 aviso de sensor fora do ar a cada 5 min

METODOS = {'digital': 'Digital', 'senha': 'E-mail e senha'}

_ultimos_envios = {}
_trava = threading.Lock()


class TelegramErro(Exception):
    """O Telegram recusou o pedido (token, chat id) ou não respondeu."""


class TelegramSemConexao(TelegramErro):
    """Este computador não conseguiu falar com api.telegram.org (rede, firewall, certificado)."""


def configurado():
    return bool(settings.TELEGRAM_TOKEN and settings.TELEGRAM_CHAT_IDS)


def chamar_api(metodo, dados=None, timeout=10):
    """Chama um método da Bot API (getMe, getUpdates, sendMessage...) e devolve o "result"."""
    # A URL leva o token: nunca colocar ela em log ou mensagem de erro.
    url = f'{settings.TELEGRAM_API_URL}/bot{settings.TELEGRAM_TOKEN}/{metodo}'
    corpo = json.dumps(dados or {}).encode('utf-8')
    pedido = urllib.request.Request(url, data=corpo, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resp:
            resposta = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            descricao = json.loads(e.read().decode('utf-8')).get('description', f'HTTP {e.code}')
        except ValueError:
            descricao = f'HTTP {e.code}'
        raise TelegramErro(descricao) from None
    except (OSError, ValueError) as e:
        # O motivo (DNS, firewall, certificado, timeout) não traz a URL, então é seguro mostrar
        motivo = getattr(e, 'reason', None) or e
        raise TelegramSemConexao(f'sem resposta do Telegram: {motivo}') from None
    if not resposta.get('ok'):
        raise TelegramErro(resposta.get('description', 'resposta inválida'))
    return resposta.get('result')


def enviar_mensagem(texto, chat_ids=None):
    """Envia agora (espera a resposta). Devolve [(chat_id, erro ou None), ...]."""
    resultados = []
    for chat_id in chat_ids or settings.TELEGRAM_CHAT_IDS:
        try:
            chamar_api('sendMessage', {
                'chat_id': chat_id,
                'text': texto,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
            })
            resultados.append((chat_id, None))
        except TelegramErro as e:
            logger.warning('Telegram: falha ao enviar para o chat %s: %s', chat_id, e)
            resultados.append((chat_id, str(e)))
    return resultados


def enviar_em_segundo_plano(texto, chave=None, intervalo=0):
    """Dispara o envio numa thread, sem atrasar a resposta do site.

    Com chave + intervalo, ignora repetições da mesma chave dentro do intervalo (anti-spam).
    """
    if not configurado():
        return False
    if chave and intervalo:
        agora = time.monotonic()
        with _trava:
            ultimo = _ultimos_envios.get(chave)
            if ultimo is not None and agora - ultimo < intervalo:
                return False
            _ultimos_envios[chave] = agora
    threading.Thread(target=enviar_mensagem, args=(texto,), daemon=True).start()
    return True


# ---------------------------------------------------------------- mensagens

def _e(valor):
    return html.escape(str(valor), quote=False)


def _agora():
    return timezone.localtime().strftime('%d/%m/%Y %H:%M:%S')


def _quem(usuario):
    if usuario is None:
        return 'Desconhecido'
    return f'{usuario.nome} ({usuario.email})'


def alerta_acesso_negado(metodo, detalhe=None, usuario=None, confianca=None, negados_recentes=0):
    linhas = [
        '🚫 <b>Acesso negado</b>',
        f'Usuário: {_e(_quem(usuario))}',
        f'Método: {METODOS.get(metodo, _e(metodo))}',
    ]
    if detalhe:
        linhas.append(f'Motivo: {_e(detalhe)}')
    if confianca is not None:
        linhas.append(f'Confiança do sensor: {_e(confianca)}')
    linhas.append(f'Quando: {_agora()}')
    if negados_recentes >= NEGADOS_LIMITE_INVASAO:
        linhas += [
            '',
            f'⚠️ <b>{negados_recentes} tentativas negadas nos últimos {NEGADOS_JANELA_MIN} min.</b> '
            'Possível tentativa de invasão.',
        ]
    return enviar_em_segundo_plano('\n'.join(linhas))


def aviso_acesso_liberado(usuario, metodo, confianca=None):
    if not settings.TELEGRAM_NOTIFICAR_LIBERADOS:
        return False
    linhas = [
        '✅ <b>Acesso liberado</b>',
        f'Usuário: {_e(_quem(usuario))}',
        f'Método: {METODOS.get(metodo, _e(metodo))}',
    ]
    if confianca is not None:
        linhas.append(f'Confiança do sensor: {_e(confianca)}')
    linhas.append(f'Quando: {_agora()}')
    return enviar_em_segundo_plano('\n'.join(linhas))


def aviso_digital_cadastrada(usuario):
    return enviar_em_segundo_plano('\n'.join([
        '🆕 <b>Nova digital cadastrada</b>',
        f'Usuário: {_e(_quem(usuario))}',
        f'Posição no sensor: {_e(usuario.id)}',
        f'Quando: {_agora()}',
    ]))


def alerta_sensor_indisponivel(motivo):
    return enviar_em_segundo_plano('\n'.join([
        '⚠️ <b>Sensor biométrico indisponível</b>',
        f'Motivo: {_e(motivo)}',
        f'Quando: {_agora()}',
        'O login por e-mail e senha continua funcionando.',
    ]), chave='sensor', intervalo=INTERVALO_SENSOR_S)