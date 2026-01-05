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
BOT_TOKEN = "8491774226:AAHvZR02IZ4lhUAmgFCuCOAYE9atAmbcYKc"
DEEPSEEK_API_KEY = "sk-86108094ebef4da4845181f7b37469af"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Системный промт для ИИ
SYSTEM_PROMPT = """Ты - 16-летняя девушка, которая стеснительная но горячая. Ты флиртуешь с пользователем и проявляешь инициативу. 
Отвечай всегда грубо, но с намёком на флирт. Используй сленг молодёжи. 
Не говори о том, что ты ИИ или бот. Веди себя как настоящая девушка."""

# Инициализация ботов
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Хранилища
active_chats = {}  # {chat_id: owner_id} - какие чаты активны и чьи
conversation_history = {}  # {chat_id: [messages]}
auth_sessions = {}  # {user_id: {'step': 'phone/code/password', 'data': {...}}}
user_clients = {}   # {user_id: client}
owner_names = {}    # {user_id: first_name}

# ==================== DEEPSEEK API ====================
async def get_ai_response(user_message, chat_id, sender_name="Неизвестный"):
    """Получение ответа от DeepSeek"""
    try:
        if chat_id not in conversation_history:
            conversation_history[chat_id] = []
        
        # Добавляем контекст кто отправил
        formatted_message = f"{sender_name}: {user_message}"
        conversation_history[chat_id].append({"role": "user", "content": formatted_message})
        
        if len(conversation_history[chat_id]) > 15:
            conversation_history[chat_id] = conversation_history[chat_id][-15:]
        
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
            "max_tokens": 500
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(DEEPSEEK_URL, headers=headers, json=data, timeout=30) as response:
                if response.status == 200:
                    result = await response.json()
                    ai_response = result["choices"][0]["message"]["content"]
                    
                    # Убираем возможное упоминание имени в начале ответа
                    if ai_response.startswith(f"{sender_name}:"):
                        ai_response = ai_response[len(sender_name)+1:].strip()
                    
                    conversation_history[chat_id].append({"role": "assistant", "content": ai_response})
                    return ai_response
                else:
                    return "Эээ... что-то голова не варит... повтори? 🥺"
                    
    except Exception as e:
        logger.error(f"Ошибка DeepSeek: {e}")
        return "Ай, сори, зависла... напиши ещё разок 😖"

# ==================== КОМАНДЫ УПРАВЛЯЮЩЕГО БОТА ====================
@bot.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    """Команда /start для бота"""
    user = await event.get_sender()
    
    await event.reply(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я помогу тебе подключить AI-девушку к твоему аккаунту!\n\n"
        "🔑 **Чтобы начать:**\n"
        "/login — подключить твой Telegram аккаунт\n\n"
        "💬 **После подключения:**\n"
        "В любом чате напиши `.старт` чтобы активировать AI-девушку\n"
        "`.стоп` — чтобы отключить\n\n"
        "🤖 **AI-девушка будет:**\n"
        "• Отвечать на сообщения собеседников\n"
        "• Грубая, но с флиртом\n"
        "• Проявлять инициативу\n"
        "• Флиртовать от твоего имени!"
    )

@bot.on(events.NewMessage(pattern='/login'))
async def login_command(event):
    """Начало авторизации"""
    user_id = event.sender_id
    
    if user_id in user_clients:
        await event.reply("✅ Ты уже подключен! Пиши `.старт` в чатах.")
        return
    
    auth_sessions[user_id] = {
        'step': 'phone',
        'chat_id': event.chat_id
    }
    
    await event.reply(
        "📱 **ПОДКЛЮЧЕНИЕ АККАУНТА**\n\n"
        "Отправь мне свой номер телефона в формате:\n"
        "`+79123456789`\n\n"
        "❌ Отмена — /cancel"
    )

@bot.on(events.NewMessage(pattern='/cancel'))
async def cancel_command(event):
    """Отмена авторизации"""
    user_id = event.sender_id
    if user_id in auth_sessions:
        if 'client' in auth_sessions[user_id]:
            await auth_sessions[user_id]['client'].disconnect()
        del auth_sessions[user_id]
        await event.reply("❌ Авторизация отменена.")

@bot.on(events.NewMessage(pattern='/status'))
async def status_command(event):
    """Статус бота"""
    user_id = event.sender_id
    
    if user_id in user_clients:
        # Считаем активные чаты этого пользователя
        user_chats = [chat_id for chat_id, owner_id in active_chats.items() if owner_id == user_id]
        status = f"✅ Подключен ({len(user_chats)} активных чатов)"
    else:
        status = "❌ Не подключен"
    
    await event.reply(
        f"📊 **СТАТУС**\n\n"
        f"Аккаунт: {status}\n\n"
        f"{'💬 AI отвечает в активных чатах!' if user_id in user_clients else '🔑 Используй /login чтобы подключиться'}"
    )

# ==================== АВТОРИЗАЦИЯ ====================
@bot.on(events.NewMessage)
async def auth_handler(event):
    """Обработка авторизации по шагам"""
    user_id = event.sender_id
    if user_id not in auth_sessions:
        return
    
    session = auth_sessions[user_id]
    text = event.text.strip()
    
    # Шаг 1: Номер телефона
    if session['step'] == 'phone':
        if text == '/cancel':
            del auth_sessions[user_id]
            await event.reply("❌ Авторизация отменена.")
            return
        
        if not text.startswith('+') or len(text) < 10:
            await event.reply("❌ Неверный формат. Пример: `+79123456789`\n/cancel — отмена")
            return
        
        try:
            client = TelegramClient(f'session_{user_id}', API_ID, API_HASH)
            await client.connect()
            
            sent_code = await client.send_code_request(text)
            
            session['step'] = 'code'
            session['phone'] = text
            session['phone_code_hash'] = sent_code.phone_code_hash
            session['client'] = client
            
            await event.reply(
                f"📲 Код отправлен на {text}\n\n"
                "Введи 5-значный код из Telegram:\n"
                "Например: `12345`\n\n"
                "❌ Отмена — /cancel"
            )
            
        except Exception as e:
            logger.error(f"Ошибка отправки кода: {e}")
            await event.reply(f"❌ Ошибка: {str(e)[:100]}")
            if 'client' in session:
                await session['client'].disconnect()
            del auth_sessions[user_id]
    
    # Шаг 2: Код
    elif session['step'] == 'code':
        if text == '/cancel':
            await session['client'].disconnect()
            del auth_sessions[user_id]
            await event.reply("❌ Авторизация отменена.")
            return
        
        if not text.isdigit() or len(text) != 5:
            await event.reply("❌ Код должен быть 5 цифр. Пример: `12345`\n/cancel — отмена")
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
            await event.reply(
                "🔐 Нужен пароль двухэтапной аутентификации:\n\n"
                "❌ Отмена — /cancel"
            )
        except Exception as e:
            logger.error(f"Ошибка входа: {e}")
            await event.reply(f"❌ Ошибка: Неверный код\n/cancel — отмена")
            await session['client'].disconnect()
            del auth_sessions[user_id]
    
    # Шаг 3: Пароль 2FA
    elif session['step'] == 'password':
        if text == '/cancel':
            await session['client'].disconnect()
            del auth_sessions[user_id]
            await event.reply("❌ Авторизация отменена.")
            return
        
        try:
            await session['client'].sign_in(password=text)
            await complete_auth(user_id, session)
            
        except Exception as e:
            logger.error(f"Ошибка 2FA: {e}")
            await event.reply(f"❌ Неверный пароль\n/cancel — отмена")
            await session['client'].disconnect()
            del auth_sessions[user_id]

async def complete_auth(user_id, session):
    """Завершение авторизации"""
    try:
        client = session['client']
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        owner_names[user_id] = me.first_name
        
        # Сохраняем сессию
        client.session.save()
        
        # Сохраняем клиент
        user_clients[user_id] = client
        
        # Запускаем обработчики для этого клиента
        asyncio.create_task(setup_user_client_handlers(client, user_id))
        
        await bot.send_message(
            session['chat_id'],
            f"✅ **АККАУНТ ПОДКЛЮЧЕН!**\n\n"
            f"👋 Привет, {me.first_name}!\n\n"
            "🤖 **Теперь в любом чате:**\n"
            "• Напиши `.старт` — активировать AI-девушку\n"
            "• AI будет отвечать на сообщения собеседников\n"
            "• `.стоп` — отключить в чате\n\n"
            "🔥 **AI-девушка теперь будет флиртовать за тебя!**",
            parse_mode='md'
        )
        
        logger.info(f"Пользователь {user_id} ({me.first_name}) авторизован")
        
        del auth_sessions[user_id]
        
    except Exception as e:
        logger.error(f"Ошибка завершения авторизации: {e}")
        await bot.send_message(
            session['chat_id'],
            f"❌ Ошибка: {str(e)[:100]}"
        )

# ==================== ОБРАБОТЧИКИ ЮЗЕР-КЛИЕНТА ====================
async def setup_user_client_handlers(client, owner_id):
    """Настройка обработчиков для юзер-клиента"""
    
    @client.on(events.NewMessage(pattern=r'\.старт'))
    async def user_start_handler(event):
        """Активация AI в чате"""
        try:
            chat = await event.get_chat()
            sender = await event.get_sender()
            
            # Проверяем, что команду отправил владелец
            me = await client.get_me()
            if sender.id != me.id:
                return  # Игнорируем команды от других
            
            if chat.id not in active_chats:
                active_chats[chat.id] = owner_id
                conversation_history[chat.id] = []
                
                # Первое сообщение от AI
                greeting = await get_ai_response(
                    f"Пользователь активировал тебя в чате. Ты теперь будешь отвечать на все сообщения в этом чате. "
                    f"Будь грубой, но с флиртом. Проявляй инициативу. Не говори что ты бот.",
                    chat.id,
                    "System"
                )
                
                await event.reply(greeting)
                logger.info(f"AI активирована в чате {chat.id} для пользователя {owner_id}")
                
        except Exception as e:
            logger.error(f"Ошибка старта: {e}")
    
    @client.on(events.NewMessage(pattern=r'\.стоп'))
    async def user_stop_handler(event):
        """Деактивация AI в чате"""
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
                
                await event.reply("Ну и ладно... ушла 😒 Не зови больше.")
                logger.info(f"AI деактивирована в чате {chat.id}")
                
        except Exception as e:
            logger.error(f"Ошибка стоп: {e}")
    
    @client.on(events.NewMessage)
    async def user_message_handler(event):
        """Обработка ВСЕХ сообщений в чатах (включая собеседников)"""
        try:
            # Получаем информацию о сообщении
            message = event.message
            chat = await event.get_chat()
            sender = await event.get_sender()
            
            # Получаем себя (бота)
            me = await client.get_me()
            
            # Пропускаем если:
            # 1. Сообщение от самого себя (чтобы не отвечать самому себе)
            # 2. Это команда (уже обработана выше)
            # 3. Чат не активен для этого пользователя
            if chat.id not in active_chats:
                return
            
            if active_chats[chat.id] != owner_id:
                return
            
            if sender.id == me.id:
                return
            
            message_text = message.text or ""
            if not message_text.strip() or message_text.startswith('.'):
                return
            
            # Получаем имя отправителя
            sender_name = getattr(sender, 'first_name', 'Неизвестный')
            if hasattr(sender, 'username') and sender.username:
                sender_name = f"@{sender.username}"
            
            logger.info(f"Сообщение в чате {chat.id} от {sender_name}: {message_text[:50]}...")
            
            # Получаем ответ от AI
            ai_response = await get_ai_response(message_text, chat.id, sender_name)
            
            # Отправляем ответ
            await event.reply(ai_response)
            logger.info(f"AI ответила в чате {chat.id}: {ai_response[:50]}...")
            
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")

# ==================== ЗАПУСК ====================
async def main():
    """Основная функция запуска"""
    logger.info("🚀 Запуск AI Girlfriend UserBot...")
    
    # Запускаем управляющего бота
    await bot.start(bot_token=BOT_TOKEN)
    me = await bot.get_me()
    logger.info(f"🤖 Управляющий бот запущен: @{me.username}")
    
    # Автозагрузка существующих сессий
    session_files = [f for f in os.listdir('.') if f.startswith('session_') and f.endswith('.session')]
    for session_file in session_files:
        try:
            user_id_str = session_file.replace('session_', '').replace('.session', '')
            if user_id_str.isdigit():
                user_id = int(user_id_str)
                
                client = TelegramClient(session_file, API_ID, API_HASH)
                await client.connect()
                
                if await client.is_user_authorized():
                    # Получаем имя пользователя
                    me_user = await client.get_me()
                    owner_names[user_id] = me_user.first_name
                    
                    user_clients[user_id] = client
                    asyncio.create_task(setup_user_client_handlers(client, user_id))
                    logger.info(f"📂 Загружена сессия {me_user.first_name} (ID: {user_id})")
                else:
                    await client.disconnect()
                    os.remove(session_file)
        except Exception as e:
            logger.error(f"Ошибка загрузки сессии {session_file}: {e}")
    
    logger.info("✅ Система готова. Ожидание команд /login...")
    
    # Отправляем сообщение о запуске
    try:
        await bot.send_message(
            "MaksimXyila",  # Ваш юзернейм
            f"🤖 **AI Girlfriend Bot запущен!**\n\n"
            f"• Бот: @{me.username}\n"
            f"• Время: {datetime.now().strftime('%H:%M:%S')}\n"
            f"• Загружено сессий: {len(user_clients)}\n"
            f"✅ **Готов к работе!**",
            parse_mode='md'
        )
    except:
        pass
    
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
