# IOT — controle de acesso por digital (Supabase + HiveMQ Cloud + ESP32 + Telegram)

## Como funciona

```
Angular (login + dashboard) ──HTTP──► Django (sisiot) ──Postgres/SSL──► Supabase
                                          │
                                          │ MQTT/TLS (8883)
                                          ▼
                                    HiveMQ Cloud ◄──MQTT/TLS──► ESP32 + sensor biométrico

                              Django ──HTTPS──► Telegram (alertas aos administradores)
```

- **ESP32** (`esp32/iot_sensor`): só lê o sensor. Recebe um comando por MQTT, lê o dedo e devolve o resultado.
- **Django** (`sisiot`): cria usuários, manda o comando para o ESP32 pelo HiveMQ, grava cada tentativa
  de login na tabela `acessos` do Supabase e entrega os dados do dashboard (`/api/acessos/`).
- **Supabase**: guarda só duas tabelas, `usuarios` e `acessos`. A digital em si fica dentro do sensor;
  no banco vai apenas a posição (`digital.slot`), que é o próprio id do usuário.
- **Angular** (`angulariot`): telas de login, cadastro e dashboard.
- **Telegram**: o Django avisa os administradores em tempo real (acesso negado, possível invasão,
  digital cadastrada, sensor fora do ar).

Rotas do backend (`/api/...`): `login/`, `criarUsuario/`, `enroll/` (cadastro com digital),
`verify/` (login com digital) e `acessos/` (dados do dashboard).

---

## 1. Supabase

1. Crie um projeto (região **South America (São Paulo)** deixa mais rápido).
2. **SQL Editor → New query**, cole o `supabase_schema.sql` e clique em **Run**.
   Cria `usuarios` e `acessos` e liga o RLS (fecha a API REST automática; o Django continua com acesso total).
   Se você já tinha rodado a versão anterior, o mesmo script apaga as tabelas de materiais e a coluna do Discord.
3. Clique em **Connect** → Method **Session pooler** → **View parameters** e anote host, porta, banco,
   usuário e senha.

> Use o **Session pooler**, não a "Direct connection": a direta é IPv6 no plano grátis e costuma falhar
> no Windows/rede de casa. O usuário do pooler é `postgres.<id-do-projeto>`, não só `postgres`.

## 2. HiveMQ Cloud

1. No cluster, em **Access Management**, crie duas credenciais com **Publish and Subscribe**:
   - `esp32_finger` / `osaka123` (a que está no código do ESP32 — troque se quiser)
   - `backend_iot` / uma senha sua (para o Django)
2. A URL do cluster já está no código e no `.env.example`:
   `b3cb723f3ee74f7699ad4b47382d9448.s1.eu.hivemq.cloud`, porta **8883** (TLS).

## 3. Backend (Django)

```bash
cd sisiot
pip install -r requirements.txt
copy .env.example .env        # no Linux/Mac: cp .env.example .env
# edite o .env com os dados do Supabase e do HiveMQ
python manage.py runserver
```

Teste: `http://127.0.0.1:8000/api/acessos/` deve devolver um JSON com tudo zerado.
Não precisa rodar `migrate` (as tabelas vêm do SQL); o aviso de "unapplied migrations" pode ser ignorado.

## 4. Frontend (Angular)

```bash
cd angulariot
npm install
npm start          # abre em http://localhost:4200
```

## 5. ESP32

1. Arduino IDE → Gerenciador de Bibliotecas: **Adafruit Fingerprint Sensor Library**, **PubSubClient** e **ArduinoJson**.
2. Abra `esp32/iot_sensor/iot_sensor.ino`, confira Wi-Fi e credencial MQTT no topo e grave.
3. No Monitor Serial (115200): `Sensor ok...` → `Wi-Fi ok...` → `Conectando ao HiveMQ Cloud... ok`.

### Limpe o sensor uma vez

O sensor pode ter digitais de testes antigos, e os ids do Supabase começam do 1. Antes do primeiro cadastro:
HiveMQ Cloud → cluster → **Web Client** → conecte com a credencial do backend → publique em
`iot/sensor/comando`:

```json
{"req":"manual","acao":"limpar"}
```

## 6. Telegram (alertas)

1. No Telegram, abra o **@BotFather**, mande `/newbot`, escolha um nome e um usuário terminado em `bot`.
   Ele devolve um **token** (`123456789:AA...`). Cole em `TELEGRAM_TOKEN` no `sisiot/.env`.
2. Abra o seu bot no Telegram e mande `/start`. Para avisar um grupo de administradores, adicione o bot
   no grupo e mande `/start@nome_do_seu_bot` lá.
3. Rode:
   ```bash
   cd sisiot
   python manage.py telegram_setup
   ```
   Ele confere o token e lista os chats que falaram com o bot, com o **id** de cada um.
4. Copie o id para `TELEGRAM_CHAT_ID` no `.env` (vários: separe por vírgula; id de grupo começa com `-`)
   e rode `python manage.py telegram_setup` de novo: chega uma mensagem de teste no Telegram.
5. Reinicie o `runserver` (o `.env` só é lido quando ele inicia).

| Alerta | Quando |
|---|---|
| 🚫 Acesso negado | Digital não reconhecida, senha errada, e-mail não cadastrado ou digital sem usuário no banco |
| ⚠️ Possível invasão | Junto do acesso negado, quando há 3 ou mais negações nos últimos 10 minutos |
| 🆕 Nova digital cadastrada | Cadastro com digital concluído |
| ⚠️ Sensor indisponível | ESP32 offline ou sem resposta (no máximo 1 aviso a cada 5 minutos) |
| ✅ Acesso liberado | Só com `TELEGRAM_NOTIFICAR_LIBERADOS=1` no `.env` |

Os envios rodam em segundo plano: se o Telegram cair ou o token estiver errado, o login continua
funcionando e o erro aparece só no terminal do Django. Sem `TELEGRAM_TOKEN`, nada é enviado.

## 7. Fluxo de uso

1. **Cadastro** (`/registro`, link "Cadastrar digital" no login): nome, e-mail e senha → **Cadastrar com digital**
   → coloque o dedo, tire e coloque o mesmo dedo de novo. Se a leitura falhar, o usuário é desfeito para
   você tentar de novo.
2. **Login** (`/login`) → **Entrar com digital** → coloque o dedo. Toda tentativa, liberada ou negada,
   vira uma linha em `acessos`. Login por e-mail e senha também é registrado (método "senha").
3. **Dashboard** (`/dashboard`): acessos de hoje, gráfico por dia (liberados x negados), quem mais entrou
   e os últimos acessos. Atualiza a cada 10 s. Sem login, o site manda de volta para `/login`.

## Tópicos MQTT

| Tópico | Quem publica | Conteúdo |
|---|---|---|
| `iot/sensor/comando` | Django | `{"req":"a1b2","acao":"verificar"}` / `{"req":"a1b2","acao":"cadastrar","id":5}` / `apagar` / `limpar` |
| `iot/sensor/resposta` | ESP32 | `{"req":"a1b2","acao":"verificar","status":"ok","match":true,"id":5,"confianca":87}` |
| `iot/sensor/status` (retido) | ESP32 | `{"online":true,"capacidade":127,"cadastradas":3}` ou `{"online":false}` quando cai |

O `req` é um código aleatório que o Django gera para casar cada resposta com o pedido certo.

## Problemas comuns

| Sintoma | Causa provável |
|---|---|
| ESP32: `falhou (rc=-2)` | Sem conexão TLS: URL/porta errada ou Wi-Fi sem internet |
| ESP32: `falhou (rc=4)` ou `rc=5` | Usuário/senha da credencial do HiveMQ errados |
| Django: `HiveMQ recusou a conexão` | `MQTT_USUARIO`/`MQTT_SENHA` do `.env` errados |
| Site: "O ESP32 do sensor está offline" | O ESP32 caiu (o broker avisou pelo tópico de status) |
| Site: "O sensor não respondeu" | ESP32 desligado, ou nunca conectou no HiveMQ |
| Site: "Tempo esgotado" | Ninguém colocou o dedo em 20 s (login) / 45 s (cadastro) |
| Site: "Essa digital já está cadastrada (id X)" | O dedo já está no sensor; use outro ou rode o `limpar` |
| Django: `no tenant identifier` | `DB_USER` precisa ser `postgres.<id-do-projeto>` no pooler |
| Django: `Faltam as credenciais do banco` | O arquivo `sisiot/.env` não existe |
| `telegram_setup`: `Unauthorized` | Token errado ou incompleto; copie de novo do @BotFather |
| `telegram_setup`: "Ninguém falou com o bot" | Mande `/start` para o bot e rode o comando em até 24 h |
| Teste falha com `chat not found` | Id errado, ou a pessoa nunca mandou `/start` para o bot |
| Alertas não chegam, mas o teste chegou | Reinicie o `runserver` depois de editar o `.env` |

## Segurança

- O `.env` (senhas do Supabase e do HiveMQ e o token do Telegram) não vai para o Git.
  Quem tiver o token controla o bot: se ele vazar, gere outro no @BotFather com `/revoke`.
- As senhas dos usuários são salvas com hash e nunca voltam nas respostas da API.
- Se o repositório antigo (MetaBEE) foi publicado com o token do bot do Discord, gere um token novo
  ou apague o bot no Discord Developer Portal — o bot do Discord saiu deste projeto.
