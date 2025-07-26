import logging
import requests
import time
import os
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
import asyncio
import aiohttp
from datetime import datetime
import pytz
import signal
import sys

# ... (импорты в начале)
from flask import Flask, jsonify
import threading

app = Flask(__name__)

@app.route('/health')
def health_check():
    return jsonify(status="ok"), 200

def run_flask():
    from waitress import serve  # Добавляем production-ready сервер
    logging.basicConfig(level=logging.INFO)
    serve(app, host='0.0.0.0', port=8080)

# ... (остальной код)

def get_avito_messages(token, last_timestamp):
    url = f'https://api.avito.ru/messenger/v1/accounts/{AVITO_USER_ID}/chats'  # v3 → v1
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.avito.messenger+json; version=1'
    }
    # ... (остальной код)

def get_avito_chat_history(token, chat_id):
    url = f'https://api.avito.ru/messenger/v1/accounts/{AVITO_USER_ID}/chats/{chat_id}/messages'  # v3 → v1
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.avito.messenger+json; version=1'
    }
    
    full_history = []
    page = 1
    per_page = 50
    
    while True:
        params = {'page': page, 'per_page': per_page}
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code != 200:
                logging.error(f"Ошибка API Авито: {response.status_code} - {response.text}")
                break
                
            data = response.json()
            messages = data.get('data', {}).get('messages', [])
            if not messages:
                break
                
            for msg in messages:
                # ... (обработка сообщения)
                full_history.append({...})
                
            if len(messages) < per_page:
                break
                
            page += 1
        except Exception as e:
            logging.error(f"Ошибка: {e}")
            break
            
    return full_history

async def main() -> None:
    # Запуск Flask сервера
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # ... (остальной код)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Конфигурация из переменных окружения
AVITO_CLIENT_ID = os.getenv('AVITO_CLIENT_ID')
AVITO_CLIENT_SECRET = os.getenv('AVITO_CLIENT_SECRET')
AVITO_USER_ID = os.getenv('AVITO_USER_ID')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Проверка наличия переменных
if not all([AVITO_CLIENT_ID, AVITO_CLIENT_SECRET, AVITO_USER_ID, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    logging.error("Не все переменные окружения заданы")
    exit(1)

# Хранилище для уникальных сообщений
processed_messages = set()

# Функция для отправки сообщений в Telegram
async def send_to_telegram(bot, message_data, is_system=False):
    try:
        if is_system:
            text = f"Системное уведомление: {message_data['text']}"
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
            logging.info(f"Системное сообщение отправлено: {text}")
            return
        
        moscow_tz = pytz.timezone('Europe/Moscow')
        message_time = datetime.fromtimestamp(message_data['timestamp'], moscow_tz)
        formatted_time = message_time.strftime('%H:%M')
        user_id = message_data.get('user_id', 'unknown')
        public_key = message_data.get('public_key', 'unknown')
        item_id = message_data.get('item_id', 'unknown')
        message_id = message_data.get('message_id', 'unknown')
        logging.info(f"Формирование сообщения: user_id={user_id}, public_key={public_key}, item_id={item_id}, message_id={message_id}")
        
        if message_id in processed_messages:
            logging.info(f"Сообщение {message_id} уже обработано, пропускаем")
            return
        
        processed_messages.add(message_id)
        
        user_link = f"<a href=\"https://www.avito.ru/brands/i121955125\">{message_data['sender']}</a>"
        item_link = f"<a href=\"https://www.avito.ru/{item_id}\">{message_data['item_title']}</a>" if item_id != 'unknown' and item_id.isdigit() else message_data['item_title']
        text = (
            f"Получено сообщение:\n"
            f"Аккаунт: Мой ноутбук\n"
            f"👤 Покупатель: {user_link}\n"
            f"📌 Объявление: {item_link}\n"
            f"💬 Сообщение: «{message_data['text']}»\n"
            f"🕒 Время: {formatted_time} (по Москве)"
        )
        
        keyboard = [
            [InlineKeyboardButton("Ответить", callback_data=f"reply_{message_data['chat_id']}")],
            [InlineKeyboardButton("История переписки", callback_data=f"history_{message_data['chat_id']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        logging.info(f"Сообщение отправлено в Telegram: {text}")
    except Exception as e:
        logging.error(f"Ошибка отправки в Telegram: {e}")

# Получение токена Авито
def get_avito_token():
    url = 'https://api.avito.ru/token'
    data = {
        'grant_type': 'client_credentials',
        'client_id': AVITO_CLIENT_ID,
        'client_secret': AVITO_CLIENT_SECRET,
        'scope': 'messenger'
    }
    try:
        response = requests.post(url, data=data, timeout=30)
        response.raise_for_status()
        token_data = response.json()
        logging.info(f"Токен Авито получен: {token_data.get('access_token')[:10]}...")
        return token_data.get('access_token')
    except Exception as e:
        logging.error(f"Ошибка получения токена Авито: {e}")
        return None

# Получение новых сообщений с Авито
def get_avito_messages(token, last_timestamp):
    url = f'https://api.avito.ru/messenger/v2/accounts/{AVITO_USER_ID}/chats'
    headers = {'Authorization': f'Bearer {token}'}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        logging.info("Ответ API Авито: " + response.text[:100])
        data = response.json()
        chats = data.get('chats', [])
        new_messages = []

        for chat in chats:
            last_message = chat.get('last_message', {})
            message_time = last_message.get('created', 0)
            message_id = str(last_message.get('id', 'unknown'))
            if message_time > last_timestamp and last_message.get('direction') == 'in' and message_id not in processed_messages:
                sender = next((user['name'] for user in chat['users'] if user['id'] != int(AVITO_USER_ID)), 'Неизвестный')
                user_id = next((str(user['id']) for user in chat['users'] if user['id'] != int(AVITO_USER_ID)), 'unknown')
                public_key = next((user.get('public_key', 'unknown') for user in chat['users'] if user['id'] != int(AVITO_USER_ID)), 'unknown')
                message_text = last_message.get('content', {}).get('text', '')
                chat_id = chat.get('id', '')
                item_title = chat.get('context', {}).get('value', {}).get('title', 'Неизвестное объявление')
                item_id = str(chat.get('context', {}).get('value', {}).get('id', 'unknown'))
                new_messages.append({
                    'chat_id': chat_id,
                    'sender': sender,
                    'user_id': user_id,
                    'public_key': public_key,
                    'text': message_text,
                    'timestamp': message_time,
                    'item_title': item_title,
                    'item_id': item_id,
                    'message_id': message_id
                })
        logging.info("Сообщения успешно получены")
        return new_messages, max([msg['timestamp'] for msg in new_messages] + [last_timestamp])
    except Exception as e:
        logging.error(f"Ошибка получения сообщений с Авито: {e}")
        return [], last_timestamp

# Получение истории сообщений в чате Авито
def get_avito_chat_history(token, chat_id):
    url = f'https://api.avito.ru/messenger/v3/accounts/{AVITO_USER_ID}/chats/{chat_id}/messages'
    headers = {'Authorization': f'Bearer {token}'}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            logging.info(f"История сообщений получена для чата {chat_id}: " + response.text[:100])
            data = response.json()
            messages = data.get('messages', [])
            history = []
            moscow_tz = pytz.timezone('Europe/Moscow')
            for msg in messages:
                sender_id = msg.get('user_id', 'unknown')
                sender = 'Вы' if sender_id == int(AVITO_USER_ID) else next((user['name'] for user in msg.get('users', []) if user['id'] == sender_id), 'Неизвестный')
                message_time = datetime.fromtimestamp(msg.get('created', 0), moscow_tz).strftime('%H:%M %d.%m.%Y')
                text = msg.get('content', {}).get('text', '')
                history.append({
                    'time': message_time,
                    'sender': sender,
                    'text': text
                })
            return history
        else:
            logging.error(f"Ошибка API Авито: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logging.error(f"Исключение при получении истории чата {chat_id}: {e}")
        return None

# Отправка ответа на Авито
async def send_avito_message(token, chat_id, message):
    url = f'https://api.avito.ru/messenger/v1/accounts/{AVITO_USER_ID}/chats/{chat_id}/messages'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'Accept': 'application/vnd.avito.messenger+json; version=1'
    }
    # Исправленный формат данных согласно документации Avito
    data = {
        "content": {
            "type": "text",
            "text": message
        }
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    logging.info(f"Ответ успешно отправлен в чат {chat_id}: {message}")
                    return True
                else:
                    # Добавляем вывод тела ответа для диагностики
                    error_text = await response.text()
                    logging.error(f"Ошибка API Авито ({response.status}): {error_text}")
                    return False
    except Exception as e:
        logging.error(f"Исключение при отправке сообщения на Авито: {e}")
        return False

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Бот запущен! Ожидаю сообщений с Авито.')
    logging.info("Команда /start выполнена")

async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        args = context.args
        logging.info(f"Команда /reply получена: args={args}")
        
        if len(args) < 2:
            await update.message.reply_text('Использование: /reply <chat_id> <сообщение>')
            logging.warning("Недостаточно аргументов для команды /reply")
            return
        
        chat_id = args[0]
        message = ' '.join(args[1:])
        logging.info(f"Попытка отправить в чат {chat_id}: {message}")
        
        token = get_avito_token()
        if token:
            success = await send_avito_message(token, chat_id, message)
            if success:
                await update.message.reply_text(f'✅ Ответ отправлен в чат {chat_id}')
                logging.info(f"Ответ успешно отправлен на Avito")
            else:
                await update.message.reply_text('❌ Ошибка при отправке ответа на Авито. Проверьте лог.')
                logging.error("Не удалось отправить ответ через API Avito")
        else:
            await update.message.reply_text('⚠️ Не удалось получить токен Авито.')
            logging.error("Токен Avito не получен")
    except Exception as e:
        logging.exception(f"Критическая ошибка в команде /reply: {e}")
        await update.message.reply_text(f'🚨 Ошибка: {str(e)}')

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text('Использование: /history <chat_id>')
            return
        chat_id = args[0]
        token = get_avito_token()
        if token:
            history_messages = get_avito_chat_history(token, chat_id)
            if history_messages:
                history_text = f"История общения в чате {chat_id}:\n"
                for msg in history_messages:
                    history_text += f"🕒 {msg['time']} | От: {msg['sender']} | Сообщение: {msg['text']}\n"
                await update.message.reply_text(history_text)
            else:
                await update.message.reply_text(f'Нет сообщений в чате {chat_id} или произошла ошибка.')
        else:
            await update.message.reply_text('Не удалось получить токен Авито.')
    except Exception as e:
        logging.error(f"Ошибка в команде /history: {e}")
        await update.message.reply_text(f'Ошибка: {e}')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = data.split('_')[1]
    
    if data.startswith('reply_'):
        logging.info(f"Кнопка 'Ответить' нажата для чата {chat_id}")
        await query.message.reply_text(
            f'Введите ответ для чата {chat_id} с помощью команды:\n'
            f'/reply {chat_id} <ваше сообщение>'
        )
    elif data.startswith('history_'):
        logging.info(f"Кнопка 'История переписки' нажата для чата {chat_id}")
        token = get_avito_token()
        if token:
            history_messages = get_avito_chat_history(token, chat_id)
            if history_messages:
                history_text = f"История общения в чате {chat_id}:\n"
                for msg in history_messages:
                    history_text += f"🕒 {msg['time']} | От: {msg['sender']} | Сообщение: {msg['text']}\n"
                await query.message.reply_text(history_text)
            else:
                await query.message.reply_text(f'Нет сообщений в чате {chat_id} или произошла ошибка.')
        else:
            await query.message.reply_text('Не удалось получить токен Авито.')

# Обработка сигналов завершения
def handle_exit(signum, frame):
    logging.info("Получен сигнал завершения")
    sys.exit(0)

# Основная функция
async def main() -> None:
    # Создаем Application вместо Updater
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    bot = application.bot
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reply", reply))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CallbackQueryHandler(button_callback, pattern='^(reply_|history_)'))
    
    # Запускаем polling в фоне
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    logging.info("Бот Telegram запущен в режиме polling")
    
    # Основной цикл проверки сообщений Авито
    last_timestamp = int(time.time()) - 3600
    token_error_count = 0
    
    while True:
        token = get_avito_token()
        if token:
            token_error_count = 0
            new_messages, last_timestamp = get_avito_messages(token, last_timestamp)
            for msg in new_messages:
                await send_to_telegram(bot, msg)
        else:
            token_error_count += 1
            if token_error_count <= 3:
                await send_to_telegram(bot, {
                    'text': 'Ошибка: Не удалось получить токен Авито',
                    'timestamp': int(time.time())
                }, is_system=True)
        await asyncio.sleep(60)

if __name__ == '__main__':
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"Общая ошибка: {e}")
        # Создаем временного бота для отправки сообщения об ошибке
        bot = Bot(token=TELEGRAM_TOKEN)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_to_telegram(bot, {
            'text': f'Критическая ошибка бота: {e}',
            'timestamp': int(time.time())
        }, is_system=True))
        loop.close()
