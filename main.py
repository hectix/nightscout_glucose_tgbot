import telebot
import requests
import hashlib
import os
import json
from dotenv import load_dotenv
from telebot import types
from datetime import datetime, timezone, timedelta

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NIGHTSCOUT_URL = os.getenv("NIGHTSCOUT_URL").rstrip("/")
API_SECRET = os.getenv("NIGHTSCOUT_SECRET")
API_SECRET_HASH = hashlib.sha1(API_SECRET.encode()).hexdigest()

bot = telebot.TeleBot(TELEGRAM_TOKEN)

AUTHORIZED_USERS = list(map(int, os.getenv("AUTHORIZED_USERS", "").split(',')))
NOTIFY_CHAT_ID = int(os.getenv("NOTIFY_CHAT_ID", "0"))
INSULIN_LOG_FILE = 'insulin_log.json'
INSULIN_ACTION_DURATION_HOURS = 4.5  # NovoRapid

def check_authorization(user_id):
    return user_id in AUTHORIZED_USERS

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_ins_05 = types.KeyboardButton("💉 0,5 единиц, короткий")
    btn_ins_1 = types.KeyboardButton("💉 1 единица, короткий")
    btn_ins_15 = types.KeyboardButton("💉 1,5 единицы, короткий")
    btn1 = types.KeyboardButton("📊 Уровень глюкозы")
    btn2 = types.KeyboardButton("📈 История глюкозы")
    btn_update = types.KeyboardButton("🔁 Обновить меню")
    markup.add(btn_ins_05, btn_ins_1, btn_ins_15)
    markup.add(btn1, btn2)
    markup.add(btn_update)
    return markup

def insulin_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("💉 0,5 единиц, короткий")
    btn2 = types.KeyboardButton("💉 1 единица, короткий")
    btn3 = types.KeyboardButton("💉 1,5 единицы, короткий")
    markup.add(btn1, btn2)
    markup.add(btn3)
    return markup

def log_insulin(dose, timestamp):
    entry = {"timestamp": timestamp, "dose": dose}
    if os.path.exists(INSULIN_LOG_FILE):
        with open(INSULIN_LOG_FILE, 'r', encoding='utf-8') as f:
            log = json.load(f)
    else:
        log = []
    log.append(entry)
    with open(INSULIN_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False)

def calculate_iob(action_time_hours: float = INSULIN_ACTION_DURATION_HOURS) -> float:
    if not os.path.exists(INSULIN_LOG_FILE):
        return 0.0
    now = datetime.now().timestamp()
    action_time_sec = action_time_hours * 3600
    with open(INSULIN_LOG_FILE, 'r', encoding='utf-8') as f:
        entries = json.load(f)
    iob = 0.0
    for entry in entries:
        time_passed = now - entry["timestamp"]
        if 0 <= time_passed < action_time_sec:
            remaining = 1 - (time_passed / action_time_sec)
            iob += entry["dose"] * remaining
    return round(iob, 2)

@bot.message_handler(commands=['start'])
def start_handler(message):
    if not check_authorization(message.chat.id):
        bot.send_message(message.chat.id, "Вы не авторизованы для использования этого бота.")
        return
    bot.send_message(
        message.chat.id,
        "Привет! Выбери действие:",
        reply_markup=main_menu()
    )

@bot.message_handler(func=lambda m: m.text == "🔁 Обновить меню")
def update_menu(message):
    if not check_authorization(message.chat.id):
        bot.send_message(message.chat.id, "Вы не авторизованы для использования этого бота.")
        return
    bot.send_message(
        message.chat.id,
        "Меню обновлено ✅",
        reply_markup=main_menu()
    )

@bot.message_handler(func=lambda m: m.text == "📊 Уровень глюкозы")
def current_glucose(message):
    if not check_authorization(message.chat.id):
        bot.send_message(message.chat.id, "Вы не авторизованы для использования этого бота.")
        return
    try:
        headers = {"API-SECRET": API_SECRET_HASH}
        url = f'{NIGHTSCOUT_URL}/api/v1/entries.json?count=1'
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()[0]
        sgv_mgdl = data['sgv']
        sgv_mmol = round(sgv_mgdl / 18.0, 1)
        direction = data['direction']
        utc_time = datetime.strptime(data['dateString'], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        local_time = utc_time.astimezone(timezone(timedelta(hours=3)))
        time_str = local_time.strftime('%H:%M')
        iob = calculate_iob()
        msg = (
            f"🩸 Уровень глюкозы: {sgv_mmol} ммоль/л ({sgv_mgdl} мг/дл)\n"
            f"📈 Направление: {direction}\n"
            f"🕒 Время: {time_str}\n"
            f"💉 Активный инсулин: {iob} ЕД"
        )
        bot.send_message(message.chat.id, msg)
    except Exception as e:
        print(f"[ERROR] {e}")
        bot.send_message(message.chat.id, "Ошибка при получении данных 😔")

@bot.message_handler(func=lambda m: m.text == "📈 История глюкозы")
def glucose_history(message):
    if not check_authorization(message.chat.id):
        bot.send_message(message.chat.id, "Вы не авторизованы для использования этого бота.")
        return
    try:
        headers = {"API-SECRET": API_SECRET_HASH}
        url = f'{NIGHTSCOUT_URL}/api/v1/entries.json?count=10'
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        msg = "📈 Последние значения глюкозы:\n"
        for entry in data:
            mmol = round(entry['sgv'] / 18.0, 1)
            utc_time = datetime.strptime(entry['dateString'], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
            local_time = utc_time.astimezone(timezone(timedelta(hours=3)))
            time = local_time.strftime('%H:%M')
            msg += f"— {mmol} ммоль/л ({entry['sgv']} мг/дл) в {time}\n"
        bot.send_message(message.chat.id, msg)
    except Exception as e:
        print(f"[ERROR] {e}")
        bot.send_message(message.chat.id, "Ошибка при получении истории 😔")

@bot.message_handler(func=lambda m: m.text in ["💉 0,5 единиц, короткий", "💉 1 единица, короткий", "💉 1,5 единицы, короткий"])
def insulin_given(message):
    if not check_authorization(message.chat.id):
        bot.send_message(message.chat.id, "Вы не авторизованы для использования этого бота.")
        return
    insulin_dose = 0.5 if message.text == "💉 0,5 единиц, короткий" else 1.0 if message.text == "💉 1 единица, короткий" else 1.5
    try:
        headers = {"API-SECRET": API_SECRET_HASH}
        url = f'{NIGHTSCOUT_URL}/api/v1/treatments.json'
        timestamp = int(message.date)
        payload = {
            "eventType": "Bolus",
            "subeventType": "Normal",
            "insulin": insulin_dose,
            "datetime": timestamp * 1000
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        user = message.from_user.username or message.from_user.first_name or "Неизвестный пользователь"
        time_formatted = datetime.fromtimestamp(timestamp).astimezone(timezone(timedelta(hours=3))).strftime('%H:%M')
        bot.send_message(
            NOTIFY_CHAT_ID,
            f"Введено {insulin_dose} инсулина в {time_formatted} пользователем @{user}"
        )
        bot.send_message(
            message.chat.id,
            f"💉 Введено {insulin_dose} единиц инсулина."
        )
        log_insulin(insulin_dose, timestamp)
    except Exception as e:
        print(f"[ERROR] {e}")
        bot.send_message(message.chat.id, "Ошибка при записи введения инсулина 😔")

bot.polling()
