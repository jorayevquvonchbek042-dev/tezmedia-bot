import os
import re
import glob
import json
import urllib.parse
import urllib.request
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

COOKIE_FILE = "cookies.txt" if os.path.exists("cookies.txt") else None

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

def fmt_sec(sec):
    if not sec:
        return ""
    sec = int(sec)
    m, s = divmod(sec, 60)
    return f" {m}:{s:02d}"

def fetch_json(url, timeout=8):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))

def search_tracks_fast(query):
    found = []
    q_enc = urllib.parse.quote(query)

    try:
        data = fetch_json(f"https://api.deezer.com/search?q={q_enc}&limit=10")
        for item in data.get("data", []):
            artist = (item.get("artist") or {}).get("name", "").strip()
            title = (item.get("title") or "").strip()
            dur = fmt_sec(item.get("duration"))
            if title:
                full = f"{artist} - {title}" if artist else title
                found.append({"artist": artist or "TezMedia", "title": title, "full": full, "dur": dur})
    except Exception:
        pass

    try:
        data = fetch_json(f"https://itunes.apple.com/search?term={q_enc}&media=music&limit=10")
        seen = {x["full"].lower() for x in found}
        for item in data.get("results", []):
            artist = (item.get("artistName") or "").strip()
            title = (item.get("trackName") or "").strip()
            dur_ms = item.get("trackTimeMillis")
            dur = fmt_sec(dur_ms // 1000) if dur_ms else ""
            if title:
                full = f"{artist} - {title}" if artist else title
                if full.lower() not in seen:
                    seen.add(full.lower())
                    found.append({"artist": artist or "TezMedia", "title": title, "full": full, "dur": dur})
    except Exception:
        pass

    return found[:10]

def build_ydl_opts(outtmpl, is_audio=True, clients=None):
    opts = {
        'format': 'bestaudio[filesize<45M]/bestaudio/best' if is_audio else 'best[ext=mp4][filesize<50M]/best[ext=mp4]/best',
        'outtmpl': outtmpl,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'geo_bypass': True,
        'socket_timeout': 20,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        },
    }
    if COOKIE_FILE and os.path.exists(COOKIE_FILE):
        opts['cookiefile'] = COOKIE_FILE
    if clients:
        opts['extractor_args'] = {'youtube': {'player_client': clients}}
    return opts

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

    try:
        ydl_opts = build_ydl_opts(filename, is_audio=False, clients=['web', 'android', 'ios'])
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
    tracks = search_tracks_fast(query)
    if not tracks:
        tracks = [{"artist": "TezMedia", "title": query, "full": query, "dur": ""}]

    lines = [f"🔎 {query}\n"]
    buttons = []

    for idx, tr in enumerate(tracks, 1):
        lines.append(f"{idx}. {tr['full']}{tr['dur']}")
        key = f"{message.chat.id}_{message.message_id}_{idx}"
        TRACK_ITEMS[key] = tr
        if len(TRACK_ITEMS) > 1500:
            TRACK_ITEMS.pop(next(iter(TRACK_ITEMS)))
        buttons.append(types.InlineKeyboardButton(str(idx), callback_data=f"dl:{key}"))

    markup = types.InlineKeyboardMarkup(row_width=5)
    markup.add(*buttons)

    bot.reply_to(message, "\n".join(lines), reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("dl:"))
def download_audio_callback(call):
    if not is_subscribed(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Avval kanalga obuna bo'ling!", show_alert=True)
        send_sub_prompt(call.message.chat.id)
        return

    key = call.data.split("dl:", 1)[1]
    tr = TRACK_ITEMS.get(key)
    if not tr:
        bot.answer_callback_query(call.id, "⚠️ Ro'yxat eskirgan, qayta qidiring.", show_alert=True)
        return

    bot.answer_callback_query(call.id, "⏳ Audio yuklanmoqda...")
    wait_msg = bot.send_message(call.message.chat.id, f"⏳ «{tr['full']}» yuklanmoqda...")

    base_name = f"audio_{call.message.chat.id}_{call.message.message_id}_{key.replace(':', '_')}"
    sent = False

    candidates = [
        (f"ytsearch1:{tr['full']} audio", ['web', 'mweb']),
        (f"ytsearch1:{tr['full']}", ['android', 'ios']),
        (f"scsearch1:{tr['full']}", None),
    ]

    for target, clients in candidates:
        for f in glob.glob(f"{base_name}.*"):
            try:
                os.remove(f)
            except Exception:
                pass
        try:
            opts = build_ydl_opts(f"{base_name}.%(ext)s", is_audio=True, clients=clients)
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([target])

            files = glob.glob(f"{base_name}.*")
            if files:
                with open(files[0], 'rb') as audio:
                    bot.send_audio(
                        call.message.chat.id,
                        audio,
                        title=tr["title"],
                        performer=tr["artist"],
                        caption="🎵 @tezmedia_uz_bot orqali yuklandi"
                    )
                bot.delete_message(call.message.chat.id, wait_msg.message_id)
                sent = True
                break
        except Exception:
            pass

    if not sent:
        bot.edit_message_text(
            "❌ Hozir bu audio faylni serverdan yuklab bo'lmadi. Ro'yxatdan boshqa raqamni bosib ko'ring.",
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
    bot.infinity_polling(timeout=20, long_polling_timeout=15)
