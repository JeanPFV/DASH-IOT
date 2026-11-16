"""
Ponte entre o Django e o ESP32 via HiveMQ Cloud.

Em vez de chamar o ESP32 por HTTP na rede local (ESP32_IP), o backend publica um
comando no broker e espera a resposta do ESP32 com o mesmo "req". Assim o backend
e o ESP32 podem estar em redes diferentes (ex.: backend na nuvem).

    resposta = enviar_comando('verificar', timeout=25)
    resposta = enviar_comando('cadastrar', timeout=50, id=usuario.id)
"""
import json
import logging
import ssl
import threading
import uuid

import paho.mqtt.client as mqtt
from django.conf import settings

logger = logging.getLogger(__name__)


class SensorIndisponivel(Exception):
    """Broker fora do ar, credencial errada, ESP32 offline ou sem resposta."""


def enviar_comando(acao, timeout, **dados):
    req = uuid.uuid4().hex[:12]
    pronto = threading.Event()      # conectado e inscrito (ou falhou)
    terminou = threading.Event()    # chegou a resposta (ou o ESP32 está offline)
    estado = {'resposta': None, 'erro': None}

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            estado['erro'] = f'HiveMQ recusou a conexão ({reason_code}). Confira usuário/senha no .env.'
            pronto.set()
            return
        client.subscribe([
            (settings.MQTT_TOPICO_RESPOSTA, 1),
            (settings.MQTT_TOPICO_STATUS, 1),
        ])

    def on_subscribe(client, userdata, mid, reason_code_list, properties):
        if any(rc.is_failure for rc in reason_code_list):
            estado['erro'] = 'HiveMQ não permitiu assinar os tópicos (confira as permissões da credencial).'
        pronto.set()

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
        except (UnicodeDecodeError, ValueError):
            return
        if msg.topic == settings.MQTT_TOPICO_STATUS:
            # Mensagem retida: se o ESP32 caiu, o broker guardou {"online": false}
            if payload.get('online') is False:
                estado['erro'] = 'O ESP32 do sensor está offline (sem energia ou sem internet).'
                terminou.set()
            return
        if payload.get('req') == req:
            estado['resposta'] = payload
            terminou.set()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f'iot-backend-{req}',
    )
    client.username_pw_set(settings.MQTT_USUARIO, settings.MQTT_SENHA)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)  # usa os certificados do sistema
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    try:
        client.connect(settings.MQTT_HOST, settings.MQTT_PORTA, keepalive=30)
    except OSError as e:
        raise SensorIndisponivel(f'Não foi possível conectar ao HiveMQ ({e}).') from e

    client.loop_start()
    try:
        if not pronto.wait(10):
            raise SensorIndisponivel('O HiveMQ não respondeu a tempo.')
        if estado['erro']:
            raise SensorIndisponivel(estado['erro'])

        comando = {'req': req, 'acao': acao, **dados}
        client.publish(settings.MQTT_TOPICO_COMANDO, json.dumps(comando), qos=1)
        logger.info('Comando enviado ao sensor: %s', comando)

        if not terminou.wait(timeout):
            raise SensorIndisponivel('O sensor não respondeu. O ESP32 está ligado e conectado ao HiveMQ?')
        if estado['erro']:
            raise SensorIndisponivel(estado['erro'])

        logger.info('Resposta do sensor: %s', estado['resposta'])
        return estado['resposta']
    finally:
        client.disconnect()
        client.loop_stop()
