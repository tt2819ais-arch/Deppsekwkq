import os
import asyncio
import logging
import json
from datetime import datetime
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
import aiohttp

# ==================== КОНФИГУРАЦИЯ ====================
API_ID = 22435995
API_HASH = "4c7b651950ed7f53520e66299453144d"
DEEPSEEK_API_KEY = "sk-86108094ebef4da4845181f7b37469af"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# Инициализация клиента
client = None
active_chats = set()  # Чаты где бот активен
user_info = None

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Системный промт для ИИ
SYSTEM_PROMPT = """Ты - 16-летняя девушка, которая стеснительная но горячая. Ты флиртуешь с пользователем и проявляешь инициативу. 
Отвечай всегда грубо, но с намёком на флирт. Используй сленг молодёжи. 
Не говори о том, что ты ИИ или бот. Веди себя как настоящая девушка."""

# История разговоров для каждого чата
conversation_history = {}

# ==================== DEEPSEEK API ====================
async def get_ai_response(user_message, chat_id):
    """Получение ответа от DeepSeek"""
    try:
        if chat_id not in conversation_history:
            conversation_history[chat_id] = []
        
        # Добавляем сообщение пользователя в историю
        conversation_history[chat_id].append({"role": "user", "content": user_message})
        
        # Ограничиваем историю последними 10 сообщениями
        if len(conversation_history[chat_id]) > 10:
            conversation_history[chat_id] = conversation_history[chat_id][-10:]
        
        # Формируем промт с историей
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
            async with session.post(DEEPSEEK_URL, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    ai_response = result["choices"][0]["message"]["content"]
                    
                    # Добавляем ответ в историю
                    conversation_history[chat_id].append({"role": "assistant", "content": ai_response})
                    
                    return ai_response
                else:
                    error_text = await response.text()
                    logger.error(f"DeepSeek API error: {response.status} - {error_text}")
                    return "Эээ... я в ступоре... что-то с сервером 🥺"
                    
    except Exception as e:
        logger.error(f"Ошибка DeepSeek: {e}")
        return "Ай, голова болит... не могу думать сейчас 😖"

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@client.on(events.NewMessage(pattern=r'\.старт'))
async def start_handler(event):
    """Активация бота в чате"""
    chat_id = event.chat_id
    sender = await event.get_sender()
    
    if chat_id not in active_chats:
        active_chats.add(chat_id)
        conversation_history[chat_id] = []
        
        # Первое сообщение при активации
        greeting = await get_ai_response(f"Пользователь активировал тебя в чате. Он: {sender.first_name}. Начни разговор грубо и с флиртом.", chat_id)
        
        await event.reply(greeting)
        logger.info(f"Бот активирован в чате {chat_id} пользователем {sender.first_name}")

@client.on(events.NewMessage(pattern=r'\.стоп'))
async def stop_handler(event):
    """Деактивация бота в чате"""
    chat_id = event.chat_id
    
    if chat_id in active_chats:
        active_chats.remove(chat_id)
        if chat_id in conversation_history:
            del conversation_history[chat_id]
        
        await event.reply("Ну и ладно... ухожу 😒 Не зови больше.")
        logger.info(f"Бот деактивирован в чате {chat_id}")

@client.on(events.NewMessage)
async def message_handler(event):
    """Обработка всех сообщений"""
    try:
        # Проверяем, что сообщение не от самого бота
        sender = await event.get_sender()
        if sender.id == (await client.get_me()).id:
            return
        
        chat_id = event.chat_id
        
        # Если бот активен в этом чате
        if chat_id in active_chats:
            message_text = event.text.strip()
            
            # Игнорируем команды
            if message_text.startswith('.'):
                return
            
            # Получаем ответ от ИИ
            ai_response = await get_ai_response(message_text, chat_id)
            
            # Отправляем ответ
            await event.reply(ai_response)
            logger.info(f"Ответ в чате {chat_id}: {ai_response[:50]}...")
            
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")

# ==================== АВТОРИЗАЦИЯ ====================
async def auth_user():
    """Авторизация пользователя по номеру телефона"""
    global client, user_info
    
    print("📱 АВТОРИЗАЦИЯ ЮЗЕР-БОТА")
    print("=" * 40)
    
    # Запрашиваем номер телефона
    phone = input("Введите номер телефона (формат: +79123456789): ").strip()
    
    # Инициализируем клиента
    client = TelegramClient('user_session', API_ID, API_HASH)
    await client.connect()
    
    try:
        # Отправляем код
        sent_code = await client.send_code_request(phone)
        print(f"✅ Код отправлен на {phone}")
        
        # Запрашиваем код
        code = input("Введите код из Telegram (5 цифр): ").strip()
        
        try:
            # Пытаемся войти с кодом
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=sent_code.phone_code_hash
            )
        except SessionPasswordNeededError:
            # Если нужен пароль 2FA
            password = input("Введите пароль двухэтапной аутентификации: ")
            await client.sign_in(password=password)
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        user_info = {
            'id': me.id,
            'first_name': me.first_name,
            'last_name': me.last_name or '',
            'username': me.username or ''
        }
        
        print("=" * 40)
        print(f"✅ АВТОРИЗАЦИЯ УСПЕШНАЯ!")
        print(f"👤 Пользователь: {user_info['first_name']} {user_info['last_name']}")
        print(f"📎 Юзернейм: @{user_info['username']}")
        print(f"🆔 ID: {user_info['id']}")
        print("=" * 40)
        print("🤖 Юзер-бот готов к работе!")
        print("💬 Напишите .старт в любом чате чтобы активировать бота")
        print("⛔ .стоп — чтобы отключить бота в чате")
        print("=" * 40)
        
        return True
        
    except PhoneCodeInvalidError:
        print("❌ Неверный код")
        return False
    except Exception as e:
        print(f"❌ Ошибка авторизации: {e}")
        return False

# ==================== ЗАПУСК ====================
async def main():
    """Основная функция запуска"""
    print("🚀 ЗАПУСК AI ЮЗЕР-БОТА")
    print("=" * 40)
    print("🤖 Бот: 16-летняя девушка (грубая + флирт)")
    print("💬 AI: DeepSeek API")
    print("=" * 40)
    
    # Авторизация
    success = await auth_user()
    if not success:
        print("❌ Не удалось авторизоваться")
        return
    
    # Запускаем клиента
    await client.run_until_disconnected()

# ==================== ЗАЩИТА ОТ СЛУЧАЙНОГО ЗАПУСКА ====================
if __name__ == "__main__":
    # Проверяем, что это не импорт
    import sys
    if sys.argv[0].endswith('bot.py'):
        asyncio.run(main())
