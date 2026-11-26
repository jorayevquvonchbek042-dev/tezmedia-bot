import os
import re
import json
import time
import threading
from flask import Flask
import telebot
from telebot import types
import yt_dlp

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@tezmedia_rasmiy")
WEB_APP_URL = "https://jorayevquvonchbek042-dev.github.io/tezmedia-panel/"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)


@app.route("/")
def home():
    return "TezMedia Bot is running!"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


def get_panel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn = types.KeyboardButton(
        text="⚡ TEZMEDIA AI PANEL",
        web_app=types.WebAppInfo(WEB_APP_URL),
    )
    markup.add(btn)
    return markup


def is_subscribed(user_id):
    if not CHANNEL_ID:
        return True
    try:
        status = bot.get_chat_member(CHANNEL_ID, user_id).status
        return status in ["member", "administrator", "creator"]
    except Exception:
        return True


def download_youtube_song(query):
    os.makedirs("downloads", exist_ok=True)
    timestamp = int(time.time())

    search_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "default_search": "ytsearch3",
        "extractor_args": {"youtube": {"player_client": ["android", "ios"]}},
    }

    selected_url = None
    song_title = query

    with yt_dlp.YoutubeDL(search_opts) as ydl:
        info = ydl.extract_info(f"{query} official audio", download=False)
        entries = info.get("entries") or []

        for entry in entries:
            if not entry:
                continue
            url = entry.get("url") or entry.get("webpage_url") or ""
            duration = entry.get("duration") or 0

            if "/shorts/" in url or duration < 60 or duration > 900:
                continue

            selected_url = (
                url
                if url.startswith("http")
                else f"https://www.youtube.com/watch?v={entry.get('id')}"
            )
            song_title = entry.get("title") or query
            break

    if not selected_url:
        return None, None

    out_template = f"downloads/song_{timestamp}.%(ext)s"
    dl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": out_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": ["android", "ios"]}},
    }

    with yt_dlp.YoutubeDL(dl_opts) as ydl:
        dl_info = ydl.extract_info(selected_url, download=True)
        file_path = ydl.prepare_filename(dl_info)
        song_title = dl_info.get("title") or song_title
        return file_path, song_title


def download_media_link(url, audio_only=False):
    os.makedirs("downloads", exist_ok=True)
    timestamp = int(time.time())
    out_template = f"downloads/media_{timestamp}.%(ext)s"

    fmt = (
        "bestaudio[ext=m4a]/bestaudio/best"
        if audio_only
        else "best[ext=mp4][filesize<48M]/best[ext=mp4]/best"
    )

    ydl_opts = {
        "format": fmt,
        "outtmpl": out_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": ["android", "ios"]}},
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info), info.get("title", "TezMedia")


def process_request(chat_id, user_id, query_text, force_audio=False):
    if not is_subscribed(user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                "📢 Kanalga obuna bo‘lish", url="https://t.me/tezmedia_rasmiy"
            )
        )
        bot.send_message(
            chat_id,
            "Botdan foydalanish uchun avval **Trend & Media** kanaliga obuna bo‘ling:",
            reply_markup=markup,
            parse_mode="Markdown",
        )
        return

    text = (query_text or "").strip()
    if not text:
        return

    # Agar havola yuborilgan bo'lsa
    if re.match(r"^https?://", text):
        wait_text = (
            "🎵 Havoladan MP3 ajratib olinmoqda..."
            if force_audio
            else "⏳ Video yuklanmoqda..."
        )
        wait_msg = bot.send_message(chat_id, wait_text)
        file_path = None
        try:
            file_path, title = download_media_link(text, audio_only=force_audio)
            if not file_path or not os.path.exists(file_path):
                bot.edit_message_text(
                    "❌ Yuklab bo‘lmadi. Havolani tekshirib qayta yuboring.",
                    chat_id,
                    wait_msg.message_id,
                )
                return

            with open(file_path, "rb") as media_file:
                if force_audio:
                    bot.send_audio(
                        chat_id,
                        media_file,
                        title=title,
                        performer="TezMedia",
                        caption="📥 @tezmedia_uz_bot orqali yuklandi",
                    )
                else:
                    bot.send_video(
                        chat_id,
                        media_file,
                        caption=f"🎬 {title}\n\n📥 @tezmedia_uz_bot",
                    )
            bot.delete_message(chat_id, wait_msg.message_id)
        except Exception as e:
            bot.edit_message_text(
                f"⚠️ Xatolik: {str(e)[:120]}",
                chat_id,
                wait_msg.message_id,
            )
        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

    # Aks holda — qo'shiq nomi bo'yicha YouTube'dan to'liq MP3 qidiramiz
    else:
        wait_msg = bot.send_message(
            chat_id, f"🔎 **{text}** — to‘liq qo‘shiq qidirilmoqda...", parse_mode="Markdown"
        )
        file_path = None
        try:
            file_path, title = download_youtube_song(text)
            if not file_path or not os.path.exists(file_path):
                bot.edit_message_text(
                    "❌ To‘liq qo‘shiq topilmadi. Qo‘shiq nomini aniqroq yozib ko‘ring.",
                    chat_id,
                    wait_msg.message_id,
                )
                return

            with open(file_path, "rb") as audio_file:
                bot.send_audio(
                    chat_id,
                    audio_file,
                    title=title,
                    performer="TezMedia",
                    caption="📥 @tezmedia_uz_bot orqali yuklandi",
                )
            bot.delete_message(chat_id, wait_msg.message_id)
        except Exception as e:
            bot.edit_message_text(
                f"⚠️ Xatolik: {str(e)[:120]}",
                chat_id,
                wait_msg.message_id,
            )
        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        "👋 **TezMedia** botiga xush kelibsiz!\n\n"
        "🚀 Pastdagi **⚡ TEZMEDIA AI PANEL** tugmasini bosib 3D boshqaruv panelini oching "
        "yoki to‘g‘ridan-to‘g‘ri chatga qo‘shiq nomi / havola yuboring:",
        reply_markup=get_panel_keyboard(),
        parse_mode="Markdown",
    )


@bot.message_handler(content_types=["web_app_data"])
def handle_web_app(message):
    try:
        data = json.loads(message.web_app_data.data)
        query_or_url = data.get("url", "")
        fmt = data.get("format", "MP3_320")
        force_audio = fmt == "MP3_320"
        process_request(message.chat.id, message.from_user.id, query_or_url, force_audio=force_audio)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Panel xatoligi: {str(e)[:120]}")


@bot.message_handler(func=lambda m: True)
def handle_all(message):
    process_request(message.chat.id, message.from_user.id, message.text, force_audio=False)


if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    bot.infinity_polling(skip_pending=True)
