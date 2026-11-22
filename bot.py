import os
import re
import time
import threading
from flask import Flask
import telebot
from telebot import types
import yt_dlp

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@tezmedia_rasmiy")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)


@app.route("/")
def home():
    return "TezMedia Bot is running!"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


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

    # 1. YouTube'dan 7 ta natija qidirib, Shorts va 60 soniyadan qisqa treklarni tashlab ketamiz
    search_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "default_search": "ytsearch7",
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

            # 30 soniyalik Shorts yoki qisqa parchalarni filtrlaymiz (kamida 60 soniya bo'lishi shart)
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

    # 2. Tanlangan to'liq trekning audiosini yuklaymiz
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


def download_video_link(url):
    os.makedirs("downloads", exist_ok=True)
    timestamp = int(time.time())
    out_template = f"downloads/video_{timestamp}.%(ext)s"

    ydl_opts = {
        "format": "best[ext=mp4][filesize<48M]/best[ext=mp4]/best",
        "outtmpl": out_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": ["android", "ios"]}},
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info), info.get("title", "Video")


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        "👋 **TezMedia** botiga xush kelibsiz!\n\n"
        "🎵 **Qo‘shiq topish:** Qo‘shiq yoki ijrochi nomini yozing.\n"
        "📥 **Video yuklash:** Instagram, TikTok yoki YouTube havolasini yuboring.",
        parse_mode="Markdown",
    )


@bot.message_handler(func=lambda m: True)
def handle_all(message):
    user_id = message.from_user.id
    if not is_subscribed(user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                "📢 Kanalga obuna bo‘lish", url="https://t.me/tezmedia_rasmiy"
            )
        )
        bot.send_message(
            message.chat.id,
            "Botdan foydalanish uchun avval **Trend & Media** kanaliga obuna bo‘ling:",
            reply_markup=markup,
            parse_mode="Markdown",
        )
        return

    text = (message.text or "").strip()
    if not text:
        return

    # Agar havola yuborilgan bo'lsa — videoni yuklaymiz
    if re.match(r"^https?://", text):
        wait_msg = bot.send_message(message.chat.id, "⏳ Video yuklanmoqda...")
        file_path = None
        try:
            file_path, title = download_video_link(text)
            if not file_path or not os.path.exists(file_path):
                bot.edit_message_text(
                    "❌ Videoni yuklab bo‘lmadi. Havolani tekshirib qayta yuboring.",
                    message.chat.id,
                    wait_msg.message_id,
                )
                return

            with open(file_path, "rb") as video_file:
                bot.send_video(
                    message.chat.id,
                    video_file,
                    caption=f"🎬 {title}\n\n📥 @tezmedia_uz_bot",
                )
            bot.delete_message(message.chat.id, wait_msg.message_id)
        except Exception as e:
            bot.edit_message_text(
                f"⚠️ Xatolik: {str(e)[:120]}",
                message.chat.id,
                wait_msg.message_id,
            )
        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

    # Aks holda — YouTube'dan to'liq qo'shiq qidiramiz
    else:
        wait_msg = bot.send_message(
            message.chat.id, "🔎 YouTube’dan to‘liq qo‘shiq qidirilmoqda..."
        )
        file_path = None
        try:
            file_path, title = download_youtube_song(text)
            if not file_path or not os.path.exists(file_path):
                bot.edit_message_text(
                    "❌ To‘liq qo‘shiq topilmadi. Qo‘shiq nomini aniqroq yozib ko‘ring.",
                    message.chat.id,
                    wait_msg.message_id,
                )
                return

            with open(file_path, "rb") as audio_file:
                bot.send_audio(
                    message.chat.id,
                    audio_file,
                    title=title,
                    performer="TezMedia",
                    caption="📥 @tezmedia_uz_bot orqali yuklandi",
                )
            bot.delete_message(message.chat.id, wait_msg.message_id)
        except Exception as e:
            bot.edit_message_text(
                f"⚠️ Xatolik: {str(e)[:120]}",
                message.chat.id,
                wait_msg.message_id,
            )
        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)


if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    bot.infinity_polling(skip_pending=True)
