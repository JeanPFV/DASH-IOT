/*
  IOT - Controle de acesso por digital (ESP32 + AS608/R307) via HiveMQ Cloud

  O ESP32 agora só cuida do sensor:
    - recebe um comando no tópico  iot/sensor/comando
    - lê a digital
    - devolve o resultado no tópico iot/sensor/resposta

  Usuários, senhas, log de acessos e dashboard ficam no backend (Django + Supabase).
  Não existe mais servidor HTTP no ESP32, então o backend pode estar em qualquer
  lugar (não precisa estar na mesma rede Wi-Fi).

  Comandos aceitos (JSON):
    {"req":"abc123","acao":"verificar"}
    {"req":"abc123","acao":"cadastrar","id":5}   -> grava a digital na posição 5 (= id do usuário no banco)
    {"req":"abc123","acao":"apagar","id":5}
    {"req":"abc123","acao":"limpar"}             -> apaga TODAS as digitais do sensor

  Respostas (JSON), sempre com o mesmo "req" do comando:
    {"req":"abc123","acao":"verificar","status":"ok","match":true,"id":5,"confianca":87}
    {"req":"abc123","acao":"verificar","status":"ok","match":false}
    {"req":"abc123","acao":"cadastrar","status":"ok","id":5}
    {"req":"abc123","acao":"cadastrar","status":"erro","msg":"..."}

  Bibliotecas (Gerenciador de Bibliotecas da Arduino IDE):
    - Adafruit Fingerprint Sensor Library
    - PubSubClient (Nick O'Leary)
    - ArduinoJson (Benoit Blanchon)
*/

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Adafruit_Fingerprint.h>

// ======================= CONFIGURAÇÃO =======================
const char* WIFI_SSID  = "LightHouse_2.4Ghz";
const char* WIFI_SENHA = "99185686";

// Dados do cluster HiveMQ Cloud (aba "Overview" do cluster)
const char*    MQTT_HOST    = "b3cb723f3ee74f7699ad4b47382d9448.s1.eu.hivemq.cloud";
const uint16_t MQTT_PORTA   = 8883;  // TLS (o HiveMQ Cloud só aceita conexão segura)
// Credencial criada em HiveMQ Cloud > Access Management
const char*    MQTT_USUARIO = "esp32_finger";
const char*    MQTT_SENHA   = "osaka123";

const char* TOPICO_COMANDO  = "iot/sensor/comando";
const char* TOPICO_RESPOSTA = "iot/sensor/resposta";
const char* TOPICO_STATUS   = "iot/sensor/status";   // retido: online/offline + contagem

#define RXD2 16
#define TXD2 17

const uint32_t PRAZO_VERIFICAR_MS = 20000;  // tempo para a pessoa colocar o dedo
const uint32_t PRAZO_CADASTRO_MS  = 45000;  // cadastro pede o dedo duas vezes
// ============================================================

// Certificados raiz do Let's Encrypt (usados pelo HiveMQ Cloud).
// ISRG Root X1 (RSA, válido até 2035) + ISRG Root X2 (ECDSA, válido até 2040).
static const char CA_RAIZ[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIICGzCCAaGgAwIBAgIQQdKd0XLq7qeAwSxs6S+HUjAKBggqhkjOPQQDAzBPMQsw
CQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJuZXQgU2VjdXJpdHkgUmVzZWFyY2gg
R3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBYMjAeFw0yMDA5MDQwMDAwMDBaFw00
MDA5MTcxNjAwMDBaME8xCzAJBgNVBAYTAlVTMSkwJwYDVQQKEyBJbnRlcm5ldCBT
ZWN1cml0eSBSZXNlYXJjaCBHcm91cDEVMBMGA1UEAxMMSVNSRyBSb290IFgyMHYw
EAYHKoZIzj0CAQYFK4EEACIDYgAEzZvVn4CDCuwJSvMWSj5cz3es3mcFDR0HttwW
+1qLFNvicWDEukWVEYmO6gbf9yoWHKS5xcUy4APgHoIYOIvXRdgKam7mAHf7AlF9
ItgKbppbd9/w+kHsOdx1ymgHDB/qo0IwQDAOBgNVHQ8BAf8EBAMCAQYwDwYDVR0T
AQH/BAUwAwEB/zAdBgNVHQ4EFgQUfEKWrt5LSDv6kviejM9ti6lyN5UwCgYIKoZI
zj0EAwMDaAAwZQIwe3lORlCEwkSHRhtFcP9Ymd70/aTSVaYgLXTWNLxBo1BfASdW
tL4ndQavEi51mI38AjEAi/V3bNTIZargCyzuFJ0nN6T5U6VR5CmD1/iQMVtCnwr1
/q4AaOeMSQ+2b1tbFfLn
-----END CERTIFICATE-----
)EOF";

Adafruit_Fingerprint finger(&Serial2);
WiFiClientSecure clienteTls;
PubSubClient mqtt(clienteTls);

enum Estado { OCIOSO, VERIFICANDO, CADASTRO_DEDO1, CADASTRO_RETIRAR, CADASTRO_DEDO2 };
Estado   estado = OCIOSO;
String   reqAtual;
String   acaoAtual;
uint16_t idAtual = 0;
uint32_t inicioAtual = 0;
uint32_t prazoAtual = 0;
uint32_t ultimaLeitura = 0;

// ---------------------- MQTT: envio ----------------------

void publicarJson(const char* topico, DynamicJsonDocument& doc, bool retido = false) {
  char buffer[256];
  serializeJson(doc, buffer, sizeof(buffer));
  if (!mqtt.publish(topico, buffer, retido)) {
    Serial.println("Aviso: não foi possível publicar (MQTT desconectado?)");
  }
  Serial.printf("-> [%s] %s\n", topico, buffer);
}

void responderErro(const String& req, const String& acao, const char* msg) {
  DynamicJsonDocument doc(256);
  doc["req"] = req;
  doc["acao"] = acao;
  doc["status"] = "erro";
  doc["msg"] = msg;
  publicarJson(TOPICO_RESPOSTA, doc);
}

void responderOk(const String& req, const String& acao, int id = -1) {
  DynamicJsonDocument doc(256);
  doc["req"] = req;
  doc["acao"] = acao;
  doc["status"] = "ok";
  if (id >= 0) doc["id"] = id;
  publicarJson(TOPICO_RESPOSTA, doc);
}

void publicarStatus() {
  finger.getTemplateCount();
  DynamicJsonDocument doc(256);
  doc["online"] = true;
  doc["capacidade"] = finger.capacity;
  doc["cadastradas"] = finger.templateCount;
  doc["ip"] = WiFi.localIP().toString();
  publicarJson(TOPICO_STATUS, doc, true);
}

void finalizar() {
  estado = OCIOSO;
  reqAtual = "";
  acaoAtual = "";
  idAtual = 0;
}

void iniciar(Estado novoEstado, const String& req, const String& acao, uint16_t id, uint32_t prazo) {
  estado = novoEstado;
  reqAtual = req;
  acaoAtual = acao;
  idAtual = id;
  inicioAtual = millis();
  prazoAtual = prazo;
}

// ---------------------- MQTT: comandos ----------------------

void aoReceberComando(char* topico, byte* payload, unsigned int tamanho) {
  DynamicJsonDocument doc(256);
  if (deserializeJson(doc, payload, tamanho)) {
    Serial.println("Comando ignorado: JSON inválido");
    return;
  }
  String req  = doc["req"]  | "";
  String acao = doc["acao"] | "";
  uint16_t id = doc["id"]   | 0;
  Serial.printf("<- comando '%s' (req=%s, id=%u)\n", acao.c_str(), req.c_str(), id);

  if (estado != OCIOSO) {
    responderErro(req, acao, "Sensor ocupado com outra leitura. Tente de novo em alguns segundos.");
    return;
  }

  if (acao == "verificar") {
    Serial.println("Coloque o dedo no sensor...");
    iniciar(VERIFICANDO, req, acao, 0, PRAZO_VERIFICAR_MS);

  } else if (acao == "cadastrar") {
    if (id < 1 || (finger.capacity > 0 && id > finger.capacity)) {
      char msg[80];
      snprintf(msg, sizeof(msg), "Id %u fora da faixa do sensor (1 a %u)", id, finger.capacity);
      responderErro(req, acao, msg);
      return;
    }
    Serial.printf("Cadastro no id %u: coloque o dedo no sensor...\n", id);
    iniciar(CADASTRO_DEDO1, req, acao, id, PRAZO_CADASTRO_MS);

  } else if (acao == "apagar") {
    if (finger.deleteModel(id) == FINGERPRINT_OK) responderOk(req, acao, id);
    else responderErro(req, acao, "Não foi possível apagar essa posição");
    publicarStatus();

  } else if (acao == "limpar") {
    if (finger.emptyDatabase() == FINGERPRINT_OK) responderOk(req, acao);
    else responderErro(req, acao, "Não foi possível limpar o sensor");
    publicarStatus();

  } else {
    responderErro(req, acao, "Ação desconhecida");
  }
}

// ---------------------- Sensor (máquina de estados) ----------------------
// Roda a cada ~100 ms dentro do loop(), sem travar: assim o MQTT continua vivo
// enquanto a pessoa coloca o dedo.

void processarSensor() {
  if (estado == OCIOSO) return;
  if (millis() - ultimaLeitura < 100) return;
  ultimaLeitura = millis();

  if (millis() - inicioAtual > prazoAtual) {
    Serial.println("Tempo esgotado.");
    responderErro(reqAtual, acaoAtual, "Tempo esgotado: nenhum dedo foi lido no sensor");
    finalizar();
    return;
  }

  uint8_t p = finger.getImage();

  switch (estado) {
    case VERIFICANDO: {
      if (p != FINGERPRINT_OK) return;                         // sem dedo ainda
      if (finger.image2Tz(1) != FINGERPRINT_OK) return;        // imagem ruim: lê de novo
      p = finger.fingerSearch();
      DynamicJsonDocument doc(256);
      doc["req"] = reqAtual;
      doc["acao"] = acaoAtual;
      if (p == FINGERPRINT_OK) {
        doc["status"] = "ok";
        doc["match"] = true;
        doc["id"] = finger.fingerID;
        doc["confianca"] = finger.confidence;
      } else if (p == FINGERPRINT_NOTFOUND) {
        doc["status"] = "ok";
        doc["match"] = false;
      } else {
        doc["status"] = "erro";
        doc["msg"] = "Falha de comunicação com o sensor na busca";
      }
      publicarJson(TOPICO_RESPOSTA, doc);
      finalizar();
      return;
    }

    case CADASTRO_DEDO1: {
      if (p != FINGERPRINT_OK) return;
      if (finger.image2Tz(1) != FINGERPRINT_OK) return;
      // Evita a mesma digital em dois usuários diferentes
      if (finger.fingerSearch() == FINGERPRINT_OK) {
        char msg[80];
        snprintf(msg, sizeof(msg), "Essa digital já está cadastrada (id %u)", finger.fingerID);
        responderErro(reqAtual, acaoAtual, msg);
        finalizar();
        return;
      }
      Serial.println("1a leitura ok. Retire o dedo...");
      estado = CADASTRO_RETIRAR;
      return;
    }

    case CADASTRO_RETIRAR: {
      if (p == FINGERPRINT_NOFINGER) {
        Serial.println("Coloque o MESMO dedo de novo...");
        estado = CADASTRO_DEDO2;
      }
      return;
    }

    case CADASTRO_DEDO2: {
      if (p != FINGERPRINT_OK) return;
      if (finger.image2Tz(2) != FINGERPRINT_OK) return;
      p = finger.createModel();
      if (p == FINGERPRINT_ENROLLMISMATCH) {
        responderErro(reqAtual, acaoAtual, "As duas leituras não bateram. Tente de novo com o mesmo dedo.");
        finalizar();
        return;
      }
      if (p != FINGERPRINT_OK) {
        responderErro(reqAtual, acaoAtual, "Falha ao gerar o modelo da digital");
        finalizar();
        return;
      }
      if (finger.storeModel(idAtual) != FINGERPRINT_OK) {
        responderErro(reqAtual, acaoAtual, "Falha ao gravar a digital no sensor");
        finalizar();
        return;
      }
      Serial.printf("Digital gravada no id %u\n", idAtual);
      responderOk(reqAtual, acaoAtual, idAtual);
      finalizar();
      publicarStatus();
      return;
    }

    default:
      return;
  }
}

// ---------------------- Conexões ----------------------

void garantirMqtt() {
  static uint32_t ultimaTentativa = 0;
  if (WiFi.status() != WL_CONNECTED || mqtt.connected()) return;
  if (ultimaTentativa != 0 && millis() - ultimaTentativa < 5000) return;
  ultimaTentativa = millis();

  String clientId = "iot-esp32-";
  clientId += String((uint32_t)ESP.getEfuseMac(), HEX);
  Serial.print("Conectando ao HiveMQ Cloud... ");
  // "Last will": se o ESP cair, o broker publica sozinho que ele ficou offline
  if (mqtt.connect(clientId.c_str(), MQTT_USUARIO, MQTT_SENHA,
                   TOPICO_STATUS, 1, true, "{\"online\":false}")) {
    Serial.println("ok");
    mqtt.subscribe(TOPICO_COMANDO, 1);
    publicarStatus();
  } else {
    // -2 = sem conexão TCP/TLS (host, porta ou certificado); 4/5 = usuário/senha errados
    Serial.printf("falhou (rc=%d). Nova tentativa em 5 s\n", mqtt.state());
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\nIOT - sensor biométrico (MQTT)");

  Serial2.begin(57600, SERIAL_8N1, RXD2, TXD2);
  finger.begin(57600);
  if (!finger.verifyPassword()) {
    Serial.println("Sensor biométrico não encontrado. Confira RX/TX e alimentação.");
    while (true) delay(1000);
  }
  finger.getParameters();
  finger.getTemplateCount();
  Serial.printf("Sensor ok: capacidade %u, digitais gravadas %u\n", finger.capacity, finger.templateCount);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_SENHA);
  Serial.print("Conectando ao Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nWi-Fi ok, IP %s\n", WiFi.localIP().toString().c_str());

  clienteTls.setCACert(CA_RAIZ);
  mqtt.setServer(MQTT_HOST, MQTT_PORTA);
  mqtt.setCallback(aoReceberComando);
  mqtt.setBufferSize(512);
  mqtt.setKeepAlive(30);
}

void loop() {
  garantirMqtt();
  mqtt.loop();
  processarSensor();
  delay(5);
}
