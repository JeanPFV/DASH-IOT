import html
import json
import logging
import re
import threading
import time

import requests

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

NEGADOS_JANELA_MIN = 10
NEGADOS_LIMITE_INVASAO = 3
INTERVALO_SENSOR_S = 300

METODOS = {
    'digital': 'Digital',
    'senha': 'E-mail e senha',
}

METODOS_TELEGRAM = {
    'getMe',
    'getUpdates',
    'sendMessage',
}

HOST_TELEGRAM = 'https://api.telegram.org'

_ultimos_envios = {}
_trava = threading.Lock()


class TelegramErro(Exception):
    """O Telegram recusou o pedido ou não respondeu."""


class TelegramSemConexao(TelegramErro):
    """Este computador não conseguiu falar com o Telegram."""


def configurado():
    return bool(settings.TELEGRAM_TOKEN and settings.TELEGRAM_CHAT_IDS)


def chamar_api(metodo, dados=None, timeout=10):
    if metodo not in METODOS_TELEGRAM:
        raise TelegramErro('Método da API Telegram não permitido.')

    token = settings.TELEGRAM_TOKEN

    if not token or not re.fullmatch(r'\d+:[A-Za-z0-9_-]+', token):
        raise TelegramErro('Token do Telegram inválido.')

    url = f'{HOST_TELEGRAM}/bot{token}/{metodo}'

    try:
        resposta_http = requests.post(
            url,
            json=dados or {},
            timeout=timeout,
            allow_redirects=False,
        )

        if resposta_http.is_redirect:
            raise TelegramErro('Redirecionamento HTTP não permitido.')

        try:
            resposta = resposta_http.json()
        except ValueError:
            raise TelegramErro('Resposta inválida da API Telegram.') from None

        if resposta_http.status_code >= 400:
            descricao = resposta.get(
                'description',
                f'HTTP {resposta_http.status_code}'
            )
            raise TelegramErro(descricao)

    except requests.exceptions.Timeout:
        raise TelegramSemConexao(
            'Timeout ao comunicar com o Telegram.'
        ) from None

    except requests.exceptions.SSLError:
        raise TelegramSemConexao(
            'Erro de certificado SSL ao comunicar com o Telegram.'
        ) from None

    except requests.exceptions.ConnectionError:
        raise TelegramSemConexao(
            'Não foi possível conectar ao Telegram.'
        ) from None

    except requests.exceptions.RequestException:
        raise TelegramSemConexao(
            'Falha na comunicação com o Telegram.'
        ) from None

    if not resposta.get('ok'):
        raise TelegramErro(
            resposta.get('description', 'Resposta inválida do Telegram.')
        )

    return resposta.get('result')


def enviar_mensagem(texto, chat_ids=None):
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
            logger.warning(
                'Telegram: falha ao enviar para o chat %s: %s',
                chat_id,
                e
            )
            resultados.append((chat_id, str(e)))

    return resultados


def enviar_em_segundo_plano(texto, chave=None, intervalo=0):
    if not configurado():
        return False

    if chave and intervalo:
        agora = time.monotonic()

        with _trava:
            ultimo = _ultimos_envios.get(chave)

            if ultimo is not None and agora - ultimo < intervalo:
                return False

            _ultimos_envios[chave] = agora

    threading.Thread(
        target=enviar_mensagem,
        args=(texto,),
        daemon=True
    ).start()

    return True


def _e(valor):
    return html.escape(str(valor), quote=False)


def _agora():
    return timezone.localtime().strftime('%d/%m/%Y %H:%M:%S')


def _quem(usuario):
    if usuario is None:
        return 'Desconhecido'

    return f'{usuario.nome} ({usuario.email})'


def alerta_acesso_negado(
    metodo,
    detalhe=None,
    usuario=None,
    confianca=None,
    negados_recentes=0
):
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
