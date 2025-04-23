import telebot
import os
from dotenv import load_dotenv


load_dotenv()

# Твой Telegram токен
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Получаем все обновления
updates = bot.get_updates()

# Выводим обновления
for update in updates:
    print(update.message.chat.id, update.message.text)
