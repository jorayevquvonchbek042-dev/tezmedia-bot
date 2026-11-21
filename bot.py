import os
import re
import glob
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types
import yt_dlp

TOKEN = os.environ.get("BOT_TOKEN")
RAW_CHANNEL = os.environ.get("CHANNEL_ID", "").strip()
if RAW_CHANNEL and not RAW_CHANNEL.startswith("@") and not RAW_CHANNEL.startswith("-100"):
    CHANNEL_ID = f"@{RAW_CHANNEL}"
else:
    CHANNEL_ID = RAW_CHANNEL

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=6)
TRACK_ITEMS = {}

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"TezMedia bot ishlamoqda!")

    def log_message(self, format, *args):
        pass

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

def extract_url(text):
    if not text:
        return None
    match = re.search(r'https?://[^\s]+', text)
    return match.group(0) if match else None

def is_subscribed(user_id):
    if not CHANNEL_ID:
        return True
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

def send_sub_prompt(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    channel_url = f"https://t.me/{CHANNEL_ID.lstrip('@')}"
    btn_sub = types.InlineKeyboardButton("📢 Kanalga obuna bo'lish", url=channel_url)
    btn_check = types.InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")
    markup.add(btn_sub, btn_check)
    bot.send_message(
        chat_id,
        "⚠️ Botdan foydalanish uchun avval rasmiy kanalimizga obuna bo'ling va «Tekshirish» tugmasini bosing:",
        reply_markup=markup
    )

def format_duration(seconds):
    if not seconds:
        return ""
    seconds = int(seconds)
    mins, secs = divmod(seconds, 60)
    return f" {mins}:{secs:02d}"

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_sub_callback(call):
    if is_subscribed(call.from_user.id):
        bot.answer_callback_query(call.id, "✅ Obuna tasdiqlandi!")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        bot.send_message(
            call.message.chat.id,
            "Rahmat! Endi Instagram, TikTok, YouTube havolasini yuboring yoki qo'shiqchi nomini yozing."
        )
    else:
        bot.answer_callback_query(call.id, "❌ Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if not is_subscribed(message.from_user.id):
        send_sub_prompt(message.chat.id)
        return
    bot.reply_to(
        message,
        "Assalomu alaykum! TezMedia botiga xush kelibsiz.\n\n"
        "📥 Video yuklash uchun Instagram, TikTok yoki YouTube havolasini yuboring.\n"
        "🎵 Qo'shiq topish uchun qo'shiqchi yoki qo'shiq nomini yozing!"
    )

@bot.message_handler(func=lambda m: extract_url(m.text) is not None)
def download_video(message):
    if not is_subscribed(message.from_user.id):
        send_sub_prompt(message.chat.id)
        return

    url = extract_url(message.text)
    wait_msg = bot.reply_to(message, "⏳ Video yuklanmoqda, biroz kuting...")
    filename = f"video_{message.chat.id}_{message.message_id}.mp4"

    ydl_opts = {
        'format': 'best[ext=mp4][filesize<50M]/best[ext=mp4]/best',
        'outtmpl': filename,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'geo_bypass': True,
        'socket_timeout': 15,
        'extractor_args': {'youtube': {'player_client': ['android', 'ios', 'web']}},
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if os.path.exists(filename):
            with open(filename, 'rb') as video:
                bot.send_video(message.chat.id, video, caption="📥 @tezmedia_uz_bot orqali yuklandi")
            bot.delete_message(message.chat.id, wait_msg.message_id)
        else:
            bot.edit_message_text("❌ Videoni yuklab bo'lmadi.", message.chat.id, wait_msg.message_id)
    except Exception:
        bot.edit_message_text(
            "❌ Videoni yuklab bo'lmadi. Havola ochiq ekanligini tekshiring.",
            message.chat.id,
            wait_msg.message_id
        )
    finally:
        if os.path.exists(filename):
            os.remove(filename)

@bot.message_handler(func=lambda m: m.text and not m.text.startswith('/') and extract_url(m.text) is None)
def search_music(message):
    if not is_subscribed(message.from_user.id):
        send_sub_prompt(message.chat.id)
        return

    query = message.text.strip()
    wait_msg = bot.reply_to(message, f"🔎 {query}")

    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 10,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch10:{query}", download=False)
            entries = info.get('entries', []) if info else []

        lines = [f"🔎 {query}\n"]
        buttons = []
        idx = 0

        for item in entries:
            vid_id = item.get('id')
            title = (item.get('title') or '').strip()
            if vid_id and title:
                idx += 1
                dur = format_duration(item.get('duration'))
                clean_title = title.replace("<", "").replace(">", "")
                lines.append(f"{idx}. {clean_title}{dur}")

                key = f"{message.chat.id}_{message.message_id}_{idx}"
                TRACK_ITEMS[key] = {"id": vid_id, "title": clean_title}
                if len(TRACK_ITEMS) > 1500:
                    TRACK_ITEMS.pop(next(iter(TRACK_ITEMS)))

                buttons.append(types.InlineKeyboardButton(str(idx), callback_data=f"dl:{key}"))

        if idx == 0:
            bot.edit_message_text("❌ Hech qanday qo'shiq topilmadi.", message.chat.id, wait_msg.message_id)
            return

        markup = types.InlineKeyboardMarkup(row_width=5)
        markup.add(*buttons)

        bot.edit_message_text(
            "\n".join(lines),
            message.chat.id,
            wait_msg.message_id,
            reply_markup=markup
        )
    except Exception:
        bot.edit_message_text(
            "❌ Qidiruvda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.",
            message.chat.id,
            wait_msg.message_id
        )

def try_download_audio(target, base_name, player_clients=None):
    opts = {
        'format': 'bestaudio[filesize<45M]/bestaudio/best',
        'outtmpl': f"{base_name}.%(ext)s",
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'geo_bypass': True,
        'socket_timeout': 15,
    }
    if player_clients:
        opts['extractor_args'] = {'youtube': {'player_client': player_clients}}

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(target, download=True)
        if isinstance(info, dict) and 'entries' in info and info['entries']:
            info = info['entries'][0]
        return info

@bot.callback_query_handler(func=lambda call: call.data.startswith("dl:"))
def download_audio_callback(call):
    if not is_subscribed(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Avval kanalga obuna bo'ling!", show_alert=True)
        send_sub_prompt(call.message.chat.id)
        return

    key = call.data.split("dl:", 1)[1]
    track = TRACK_ITEMS.get(key)
    if not track:
        bot.answer_callback_query(call.id, "⚠️ Ro'yxat eskirgan, qayta qidiring.", show_alert=True)
        return

    vid_id = track["id"]
    title = track["title"]
    yt_url = f"https://www.youtube.com/watch?v={vid_id}"

    bot.answer_callback_query(call.id, "⏳ Yuklanmoqda...")
    wait_msg = bot.send_message(call.message.chat.id, "⏳ Qo'shiq yuklanmoqda, biroz kuting...")

    base_name = f"audio_{call.message.chat.id}_{call.message.message_id}_{vid_id}"
    downloaded_info = None

    attempts = [
        (yt_url, ['android', 'ios']),
        (yt_url, ['web_safari', 'mweb']),
        (f"scsearch1:{title}", None),
    ]

    for target, clients in attempts:
        for f in glob.glob(f"{base_name}.*"):
            try:
                os.remove(f)
            except Exception:
                pass
        try:
            downloaded_info = try_download_audio(target, base_name, clients)
            if glob.glob(f"{base_name}.*"):
                break
        except Exception:
            downloaded_info = None

    try:
        files = glob.glob(f"{base_name}.*")
        if files:
            audio_path = files[0]
            performer = (downloaded_info.get('uploader') if isinstance(downloaded_info, dict) else None) or "TezMedia"
            with open(audio_path, 'rb') as audio:
                bot.send_audio(
                    call.message.chat.id,
                    audio,
                    title=title,
                    performer=performer,
                    caption="🎵 @tezmedia_uz_bot orqali yuklandi"
                )
            bot.delete_message(call.message.chat.id, wait_msg.message_id)
        else:
            bot.edit_message_text(
                "❌ Hozir bu qo'shiqni yuklab bo'lmadi. Ro'yxatdan boshqa raqamni bosib ko'ring.",
                call.message.chat.id,
                wait_msg.message_id
            )
    except Exception:
        bot.edit_message_text(
            "❌ Qo'shiqni yuborishda xatolik yuz berdi.",
            call.message.chat.id,
            wait_msg.message_id
        )
    finally:
        for f in glob.glob(f"{base_name}.*"):
            try:
                os.remove(f)
            except Exception:
                pass

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    bot.infinity_polling(timeout=20, long_polling_timeout=15)
