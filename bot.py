import os
import re
import glob
import urllib.parse
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
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
SEARCH_CACHE = {}

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

def format_duration(ms):
    if not ms:
        return ""
    seconds = int(ms // 1000)
    mins, secs = divmod(seconds, 60)
    return f" ({mins}:{secs:02d})"

def fast_music_search(query):
    results = []
    # 1-tezkor manba: Deezer API (0.3 soniyada ijrochi va qo'shiq nomini qaytaradi)
    try:
        r = requests.get(
            "https://api.deezer.com/search",
            params={"q": query, "limit": 6},
            timeout=5
        )
        if r.status_code == 200:
            for item in r.json().get("data", []):
                artist = item.get("artist", {}).get("name", "")
                title = item.get("title", "")
                dur = format_duration(item.get("duration", 0) * 1000)
                if artist and title:
                    results.append({
                        "label": f"{artist} — {title}",
                        "dur": dur,
                        "artist": artist,
                        "title": title
                    })
    except Exception:
        pass

    # 2-tezkor zaxira manba: iTunes API
    if not results:
        try:
            r = requests.get(
                "https://itunes.apple.com/search",
                params={"term": query, "media": "music", "limit": 6},
                timeout=5
            )
            if r.status_code == 200:
                for item in r.json().get("results", []):
                    artist = item.get("artistName", "")
                    title = item.get("trackName", "")
                    dur = format_duration(item.get("trackTimeMillis", 0))
                    if artist and title:
                        results.append({
                            "label": f"{artist} — {title}",
                            "dur": dur,
                            "artist": artist,
                            "title": title
                        })
        except Exception:
            pass

    return results[:5]

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
    results = fast_music_search(query)

    # Agar katalogda topilmasa, to'g'ridan-to'g'ri SoundCloud/YouTube orqali qidirish tugmasini beradi
    if not results:
        results = [{"label": query, "dur": "", "artist": "", "title": query}]

    markup = types.InlineKeyboardMarkup(row_width=1)
    for idx, item in enumerate(results, 1):
        cache_key = f"{message.chat.id}_{message.message_id}_{idx}"
        SEARCH_CACHE[cache_key] = item
        if len(SEARCH_CACHE) > 500:
            SEARCH_CACHE.pop(next(iter(SEARCH_CACHE)))

        short_label = item["label"][:42] + "..." if len(item["label"]) > 42 else item["label"]
        btn_text = f"🎵 {idx}. {short_label}{item['dur']}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"trk:{cache_key}"))

    bot.reply_to(
        message,
        f"🎶 «{query}» bo'yicha natijalar (keraklisini tanlang):",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("trk:"))
def download_track_callback(call):
    if not is_subscribed(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Avval kanalga obuna bo'ling!", show_alert=True)
        send_sub_prompt(call.message.chat.id)
        return

    cache_key = call.data.split("trk:", 1)[1]
    item = SEARCH_CACHE.get(cache_key)
    if not item:
        bot.answer_callback_query(call.id, "⚠️ Eskirgan tugma, qo'shiq nomini qayta yozing.", show_alert=True)
        return

    search_term = item["label"]
    bot.answer_callback_query(call.id, "⏳ Yuklanmoqda...")
    wait_msg = bot.send_message(call.message.chat.id, f"⏳ «{search_term}» yuklanmoqda...")

    base_name = f"audio_{call.message.chat.id}_{call.message.message_id}"
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

    success = False
    for source_prefix in (f"scsearch1:{search_term}", f"ytsearch1:{search_term} audio"):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(source_prefix, download=True)
                entry = info['entries'][0] if info and 'entries' in info and info['entries'] else info

            downloaded_files = glob.glob(f"{base_name}.*")
            if downloaded_files:
                audio_path = downloaded_files[0]
                title = item["title"] or (entry.get('title') if entry else search_term)
                performer = item["artist"] or (entry.get('uploader') if entry else "TezMedia")
                with open(audio_path, 'rb') as audio:
                    bot.send_audio(
                        call.message.chat.id,
                        audio,
                        title=title,
                        performer=performer,
                        caption="🎵 @tezmedia_uz_bot orqali yuklandi"
                    )
                bot.delete_message(call.message.chat.id, wait_msg.message_id)
                success = True
                break
        except Exception:
            for f in glob.glob(f"{base_name}.*"):
                try:
                    os.remove(f)
                except Exception:
                    pass

    if not success:
        bot.edit_message_text(
            "❌ Qo'shiqni yuklab bo'lmadi. Boshqa variantni tanlab ko'ring.",
            call.message.chat.id,
            wait_msg.message_id
        )

    for f in glob.glob(f"{base_name}.*"):
        try:
            os.remove(f)
        except Exception:
            pass

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    bot.infinity_polling()
