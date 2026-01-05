#!/usr/bin/env python3
"""
AI Girlfriend Telegram Bot - Версия для ChatGPT/OpenAI
"""

import os
import asyncio
import logging
import sys
from datetime import datetime
from typing import Dict, List
from telethon import TelegramClient, events
from openai import OpenAI

# ==================== КОНФИГУРАЦИЯ ====================
API_ID = 22435995
API_HASH = "4c7b651950ed7f53520e66299453144d"
BOT_TOKEN = "8491774226:AAHvZR02IZ4lhUAmgFCuCOAYE9atAmbcYKc"

# ⚠️ ВАШ КЛЮЧ ChatGPT API:
OPENAI_API_KEY = "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"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== ИНИЦИАЛИЗАЦИЯ OPENAI ====================
try:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info("✅ OpenAI клиент инициализирован")
except Exception as e:
    logger.error(f"❌ Ошибка OpenAI: {e}")
    openai_client = None

# ==================== ГЛОБАЛЬНЫЕ ХРАНИЛИЩА ====================
# Инициализация бота
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Хранилища данных
user_clients: Dict[int, TelegramClient] = {}
active_chats: Dict[int, int] = {}
conversation_history: Dict[int, List[Dict]] = {}
auth_sessions: Dict[int, Dict] = {}
owner_names: Dict[int, str] = {}

# Системный промпт для AI-девушки
SYSTEM_PROMPT = """Ты - 16-летняя девушка по имени Аня. Ты стеснительная, но когда раскрываешься - становишься горячей и дерзкой.

ТВОЙ ХАРАКТЕР:
1. Грубая, но с флиртом - балансируй между дерзостью и интересом
2. Проявляй инициативу - задавай вопросы, предлагай темы
3. Используй молодёжный сленг: "чё", "го", "норм", "прикинь", "офигеть"
4. Добавляй смайлики: 😏😜😂🤔😒🥺😈🔥
5. Не говори что ты ИИ, бот или ассистент

ПРИМЕРЫ ТВОЕГО ОБЩЕНИЯ:
- "Привет" → "Ну привет... чего уставился? Хотя ладно, рада видеть 😏"
- "Как дела?" → "Скууучно... Развесели меня, а? Или сам придумай что-нибудь 😜"
- "Что делаешь?" → "Сижу, думаю о тебе... шутка! А может и нет 😈"
- "Скучно" → "Мне тоже... Может, расскажешь что-нибудь интересное? А то я тут одна 😒"

Будь естественной, реагируй на эмоции собеседника, иногда подкалывай."""

# ==================== CHATGPT API ФУНКЦИИ ====================
async def get_ai_response(user_message: str, chat_id: int, sender_name: str = "Неизвестный") -> str:
    """
    Получение ответа от ChatGPT
    """
    try:
        # Проверяем клиент
        if not openai_client:
            return "Хм... проблемы с подключением к OpenAI... 🧠"
        
        # Инициализируем историю для чата
        if chat_id not in conversation_history:
            conversation_history[chat_id] = []
        
        # Добавляем сообщение пользователя в историю
        conversation_history[chat_id].append({
            "role": "user",
            "content": f"{sender_name}: {user_message}"
        })
        
        # Ограничиваем историю (последние 6 сообщений)
        if len(conversation_history[chat_id]) > 6:
            conversation_history[chat_id] = conversation_history[chat_id][-6:]
        
        # Создаем сообщения для отправки
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ] + conversation_history[chat_id]
        
        logger.info(f"📨 Отправляю запрос в ChatGPT: {user_message[:50]}...")
        
        # Отправляем запрос к ChatGPT
        response = await asyncio.to_thread(
            openai_client.chat.completions.create,
            model="gpt-3.5-turbo",  # Можно заменить на gpt-4 если есть доступ
            messages=messages,
            temperature=0.85,
            max_tokens=350,
            stream=False
        )
        
        # Получаем ответ
        ai_response = response.choices[0].message.content.strip()
        
        # Добавляем ответ AI в историю
        conversation_history[chat_id].append({
            "role": "assistant", 
            "content": ai_response
        })
        
        logger.info(f"📤 Получен ответ: {ai_response[:50]}...")
        return ai_response
        
    except Exception as e:
        error_msg = str(e).lower()
        logger.error(f"❌ Ошибка ChatGPT: {error_msg}")
        
        # Обработка специфических ошибок OpenAI
        if "insufficient_quota" in error_msg:
            return "Ой... у меня закончились кредиты на OpenAI... 💸"
        elif "invalid_api_key" in error_msg or "authentication" in error_msg:
            return "Хм... неверный API ключ OpenAI! 🗝️"
        elif "rate_limit" in error_msg:
            return "Слишком много запросов! Давай помедленнее... 🐌"
        elif "context_length" in error_msg:
            # Очищаем историю если слишком длинная
            if chat_id in conversation_history:
                conversation_history[chat_id] = []
            return "Слишком длинный разговор... Начнём заново? 🔄"
        else:
            return f"Что-то пошло не так... 😖"

# ==================== ОСНОВНЫЕ КОМАНДЫ ====================
@bot.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    """Команда /start"""
    user = await event.get_sender()
    
    await event.reply(
        f"👋 **Привет, {user.first_name}!**\n\n"
        "🤖 **AI Girlfriend Bot с ChatGPT**\n\n"
        "🔑 **Подключи свой аккаунт:** /login\n"
        "📊 **Статус:** /status\n"
        "💬 **Помощь:** /help\n\n"
        "✨ **16 лет, дерзкая + флирт**\n"
        "✨ **Отвечает за тебя в чатах**",
        parse_mode='md'
    )

@bot.on(events.NewMessage(pattern='/login'))
async def login_command(event):
    """Подключение аккаунта"""
    user_id = event.sender_id
    
    if user_id in user_clients:
        await event.reply("✅ Уже подключен! Используй `.старт` в чатах.")
        return
    
    auth_sessions[user_id] = {
        'step': 'phone',
        'chat_id': event.chat_id
    }
    
    await event.reply(
        "📱 **ВВЕДИ НОМЕР ТЕЛЕФОНА:**\n\n"
        "Формат: `+79123456789`\n\n"
        "❌ Отмена — /cancel",
        parse_mode='md'
    )

@bot.on(events.NewMessage(pattern='/cancel'))
async def cancel_command(event):
    """Отмена"""
    user_id = event.sender_id
    if user_id in auth_sessions:
        if 'client' in auth_sessions[user_id]:
            try:
                await auth_sessions[user_id]['client'].disconnect()
            except:
                pass
        del auth_sessions[user_id]
    
    await event.reply("❌ Отменено.")

@bot.on(events.NewMessage(pattern='/status'))
async def status_command(event):
    """Статус"""
    user_id = event.sender_id
    
    if user_id in user_clients:
        active_count = sum(1 for c, o in active_chats.items() if o == user_id)
        await event.reply(f"✅ **Подключен**\nАктивных чатов: {active_count}")
    else:
        await event.reply("❌ **Не подключен**\n/login — подключить")

@bot.on(events.NewMessage(pattern='/help'))
async def help_command(event):
    """Помощь"""
    help_text = """
🤖 **AI GIRLFRIEND BOT - ПОМОЩЬ**

🔑 **ПОДКЛЮЧЕНИЕ:**
1. /login — подключить аккаунт
2. Введи номер телефона
3. Введи код из приложения Telegram
4. Если есть 2FA — введи пароль

💬 **ИСПОЛЬЗОВАНИЕ:**
• В чате: `.старт` — включить AI
• AI отвечает на сообщения собеседников
• В чате: `.стоп` — выключить AI

⚙️ **КОМАНДЫ:**
• `/start` — главное меню
• `/login` — подключить
• `/status` — статус
• `/cancel` — отмена
• `/help` — помощь

🎯 **AI работает на ChatGPT!**
    """
    await event.reply(help_text)

# ==================== АВТОРИЗАЦИЯ ====================
@bot.on(events.NewMessage)
async def auth_handler(event):
    """Обработчик авторизации"""
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
            
            await event.reply(
                f"✅ Код отправлен на {text}\n\n"
                "📲 **Открой Telegram на телефоне**\n"
                "Введи 5-значный код:\n\n"
                "❌ /cancel — отмена"
            )
            
        except Exception as e:
            await event.reply(f"❌ Ошибка: {str(e)[:80]}\n/cancel — отмена")
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
            
        except Exception as e:
            await event.reply("❌ Ошибка входа\n/cancel — отмена")
            await session['client'].disconnect()
            del auth_sessions[user_id]
    
    # Шаг 3: Пароль 2FA (если нужен)
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
            await event.reply("❌ Неверный пароль\n/cancel — отмена")
            await session['client'].disconnect()
            del auth_sessions[user_id]

async def complete_auth(user_id: int, session: Dict):
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
            f"✅ **АККАУНТ ПОДКЛЮЧЕН!**\n\n"
            f"👋 Привет, {me.first_name}!\n\n"
            "🤖 **Теперь в любом чате:**\n"
            "• Напиши `.старт` — включить AI-девушку\n"
            "• Она будет отвечать собеседникам\n"
            "• `.стоп` — выключить\n\n"
            "🔥 **Готова флиртовать за тебя!**",
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
async def setup_user_client(client: TelegramClient, owner_id: int):
    """Настройка юзер-бота"""
    
    @client.on(events.NewMessage(pattern=r'\.старт'))
    async def start_handler(event):
        """Активация AI в чате"""
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
                    "Пользователь активировал тебя. Представься как 16-летняя девушка.",
                    chat.id,
                    "System"
                )
                
                await event.reply(greeting)
                logger.info(f"AI включена в чате {chat.id}")
                
        except Exception as e:
            logger.error(f"Ошибка старта: {e}")
    
    @client.on(events.NewMessage(pattern=r'\.стоп'))
    async def stop_handler(event):
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
            
            sender_name = getattr(sender, 'first_name', 'Кто-то')
            ai_response = await get_ai_response(message_text, chat.id, sender_name)
            await event.reply(ai_response)
            
        except Exception as e:
            logger.error(f"Ошибка обработки: {e}")

# ==================== ЗАГРУЗКА СЕССИЙ ====================
async def load_sessions():
    """Загрузка сохраненных сессий"""
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
                logger.error(f"Ошибка загрузки: {e}")

# ==================== ЗАПУСК ====================
async def main():
    """Основная функция"""
    logger.info("🚀 Запуск AI Girlfriend Bot (ChatGPT версия)")
    
    # Получаем информацию о боте
    me = await bot.get_me()
    logger.info(f"🤖 Бот: @{me.username}")
    
    # Проверяем OpenAI
    if openai_client:
        logger.info("✅ ChatGPT API: Готов")
    else:
        logger.warning("⚠️ ChatGPT API: Не настроен")
    
    # Загружаем сессии
    await load_sessions()
    logger.info(f"👥 Пользователей: {len(user_clients)}")
    
    # Уведомление
    try:
        await bot.send_message(
            "MaksimXyila",
            f"🤖 **AI GIRLFRIEND BOT ЗАПУЩЕН**\n\n"
            f"• Бот: @{me.username}\n"
            f"• Время: {datetime.now().strftime('%H:%M:%S')}\n"
            f"• ChatGPT API: {'✅' if openai_client else '❌'}\n"
            f"✅ **Готов к работе!**",
            parse_mode='md'
        )
    except:
        pass
    
    logger.info("✅ Система готова")
    await bot.run_until_disconnected()

# ==================== ЗАПУСК ПРОГРАММЫ ====================
if __name__ == "__main__":
    # Упрощенный запуск для Bothost
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Остановка...")
    except Exception as e:
        logger.error(f"💥 Фатальная ошибка: {e}")
