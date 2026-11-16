"""
Testa a conexão com o Supabase usando os dados do sisiot/.env.

    cd sisiot
    python testar_banco.py

Tenta o host do .env e as variações do pooler da mesma região (aws-0, aws-1, aws-2),
além da conexão direta. Mostra qual funcionou para você copiar para o .env.
"""
import os
import re
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / '.env')

host = os.getenv('DB_HOST', '')
porta = os.getenv('DB_PORT', '5432')
banco = os.getenv('DB_NAME', 'postgres')
usuario = os.getenv('DB_USER', '')
senha = os.getenv('DB_PASSWORD', '')

print('Valores lidos do .env (repr mostra espaços ou aspas escondidos):')
print(f'  DB_HOST = {host!r}')
print(f'  DB_PORT = {porta!r}')
print(f'  DB_NAME = {banco!r}')
print(f'  DB_USER = {usuario!r}')
print(f'  DB_PASSWORD = {"(vazia)" if not senha else f"{len(senha)} caracteres"}')
print()

ref = usuario.split('.', 1)[1] if '.' in usuario else ''
achou = re.match(r'aws-\d+-(.+)\.pooler\.supabase\.com$', host)
regiao = achou.group(1) if achou else ''

tentativas = [(host, porta, usuario)]
if regiao:
    for n in (0, 1, 2):
        outro = f'aws-{n}-{regiao}.pooler.supabase.com'
        if outro != host:
            tentativas.append((outro, '5432', usuario))
if ref:
    tentativas.append((f'db.{ref}.supabase.co', '5432', 'postgres'))   # direta (só funciona com IPv6)

for h, p, u in tentativas:
    try:
        conexao = psycopg2.connect(host=h, port=p, dbname=banco, user=u, password=senha,
                                   sslmode='require', connect_timeout=8)
        conexao.close()
        print(f'OK      {h}:{p}  usuário {u}   <-- use estes valores no .env')
    except psycopg2.OperationalError as e:
        motivo = str(e).strip().splitlines()[-1] if str(e).strip() else e.__class__.__name__
        print(f'falhou  {h}:{p}  usuário {u}   ({motivo})')
