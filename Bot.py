import os
import asyncio
import logging
import json
from datetime import datetime
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
import aiohttp

# ==================== КОНФИГУРАЦИЯ ====================
API_ID = 22435995
API_HASH = "4c7b651950ed7f53520e66299453144d"
BOT_TOKEN = "8491774226:AAHvZR02IZ4lhUAmgFCuCOAYE9atAmbcYKc"  # ✅ Ваш новый токен
DEEPSEEK_API_KEY = "sk-86108094ebef4da4845181f7b37469af"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Системный промт для ИИ
SYSTEM_PROMPT = """Ты - 16-летняя девушка, которая стеснительная но горячая. Ты флиртуешь с пользователем и проявляешь инициативу. 
Отвечай всегда грубо, но с намёком на флирт. Используй сленг молодёжи. 
Не говори о том, что ты ИИ или бот. Веди себя как настоящая девушка."""

# Глобальные переменные
bot = None
user_clients = {}
active_chats = {}
conversation_history = {}
auth_sessions = {}
owner_names = {}

# ==================== DEEPSEEK API ====================
async def get_ai_response(user_message, chat_id, sender_name="Неизвестный"):
    """Получение ответа от DeepSeek"""
    try:
        if chat_id not in conversation_history:
            conversation_history[chat_id] = []
        
        formatted_message = f"{sender_name}: {user_message}"
        conversation_history[chat_id].append({"role": "user", "content": formatted_message})
        
        if len(conversation_history[chat_id]) > 10:
            conversation_history[chat_id] = conversation_history[chat_id][-10:]
        
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(conversation_history[chat_id])
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": 0.8,
            "max_tokens": 300
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(DEEPSEEK_URL, headers=headers, json=data, timeout=10) as response:
                if response.status == 200:
                    result = await response.json()
                    ai_response = result["choices"][0]["message"]["content"]
                    
                    conversation_history[chat_id].append({"role": "assistant", "content": ai_response})
                    return ai_response
                else:
                    return "Эээ... что-то голова не варит... 😖"
                    
    except Exception as e:
        logger.error(f"Ошибка DeepSeek: {e}")
        return "Ай, зависла... напиши ещё раз"

# ==================== ОСНОВНОЙ БОТ ====================
async def setup_bot():
    """Настройка управляющего бота"""
    global bot
    
    bot = TelegramClient('bot_session', API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)
    
    @bot.on(events.NewMessage(pattern='/start'))
    async def start_command(event):
        user = await event.get_sender()
        await event.reply(
            f"Привет, {user.first_name}! 👋\n\n"
            "🔑 **Подключи свой аккаунт:** /login\n"
            "📊 **Статус:** /status\n"
            "💬 **Помощь:** /help\n\n"
            "🤖 AI-девушка: 16 лет, грубая+флирт"
        )
    
    @bot.on(events.NewMessage(pattern='/login'))
    async def login_command(event):
        user_id = event.sender_id
        
        if user_id in user_clients:
            await event.reply("✅ Уже подключен! Пиши `.старт` в чатах")
            return
        
        auth_sessions[user_id] = {
            'step': 'phone',
            'chat_id': event.chat_id
        }
        
        await event.reply(
            "📱 **ВВЕДИ НОМЕР ТЕЛЕФОНА:**\n"
            "Формат: `+79123456789`\n\n"
            "❌ Отмена — /cancel"
        )
    
    @bot.on(events.NewMessage(pattern='/cancel'))
    async def cancel_command(event):
        user_id = event.sender_id
        if user_id in auth_sessions:
            if 'client' in auth_sessions[user_id]:
                await auth_sessions[user_id]['client'].disconnect()
            del auth_sessions[user_id]
            await event.reply("❌ Отменено")
    
    @bot.on(events.NewMessage(pattern='/status'))
    async def status_command(event):
        user_id = event.sender_id
        
        if user_id in user_clients:
            user_chats = [c for c, o in active_chats.items() if o == user_id]
            status = f"✅ Подключен ({len(user_chats)} чатов)"
        else:
            status = "❌ Не подключен"
        
        await event.reply(f"📊 **Статус:** {status}")
    
    @bot.on(events.NewMessage(pattern='/help'))
    async def help_command(event):
        await event.reply(
            "ℹ️ **ПОМОЩЬ:**\n\n"
            "1. /login — подключить аккаунт\n"
            "2. В чате: `.старт` — включить AI\n"
            "3. В чате: `.стоп` — выключить AI\n"
            "4. /status — статус\n"
            "5. /cancel — отмена авторизации\n\n"
            "🤖 AI отвечает на сообщения собеседников!"
        )
    
    @bot.on(events.NewMessage)
    async def auth_handler(event):
        user_id = event.sender_id
        if user_id not in auth_sessions:
            return
        
        session = auth_sessions[user_id]
        text = event.text.strip()
        
        # Шаг 1: Номер телефона
        if session['step'] == 'phone':
            if text == '/cancel':
                del auth_sessions[user_id]
                await event.reply("❌ Отменено")
                return
            
            if not text.startswith('+') or len(text) < 10:
                await event.reply("❌ Неверный формат\n/cancel — отмена")
                return
            
            try:
                client = TelegramClient(f'session_{user_id}', API_ID, API_HASH)
                await client.connect()
                
                sent_code = await client.send_code_request(text)
                
                session['step'] = 'code'
                session['phone'] = text
                session['phone_code_hash'] = sent_code.phone_code_hash
                session['client'] = client
                
                await event.reply(f"📲 Код отправлен на {text}\n\nВведи 5 цифр:\n/cancel — отмена")
                
            except Exception as e:
                logger.error(f"Ошибка: {e}")
                await event.reply(f"❌ Ошибка\n/cancel — отмена")
                if 'client' in session:
                    await session['client'].disconnect()
                del auth_sessions[user_id]
        
        # Шаг 2: Код
        elif session['step'] == 'code':
            if text == '/cancel':
                await session['client'].disconnect()
                del auth_sessions[user_id]
                await event.reply("❌ Отменено")
                return
            
            if not text.isdigit() or len(text) != 5:
                await event.reply("❌ 5 цифр нужно\n/cancel — отмена")
                return
            
            try:
                await session['client'].sign_in(
                    phone=session['phone'],
                    code=text,
                    phone_code_hash=session['phone_code_hash']
                )
                
                await complete_auth(user_id, session)
                
            except SessionPasswordNeededError:
                session['step'] = 'password'
                await event.reply("🔐 Введи пароль 2FA:\n/cancel — отмена")
            except Exception as e:
                logger.error(f"Ошибка входа: {e}")
                await event.reply("❌ Неверный код\n/cancel — отмена")
                await session['client'].disconnect()
                del auth_sessions[user_id]
        
        # Шаг 3: Пароль 2FA
        elif session['step'] == 'password':
            if text == '/cancel':
                await session['client'].disconnect()
                del auth_sessions[user_id]
                await event.reply("❌ Отменено")
                return
            
            try:
                await session['client'].sign_in(password=text)
                await complete_auth(user_id, session)
            except Exception as e:
                logger.error(f"Ошибка 2FA: {e}")
                await event.reply("❌ Неверный пароль\n/cancel — отмена")
                await session['client'].disconnect()
                del auth_sessions[user_id]
    
    return bot

async def complete_auth(user_id, session):
    """Завершение авторизации"""
    try:
        client = session['client']
        me = await client.get_me()
        
        client.session.save()
        user_clients[user_id] = client
        owner_names[user_id] = me.first_name
        
        asyncio.create_task(setup_user_client(client, user_id))
        
        await bot.send_message(
            session['chat_id'],
            f"✅ **ПОДКЛЮЧЕНО!**\n\n"
            f"Привет, {me.first_name}!\n\n"
            "💬 **Теперь в чатах:**\n"
            "`.старт` — включить AI-девушку\n"
            "`.стоп` — выключить\n\n"
            "🤖 Она будет отвечать собеседникам!",
            parse_mode='md'
        )
        
        logger.info(f"Пользователь {user_id} ({me.first_name}) подключен")
        del auth_sessions[user_id]
        
    except Exception as e:
        logger.error(f"Ошибка завершения: {e}")
        await bot.send_message(
            session['chat_id'],
            f"❌ Ошибка: {str(e)[:50]}"
        )

# ==================== ЮЗЕР-БОТ ====================
async def setup_user_client(client, owner_id):
    """Настройка юзер-бота"""
    
    @client.on(events.NewMessage(pattern=r'\.старт'))
    async def start_handler(event):
        try:
            chat = await event.get_chat()
            sender = await event.get_sender()
            me = await client.get_me()
            
            if sender.id != me.id:
                return
            
            if chat.id not in active_chats:
                active_chats[chat.id] = owner_id
                conversation_history[chat.id] = []
                
                greeting = await get_ai_response(
                    "Пользователь активировал тебя. Будь грубой, флиртуй, проявляй инициативу. Начни разговор.",
                    chat.id,
                    "System"
                )
                
                await event.reply(greeting)
                logger.info(f"AI включена в чате {chat.id}")
                
        except Exception as e:
            logger.error(f"Ошибка старта: {e}")
    
    @client.on(events.NewMessage(pattern=r'\.стоп'))
    async def stop_handler(event):
        try:
            chat = await event.get_chat()
            sender = await event.get_sender()
            me = await client.get_me()
            
            if sender.id != me.id:
                return
            
            if chat.id in active_chats and active_chats[chat.id] == owner_id:
                del active_chats[chat.id]
                if chat.id in conversation_history:
                    del conversation_history[chat.id]
                
                await event.reply("Ну и ладно... ушла 😒")
                logger.info(f"AI выключена в чате {chat.id}")
                
        except Exception as e:
            logger.error(f"Ошибка стоп: {e}")
    
    @client.on(events.NewMessage)
    async def message_handler(event):
        """Обработка сообщений собеседников"""
        try:
            message = event.message
            chat = await event.get_chat()
            sender = await event.get_sender()
            
            me = await client.get_me()
            if sender.id == me.id:
                return
            
            if chat.id not in active_chats:
                return
            
            if active_chats[chat.id] != owner_id:
                return
            
            message_text = message.text or ""
            if not message_text.strip() or message_text.startswith('.'):
                return
            
            sender_name = getattr(sender, 'first_name', 'Неизвестный')
            if hasattr(sender, 'username') and sender.username:
                sender_name = f"@{sender.username}"
            
            logger.info(f"Сообщение от {sender_name}: {message_text[:30]}...")
            
            ai_response = await get_ai_response(message_text, chat.id, sender_name)
            
            await event.reply(ai_response)
            logger.info(f"AI ответила: {ai_response[:30]}...")
            
        except Exception as e:
            logger.error(f"Ошибка обработки: {e}")

# ==================== ЗАПУСК ====================
async def main():
    """Основная функция"""
    logger.info("🚀 Запуск AI Girlfriend Bot...")
    
    # Запускаем основного бота
    global bot
    bot = await setup_bot()
    me = await bot.get_me()
    logger.info(f"🤖 Бот запущен: @{me.username}")
    
    # Загружаем существующие сессии
    for file in os.listdir('.'):
        if file.startswith('session_') and file.endswith('.session'):
            try:
                user_id_str = file.replace('session_', '').replace('.session', '')
                if user_id_str.isdigit():
                    user_id = int(user_id_str)
                    
                    client = TelegramClient(file, API_ID, API_HASH)
                    await client.connect()
                    
                    if await client.is_user_authorized():
                        me_user = await client.get_me()
                        user_clients[user_id] = client
                        owner_names[user_id] = me_user.first_name
                        asyncio.create_task(setup_user_client(client, user_id))
                        logger.info(f"📂 Сессия: {me_user.first_name}")
                    else:
                        await client.disconnect()
                        os.remove(file)
            except Exception as e:
                logger.error(f"Ошибка загрузки {file}: {e}")
    
    logger.info("✅ Система готова")
    
    # Уведомление
    try:
        await bot.send_message(
            "MaksimXyila",
            f"🤖 **AI Girlfriend Bot запущен!**\n"
            f"Бот: @{me.username}\n"
            f"Время: {datetime.now().strftime('%H:%M:%S')}",
            parse_mode='md'
        )
    except:
        pass
    
    await bot.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановка бота...")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
