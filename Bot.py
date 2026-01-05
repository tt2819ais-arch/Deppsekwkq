#!/usr/bin/env python3
"""
AI Girlfriend Telegram Bot - Исправленная версия для Bothost
"""

import os
import asyncio
import logging
import signal
import sys
import atexit
from datetime import datetime
from typing import Dict, List
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from openai import OpenAI
import nest_asyncio

# ==================== КОНФИГУРАЦИЯ ====================
API_ID = 22435995
API_HASH = "4c7b651950ed7f53520e66299453144d"
BOT_TOKEN = "8491774226:AAHvZR02IZ4lhUAmgFCuCOAYE9atAmbcYKc"

# ⚠️ ВАЖНО: Получите ключ на https://platform.deepseek.com/api_keys
DEEPSEEK_API_KEY = "sk-86108094ebef4da4845181f7b37469af"

# Применяем nest_asyncio для Bothost
nest_asyncio.apply()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
bot = None
deepseek_client = None
user_clients: Dict[int, TelegramClient] = {}
active_chats: Dict[int, int] = {}
conversation_history: Dict[int, List[Dict]] = {}
auth_sessions: Dict[int, Dict] = {}
owner_names: Dict[int, str] = {}

SYSTEM_PROMPT = """Ты - 16-летняя девушка по имени Аня. Ты стеснительная, но когда раскрываешься - становишься горячей и дерзкой.
Будь грубой, но с флиртом, используй молодёжный сланг. Не говори что ты ИИ."""

# ==================== DEEPSEEK API ====================
def init_deepseek():
    """Инициализация DeepSeek клиента"""
    global deepseek_client
    try:
        if DEEPSEEK_API_KEY and not DEEPSEEK_API_KEY.startswith("sk-ваш_ключ"):
            deepseek_client = OpenAI(
                api_key=DEEPSEEK_API_KEY,
                base_url="https://api.deepseek.com",
                timeout=30.0
            )
            logger.info("✅ DeepSeek клиент инициализирован")
        else:
            logger.warning("⚠️ DeepSeek API ключ не настроен")
    except Exception as e:
        logger.error(f"❌ Ошибка DeepSeek: {e}")

async def get_ai_response(user_message: str, chat_id: int, sender_name: str = "Кто-то") -> str:
    """Получение ответа от AI"""
    try:
        if not deepseek_client:
            return "Настрой API ключ DeepSeek! 🗝️"
        
        if chat_id not in conversation_history:
            conversation_history[chat_id] = []
        
        conversation_history[chat_id].append({
            "role": "user",
            "content": f"{sender_name}: {user_message}"
        })
        
        if len(conversation_history[chat_id]) > 6:
            conversation_history[chat_id] = conversation_history[chat_id][-6:]
        
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(conversation_history[chat_id])
        
        # Синхронный вызов в отдельном потоке
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                temperature=0.8,
                max_tokens=300,
                stream=False
            )
        )
        
        ai_response = response.choices[0].message.content
        conversation_history[chat_id].append({"role": "assistant", "content": ai_response})
        
        return ai_response
        
    except Exception as e:
        logger.error(f"Ошибка AI: {e}")
        return "Что-то с мозгами... 😖"

# ==================== УПРАВЛЯЮЩИЙ БОТ ====================
async def setup_bot():
    """Настройка бота"""
    global bot
    
    bot = TelegramClient('bot_session', API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)
    
    # Регистрируем команды
    @bot.on(events.NewMessage(pattern='/start'))
    async def start_cmd(event):
        user = await event.get_sender()
        await event.reply(f"Привет, {user.first_name}! 👋\n\n/link — подключить аккаунт")
    
    @bot.on(events.NewMessage(pattern='/link'))
    async def link_cmd(event):
        user_id = event.sender_id
        if user_id in user_clients:
            await event.reply("✅ Уже подключен!\nИспользуй `.start` в чатах")
            return
        
        auth_sessions[user_id] = {'step': 'phone', 'chat_id': event.chat_id}
        await event.reply("📱 Введи номер телефона (+79123456789):\n/cancel — отмена")
    
    @bot.on(events.NewMessage(pattern='/cancel'))
    async def cancel_cmd(event):
        user_id = event.sender_id
        if user_id in auth_sessions:
            if 'client' in auth_sessions[user_id]:
                await auth_sessions[user_id]['client'].disconnect()
            del auth_sessions[user_id]
            await event.reply("❌ Отменено")
    
    @bot.on(events.NewMessage(pattern='/status'))
    async def status_cmd(event):
        user_id = event.sender_id
        if user_id in user_clients:
            chats = sum(1 for c, o in active_chats.items() if o == user_id)
            await event.reply(f"✅ Подключен\nАктивных чатов: {chats}")
        else:
            await event.reply("❌ Не подключен\n/link — подключить")
    
    # Обработчик авторизации
    @bot.on(events.NewMessage)
    async def auth_handler(event):
        user_id = event.sender_id
        if user_id not in auth_sessions:
            return
        
        session = auth_sessions[user_id]
        text = event.text.strip()
        
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
                
                await event.reply(f"✅ Код отправлен на {text}\nВведи 5 цифр:\n/cancel — отмена")
                
            except Exception as e:
                await event.reply(f"❌ Ошибка: {str(e)[:80]}")
                if 'client' in session:
                    await session['client'].disconnect()
                del auth_sessions[user_id]
        
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
                await event.reply("❌ Ошибка входа\n/cancel — отмена")
                await session['client'].disconnect()
                del auth_sessions[user_id]
        
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
    
    return bot

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
            f"✅ **Подключено!** Привет, {me.first_name}!\n\n"
            "💬 **В чатах используй:**\n"
            "`.start` — включить AI\n"
            "`.stop` — выключить\n\n"
            "🤖 AI будет отвечать за тебя!",
            parse_mode='md'
        )
        
        logger.info(f"Пользователь {user_id} подключен")
        del auth_sessions[user_id]
        
    except Exception as e:
        logger.error(f"Ошибка завершения: {e}")
        await bot.send_message(session['chat_id'], f"❌ Ошибка: {str(e)[:50]}")

# ==================== ЮЗЕР-БОТ ====================
async def setup_user_client(client: TelegramClient, owner_id: int):
    """Настройка юзер-бота"""
    
    @client.on(events.NewMessage(pattern=r'\.start'))
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
                    "Пользователь активировал тебя. Представься как 16-летняя девушка.",
                    chat.id,
                    "System"
                )
                
                await event.reply(greeting)
                logger.info(f"AI включена в чате {chat.id}")
                
        except Exception as e:
            logger.error(f"Ошибка старта: {e}")
    
    @client.on(events.NewMessage(pattern=r'\.stop'))
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
                
                await event.reply("Ну и ладно... 😒")
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
                logger.error(f"Ошибка загрузки {file}: {e}")

# ==================== ОБРАБОТЧИКИ ЗАКРЫТИЯ ====================
async def shutdown():
    """Корректное завершение работы"""
    logger.info("🛑 Завершение работы...")
    
    # Отключаем всех клиентов
    for client in user_clients.values():
        try:
            await client.disconnect()
        except:
            pass
    
    if bot:
        try:
            await bot.disconnect()
        except:
            pass
    
    logger.info("✅ Бот остановлен")

def signal_handler(signum, frame):
    """Обработчик сигналов"""
    logger.info(f"📞 Получен сигнал {signum}")
    asyncio.create_task(shutdown())

# ==================== ГЛАВНАЯ ФУНКЦИЯ ====================
async def main():
    """Основная функция"""
    logger.info("🚀 Запуск AI Girlfriend Bot")
    
    # Регистрируем обработчики завершения
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    atexit.register(lambda: asyncio.run(shutdown()))
    
    # Инициализируем DeepSeek
    init_deepseek()
    
    # Настраиваем бота
    global bot
    bot = await setup_bot()
    me = await bot.get_me()
    logger.info(f"🤖 Бот: @{me.username}")
    
    # Загружаем сессии
    await load_sessions()
    logger.info(f"👥 Пользователей: {len(user_clients)}")
    
    # Уведомление
    try:
        await bot.send_message(
            "MaksimXyila",
            f"🤖 Бот запущен\n@{me.username}\n{datetime.now().strftime('%H:%M:%S')}",
            parse_mode='md'
        )
    except:
        pass
    
    logger.info("✅ Система готова")
    
    # Запускаем бота
    try:
        await bot.run_until_disconnected()
    finally:
        await shutdown()

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    # Упрощенный запуск для Bothost
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("🛑 Остановка по запросу")
    except Exception as e:
        logger.error(f"💥 Фатальная ошибка: {e}")
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
        except:
            pass