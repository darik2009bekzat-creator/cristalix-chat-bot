import os
import re
import tempfile
import requests
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

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
# HTTP-СЕРВЕР ДЛЯ RENDER
# =========================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )
        self.end_headers()
        self.wfile.write(b"Bot is running!")

    def log_message(self, format, *args):
        return


def start_web_server():
    port = int(os.environ.get("PORT", "10000"))

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    print(f"WEB SERVER STARTED ON PORT {port}")

    server.serve_forever()


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
                headers={
                    "apikey": OCR_KEY
                },
                files={
                    "file": image
                },
                data={
                    "language": "rus",
                    "isOverlayRequired": "false",
                    "OCREngine": "2",
                },
                timeout=60,
            )

        print("OCR STATUS:", response.status_code)

        data = response.json()

        print("OCR RESPONSE:",
              str(data)[:2000])

        if data.get("IsErroredOnProcessing"):
            print(
                "OCR PROCESSING ERROR:",
                data.get("ErrorMessage")
            )
            return ""

        results = data.get(
            "ParsedResults",
            []
        )

        text = "\n".join(
            item.get(
                "ParsedText",
                ""
            )
            for item in results
        )

        return text.strip()

    except Exception as e:

        print(
            "OCR ERROR:",
            repr(e)
        )

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

        # Основной вариант Cristalix
        separators = [
            "»",
            ">",
            "» ",
            ":",
        ]

        found = False

        for separator in separators:

            if separator not in line:
                continue

            parts = line.split(
                separator,
                1
            )

            if len(parts) != 2:
                continue

            player = parts[0].strip()
            message = parts[1].strip()

            player = re.sub(
                r"^[^\wА-Яа-яЁё_-]*",
                "",
                player
            )

            if player and message:

                messages.append(
                    (
                        player,
                        message
                    )
                )

                found = True
                break

        if found:
            continue

    return messages


# =========================
# ПРОВЕРКА ПРАВИЛ
# =========================

def check_message(
    player,
    message
):

    text = message.lower()

    violations = []

    # 2.7 — мат
    for word in BAD_WORDS:

        if word in text:

            violations.append(
                (
                    "2.7",
                    RULES["2.7"]
                )
            )

            break

    # 2.4 — дискриминация
    for word in DISCRIMINATION:

        if word in text:

            violations.append(
                (
                    "2.4",
                    RULES["2.4"]
                )
            )

            break

    # 2.1 — выдача себя за персонал
    if any(
        word in text
        for word in STAFF_WORDS
    ):

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

        if any(
            phrase in text
            for phrase in phrases
        ):

            violations.append(
                (
                    "2.1",
                    RULES["2.1"]
                )
            )

    # 2.8 — оскорбления
    if any(
        word in text
        for word in TOXIC_WORDS
    ):

        violations.append(
            (
                "2.8",
                RULES["2.8"]
            )
        )

    # 2.12 — капс
    letters = [
        c
        for c in message
        if c.isalpha()
    ]

    if len(letters) >= 6:

        upper = sum(
            1
            for c in letters
            if c.isupper()
        )

        if (
            upper >= 6
            or upper / len(letters) >= 0.5
        ):

            violations.append(
                (
                    "2.12",
                    RULES["2.12"]
                )
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

    if any(
        word in text
        for word in immoral
    ):

        violations.append(
            (
                "2.13",
                RULES["2.13"]
            )
        )

    # 2.15 — реклама
    if any(
        word in text
        for word in AD_WORDS
    ):

        violations.append(
            (
                "2.15",
                RULES["2.15"]
            )
        )

    # Другой сервер
    for server in OTHER_SERVERS:

        if server in text:

            violations.append(
                (
                    "2.15",
                    RULES["2.15"]
                )
            )

            break

    return violations


# =========================
# АНАЛИЗ ФОТО
# =========================

async def analyze_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "📥 Фото получено.\n"
        "🔎 Начинаю обработку..."
    )

    try:

        photo = update.message.photo[-1]

        await update.message.reply_text(
            "📥 Скачиваю изображение..."
        )

        file = await context.bot.get_file(
            photo.file_id
        )

        filename = tempfile.mktemp(
            suffix=".jpg"
        )

        await file.download_to_drive(
            filename
        )

        await update.message.reply_text(
            "🔎 Отправляю изображение в OCR..."
        )

        text = recognize_image(
            filename
        )

        try:
            os.remove(filename)
        except Exception:
            pass

        print("OCR TEXT:")
        print(repr(text))

        if not text:

            await update.message.reply_text(
                "❌ OCR не смог распознать текст.\n\n"
                "Проверь Logs Render — там будет "
                "причина ошибки OCR."
            )

            return

        # Показываем распознанный текст
        await update.message.reply_text(
            "✅ OCR текст получен!\n\n"
            + text[:3500]
        )

        messages = extract_messages(
            text
        )

        if not messages:

            await update.message.reply_text(
                "⚠️ Текст распознан, "
                "но формат сообщений не найден.\n\n"
                "Теперь мы видим сам текст OCR "
                "и сможем подстроить распознавание."
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
                f"👤 Нарушитель: "
                f"{result['player']}\n"
                f"📕 Правило: "
                f"{result['rule']}\n"
                f"⚠️ Нарушение: "
                f"{result['description']}\n"
                f"💬 Сообщение: "
                f"«{result['message']}»\n\n"
            )

        await update.message.reply_text(
            answer[:4000]
        )

    except Exception as e:

        print(
            "PHOTO ERROR:",
            repr(e)
        )

        await update.message.reply_text(
            "❌ Ошибка при обработке фото:\n\n"
            + str(e)[:1500]
        )


# =========================
# КОМАНДЫ
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Отправь мне скриншот Minecraft-чата, "
        "и я попробую определить нарушителя "
        "и пункт правил Cristalix."
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "📸 Просто отправь скриншот "
        "Minecraft-чата.\n\n"
        "Я распознаю сообщения и проверю "
        "их по правилам чата."
    )


# =========================
# ЗАПУСК БОТА
# =========================

async def run_bot():

    if not BOT_TOKEN:

        raise RuntimeError(
            "Не найден BOT_TOKEN"
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_command
        )
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


# =========================
# MAIN
# =========================

def main():

    web_thread = threading.Thread(
        target=start_web_server,
        daemon=True
    )

    web_thread.start()

    asyncio.run(
        run_bot()
    )


if __name__ == "__main__":
    main()

