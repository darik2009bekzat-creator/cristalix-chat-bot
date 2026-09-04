import os
import re
import tempfile
import requests
import asyncio

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# НАСТРОЙКИ
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
OCR_KEY = os.getenv("OCR_KEY", "helloworld")

OCR_URL = "https://api.ocr.space/parse/image"


# =========================
# ПРАВИЛА CRISTALIX
# =========================

RULES = {
    "2.1": "Выдача себя за модерацию или администрацию",
    "2.4": "Дискриминация",
    "2.5": "Пропаганда запрещённых явлений",
    "2.7": "Нецензурная или чрезмерно грубая лексика",
    "2.8": "Оскорбление, нахальное поведение или угрозы",
    "2.10": "Флуд",
    "2.11": "Организация массового флуда",
    "2.12": "Сообщение написано капсом",
    "2.13": "Неадекватное или аморальное поведение",
    "2.14": "Чрезмерно токсичное поведение",
    "2.15": "Реклама сторонних ресурсов или других серверов",
}


# =========================
# СЛОВАРИ
# =========================

BAD_WORDS = [
    "бля",
    "блять",
    "блядь",
    "сука",
    "ебать",
    "ебан",
    "нахуй",
    "пизд",
    "хуй",
    "хуйн",
    "fuck",
    "shit",
]

DISCRIMINATION = [
    "нигер",
    "негр",
    "чурка",
    "хач",
    "хохол",
    "москаль",
    "жид",
    "пендос",
    "русня",
]

TOXIC_WORDS = [
    "нуб",
    "изи",
    "easy",
    "лох",
    "дебил",
    "идиот",
]

STAFF_WORDS = [
    "админ",
    "администратор",
    "модер",
    "модератор",
    "хелпер",
    "helper",
    "owner",
    "овнер",
]

AD_WORDS = [
    "discord.gg/",
    "t.me/",
    "vk.com/",
    "youtube.com/",
    "youtu.be/",
    "telegram.me/",
]

OTHER_SERVERS = [
    "hypixel",
    "mineplex",
]


# =========================
# OCR
# =========================

def recognize_image(filename):
    try:
        with open(filename, "rb") as image:
            response = requests.post(
                OCR_URL,
                headers={"apikey": OCR_KEY},
                files={"file": image},
                data={
                    "language": "rus",
                    "isOverlayRequired": "false",
                    "OCREngine": "2",
                },
                timeout=60,
            )

        data = response.json()

        if data.get("IsErroredOnProcessing"):
            return ""

        results = data.get("ParsedResults", [])

        text = "\n".join(
            item.get("ParsedText", "")
            for item in results
        )

        return text.strip()

    except Exception as e:
        print("OCR ERROR:", e)
        return ""


# =========================
# РАЗБОР СООБЩЕНИЙ
# =========================

def extract_messages(text):
    messages = []

    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        if "»" in line:
            parts = line.split("»", 1)

            player = parts[0].strip()
            message = parts[1].strip()

            player = re.sub(
                r"^[^\wА-Яа-яЁё_-]*",
                "",
                player
            )

            if player and message:
                messages.append((player, message))

    return messages


# =========================
# ПРОВЕРКА ПРАВИЛ
# =========================

def check_message(player, message):
    text = message.lower()
    violations = []

    # 2.7 — мат
    for word in BAD_WORDS:
        if word in text:
            violations.append(
                ("2.7", "Нецензурная или чрезмерно грубая лексика")
            )
            break

    # 2.4 — дискриминация
    for word in DISCRIMINATION:
        if word in text:
            violations.append(
                ("2.4", "Дискриминация")
            )
            break

    # 2.1 — выдача себя за персонал
    if any(word in text for word in STAFF_WORDS):
        phrases = [
            "я админ",
            "я модер",
            "я модератор",
            "я хелпер",
            "я овнер",
            "я администратор",
            "я owner",
            "я helper",
        ]

        if any(phrase in text for phrase in phrases):
            violations.append(
                ("2.1", "Выдача себя за модерацию или администрацию")
            )

    # 2.8 — оскорбления
    if any(word in text for word in TOXIC_WORDS):
        violations.append(
            ("2.8", "Оскорбление или нахальное поведение")
        )

    # 2.12 — капс
    letters = [c for c in message if c.isalpha()]

    if len(letters) >= 6:
        upper = sum(1 for c in letters if c.isupper())

        if upper >= 6 or upper / len(letters) >= 0.5:
            violations.append(
                ("2.12", "Сообщение написано капсом")
            )

    # 2.13 — аморальное содержание
    immoral = [
        "порно",
        "проститут",
        "сперма",
        "дилдо",
        "дроч",
        "минет",
        "шлюха",
    ]

    if any(word in text for word in immoral):
        violations.append(
            ("2.13", "Неадекватное или аморальное поведение")
        )

    # 2.15 — реклама
    if any(word in text for word in AD_WORDS):
        violations.append(
            ("2.15", "Реклама сторонних ресурсов или других серверов")
        )

    # Упоминание другого сервера
    for server in OTHER_SERVERS:
        if server in text:
            violations.append(
                ("2.15", "Упоминание стороннего сервера")
            )
            break

    return violations


# =========================
# АНАЛИЗ ФОТО
# =========================

async def analyze_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🔎 Анализирую скриншот..."
    )

    photo = update.message.photo[-1]

    file = await context.bot.get_file(photo.file_id)

    filename = tempfile.mktemp(
        suffix=".jpg"
    )

    await file.download_to_drive(filename)

    text = recognize_image(filename)

    try:
        os.remove(filename)
    except Exception:
        pass

    if not text:
        await update.message.reply_text(
            "❌ Не удалось распознать текст на скриншоте."
        )
        return

    print("OCR TEXT:")
    print(text)

    messages = extract_messages(text)

    if not messages:
        await update.message.reply_text(
            "⚠️ Не удалось определить формат сообщений Minecraft-чата."
        )
        return

    results = []

    for player, message in messages:
        violations = check_message(
            player,
            message
        )

        for rule, description in violations:
            results.append(
                {
                    "player": player,
                    "rule": rule,
                    "description": description,
                    "message": message,
                }
            )

    if not results:
        await update.message.reply_text(
            "✅ Явных нарушений не обнаружено."
        )
        return

    answer = "🔎 АНАЛИЗ ЧАТА\n\n"

    for result in results:
        answer += (
            f"👤 Нарушитель: {result['player']}\n"
            f"📕 Правило: {result['rule']}\n"
            f"⚠️ Нарушение: {result['description']}\n"
            f"💬 Сообщение: «{result['message']}»\n\n"
        )

    await update.message.reply_text(answer)


# =========================
# КОМАНДЫ
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Отправь мне скриншот Minecraft-чата, "
        "и я попробую определить нарушителя "
        "и пункт правил Cristalix."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "📸 Просто отправь скриншот Minecraft-чата.\n\n"
        "Я распознаю сообщения и проверю их "
        "по правилам чата."
    )


# =========================
# ЗАПУСК
# =========================

async def main():

    if not BOT_TOKEN:
        raise RuntimeError("Не найден BOT_TOKEN")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            analyze_photo
        )
    )

    print("BOT STARTED")

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    try:
        await asyncio.Event().wait()
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
