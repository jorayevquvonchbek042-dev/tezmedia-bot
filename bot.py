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

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=4)
TRACK_TITLES = {}

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
    return f" ({mins}:{secs:02d})"

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
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        },
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
    wait_msg = bot.reply_to(message, f"🔍 «{query}» qidirilmoqda...")

    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            entries = info.get('entries', []) if info else []

        markup = types.InlineKeyboardMarkup(row_width=1)
        count = 0
        for item in entries:
            vid_id = item.get('id')
            title = item.get('title') or 'Nomsiz qo\'shiq'
            duration = format_duration(item.get('duration'))
            if vid_id:
                count += 1
                TRACK_TITLES[vid_id] = title
                if len(TRACK_TITLES) > 1000:
                    TRACK_TITLES.pop(next(iter(TRACK_TITLES)))

                short_title = title[:42] + "..." if len(title) > 42 else title
                btn_text = f"🎵 {count}. {short_title}{duration}"
                markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"aud:{vid_id}"))

        if count == 0:
            bot.edit_message_text("❌ Hech qanday qo'shiq topilmadi.", message.chat.id, wait_msg.message_id)
            return

        bot.edit_message_text(
            f"🎶 «{query}» bo'yicha topilgan qo'shiqlar:",
            message.chat.id,
            wait_msg.message_id,
            reply_markup=markup
        )
    except Exception:
        bot.edit_message_text(
            "❌ Hozir qidiruvda cheklov bor. Bir ozdan so'ng qayta urinib ko'ring.",
            message.chat.id,
            wait_msg.message_id
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith("aud:"))
def download_audio_callback(call):
    if not is_subscribed(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Avval kanalga obuna bo'ling!", show_alert=True)
        send_sub_prompt(call.message.chat.id)
        return

    vid_id = call.data.split("aud:", 1)[1]
    url = f"https://www.youtube.com/watch?v={vid_id}"
    bot.answer_callback_query(call.id, "⏳ Qo'shiq yuklanmoqda...")
    wait_msg = bot.send_message(call.message.chat.id, "⏳ Qo'shiq yuklanmoqda, biroz kuting...")

    base_name = f"audio_{call.message.chat.id}_{call.message.message_id}_{vid_id}"
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio[filesize<45M]/bestaudio/best',
        'outtmpl': f"{base_name}.%(ext)s",
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'geo_bypass': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = TRACK_TITLES.get(vid_id) or (info.get('title') if info else 'Audio')
            performer = info.get('uploader', 'TezMedia') if info else 'TezMedia'

        downloaded_files = glob.glob(f"{base_name}.*")
        if downloaded_files:
            audio_path = downloaded_files[0]
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
            bot.edit_message_text("❌ Qo'shiqni yuklab bo'lmadi.", call.message.chat.id, wait_msg.message_id)
    except Exception:
        bot.edit_message_text("❌ Qo'shiqni yuklab bo'lmadi.", call.message.chat.id, wait_msg.message_id)
    finally:
        for f in glob.glob(f"{base_name}.*"):
            try:
                os.remove(f)
            except Exception:
                pass

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    bot.infinity_polling()
