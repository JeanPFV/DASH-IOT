"""
python manage.py telegram_setup

1. Confere se o TELEGRAM_TOKEN do .env é válido.
2. Lista os chats que mandaram mensagem para o bot (é daí que sai o TELEGRAM_CHAT_ID).
3. Se o TELEGRAM_CHAT_ID já estiver no .env, manda uma mensagem de teste.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from app_sisiot import telegram_alertas as telegram


class Command(BaseCommand):
    help = 'Confere o bot do Telegram, mostra o chat id e manda uma mensagem de teste.'

    def handle(self, *args, **options):
        if not settings.TELEGRAM_TOKEN:
            raise CommandError(
                'Falta o TELEGRAM_TOKEN no sisiot/.env. No Telegram, fale com o @BotFather, '
                'mande /newbot e cole o token que ele devolver.'
            )

        try:
            bot = telegram.chamar_api('getMe')
        except telegram.TelegramSemConexao as e:
            raise CommandError(
                f'Este computador não conseguiu falar com o Telegram ({e}).\n'
                'Redes de escola ou empresa costumam bloquear o Telegram: teste em outra rede '
                '(por exemplo, a internet do celular). Se aparecer CERTIFICATE_VERIFY_FAILED, '
                'a rede está interceptando o HTTPS.'
            )
        except telegram.TelegramErro as e:
            raise CommandError(f'O Telegram recusou o token ({e}). Confira o TELEGRAM_TOKEN.')
        self.stdout.write(self.style.SUCCESS(f'Bot encontrado: @{bot.get("username")} ({bot.get("first_name")})'))

        # Chats que falaram com o bot nas últimas 24 h
        try:
            atualizacoes = telegram.chamar_api('getUpdates', {'limit': 100, 'timeout': 0})
        except telegram.TelegramErro as e:
            atualizacoes = []
            self.stdout.write(self.style.WARNING(f'Não deu para ler as mensagens recentes do bot: {e}'))

        chats = {}
        for atualizacao in atualizacoes or []:
            for tipo in ('message', 'edited_message', 'channel_post', 'my_chat_member'):
                chat = (atualizacao.get(tipo) or {}).get('chat')
                if chat:
                    chats[chat['id']] = chat

        if chats:
            self.stdout.write('\nChats que falaram com o bot (copie o id para TELEGRAM_CHAT_ID):')
            for chat in chats.values():
                nome = chat.get('title') or ' '.join(
                    p for p in (chat.get('first_name'), chat.get('last_name')) if p
                ) or chat.get('username', '')
                self.stdout.write(f'  id {chat["id"]:<16} {chat.get("type", ""):<11} {nome}')
        else:
            self.stdout.write(self.style.WARNING(
                f'\nNinguém falou com o bot nas últimas 24 h. Abra @{bot.get("username")} no Telegram, '
                'mande /start e rode este comando de novo. Em grupo: adicione o bot e mande '
                f'/start@{bot.get("username")}.'
            ))

        if not settings.TELEGRAM_CHAT_IDS:
            self.stdout.write(self.style.WARNING(
                '\nNenhuma mensagem de teste foi enviada: o TELEGRAM_CHAT_ID está vazio no .env. '
                'Copie um dos ids acima para ele e rode este comando de novo.'
            ))
            return

        self.stdout.write(f'\nEnviando teste para: {", ".join(settings.TELEGRAM_CHAT_IDS)}')

        resultados = telegram.enviar_mensagem(
            '✅ <b>IOT · Controle de acesso</b>\n'
            'Integração com o Telegram funcionando. Os alertas de acesso vão chegar aqui.'
        )
        for chat_id, erro in resultados:
            if erro:
                dica = ''
                if 'chat not found' in erro:
                    dica = ' -> id errado, ou essa pessoa/grupo nunca mandou /start para o bot'
                elif 'upgraded to a supergroup' in erro:
                    dica = ' -> o grupo mudou de id; rode o comando de novo e use o id novo (começa com -100)'
                elif 'bot was blocked' in erro:
                    dica = ' -> desbloqueie o bot no Telegram e mande /start'
                self.stdout.write(self.style.ERROR(f'Chat {chat_id}: falhou ({erro}){dica}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Chat {chat_id}: mensagem de teste enviada'))
