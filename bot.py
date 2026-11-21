import os
import re
import glob
import json
import base64
import urllib.parse
import urllib.request
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types
import yt_dlp

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
RAW_CHANNEL = os.environ.get("CHANNEL_ID", "").strip()
if RAW_CHANNEL and not RAW_CHANNEL.startswith("@") and not RAW_CHANNEL.startswith("-100"):
    CHANNEL_ID = f"@{RAW_CHANNEL}"
else:
    CHANNEL_ID = RAW_CHANNEL

COOKIES_RAW = os.environ.get("YT_COOKIES", "").strip()
COOKIES_PATH = "/tmp/yt_cookies.txt"

def prepare_cookies_file():
    if not COOKIES_RAW or COOKIES_RAW.lower() == "cookies.txt":
        return None
    try:
        if "# Netscape HTTP Cookie File" in COOKIES_RAW or "\t" in COOKIES_RAW:
            content = COOKIES_RAW
        else:
            content = base64.b64decode(COOKIES_RAW).decode("utf-8", errors="ignore")
        if len(content.strip()) < 20:
            return None
        with open(COOKIES_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        return COOKIES_PATH
    except Exception:
        return None

ACTIVE_COOKIE_FILE = prepare_cookies_file()

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
    port = int(os.environ.get("PORT", 7860))
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
            preview = (item.get("preview") or "").strip()
            dur = fmt_sec(item.get("duration"))
            if title:
                full = f"{artist} - {title}" if artist else title
                found.append({
                    "artist": artist or "TezMedia",
                    "title": title,
                    "full": full,
                    "dur": dur,
                    "preview": preview
                })
    except Exception:
        pass

    try:
        data = fetch_json(f"https://itunes.apple.com/search?term={q_enc}&media=music&limit=10")
        seen = {x["full"].lower() for x in found}
        for item in data.get("results", []):
            artist = (item.get("artistName") or "").strip()
            title = (item.get("trackName") or "").strip()
            preview = (item.get("previewUrl") or "").strip()
            dur_ms = item.get("trackTimeMillis")
            dur = fmt_sec(dur_ms // 1000) if dur_ms else ""
            if title:
                full = f"{artist} - {title}" if artist else title
                if full.lower() not in seen:
                    seen.add(full.lower())
                    found.append({
                        "artist": artist or "TezMedia",
                        "title": title,
                        "full": full,
                        "dur": dur,
                        "preview": preview
                    })
    except Exception:
        pass

    return found[:10]

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
    base_vid = f"video_{message.chat.id}_{message.message_id}"
    filename = f"{base_vid}.mp4"
    sent = False

    for clients in [['web', 'mweb', 'android'], ['ios', 'web']]:
        for f in glob.glob(f"{base_vid}*"):
            try:
                os.remove(f)
            except Exception:
                pass

        ydl_opts = {
            'format': 'best[ext=mp4][filesize<50M]/best[ext=mp4]/best',
            'outtmpl': filename,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'geo_bypass': True,
            'socket_timeout': 20,
            'extractor_args': {'youtube': {'player_client': clients}},
        }
        if ACTIVE_COOKIE_FILE:
            ydl_opts['cookiefile'] = ACTIVE_COOKIE_FILE

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            ready_files = [
                f for f in glob.glob(f"{base_vid}*")
                if not f.endswith((".part", ".ytdl", ".temp"))
            ]
            if ready_files:
                with open(ready_files[0], 'rb') as video:
                    bot.send_video(message.chat.id, video, caption="📥 @tezmedia_uz_bot orqali yuklandi")
                bot.delete_message(message.chat.id, wait_msg.message_id)
                sent = True
                break
        except Exception:
            pass

    if not sent:
        bot.edit_message_text(
            "❌ Videoni yuklab bo'lmadi. Havola ochiq ekanligini tekshiring yoki keyinroq urinib ko'ring.",
            message.chat.id,
            wait_msg.message_id
        )

    for f in glob.glob(f"{base_vid}*"):
        try:
            os.remove(f)
        except Exception:
            pass

@bot.message_handler(func=lambda m: m.text and not m.text.startswith('/') and extract_url(m.text) is None)
def search_music(message):
    if not is_subscribed(message.from_user.id):
        send_sub_prompt(message.chat.id)
        return

    query = message.text.strip()
    tracks = search_tracks_fast(query)
    if not tracks:
        tracks = [{"artist": "TezMedia", "title": query, "full": query, "dur": "", "preview": ""}]

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

    bot.answer_callback_query(call.id, "⏳ Audio tayyorlanmoqda...")
    wait_msg = bot.send_message(call.message.chat.id, f"⏳ «{tr['full']}» yuklanmoqda...")

    base_name = f"audio_{call.message.chat.id}_{call.message.message_id}_{key.replace(':', '_')}"
    sent = False
    clean_full = re.sub(r'\s*\(.*?\)\s*', ' ', tr['full']).strip()

    full_candidates = [
        (f"scsearch2:{clean_full}", None),
        (f"ytsearch1:{clean_full} official audio", ['web', 'mweb', 'android']),
        (f"ytsearch1:{clean_full}", ['ios', 'web']),
    ]

    for target, clients in full_candidates:
        for f in glob.glob(f"{base_name}*"):
            try:
                os.remove(f)
            except Exception:
                pass
        try:
            opts = {
                'format': 'bestaudio[ext!=m3u8]/bestaudio/best',
                'outtmpl': f"{base_name}.%(ext)s",
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'geo_bypass': True,
                'socket_timeout': 20,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
            if clients:
                opts['extractor_args'] = {'youtube': {'player_client': clients}}
            if ACTIVE_COOKIE_FILE:
                opts['cookiefile'] = ACTIVE_COOKIE_FILE

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([target])

            mp3_files = glob.glob(f"{base_name}*.mp3")
            files = mp3_files or [
                f for f in glob.glob(f"{base_name}*")
                if not f.endswith((".part", ".ytdl", ".temp"))
            ]
            if files and os.path.getsize(files[0]) > 50000:
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

    preview_url = tr.get("preview")
    if not sent and preview_url:
        for f in glob.glob(f"{base_name}*"):
            try:
                os.remove(f)
            except Exception:
                pass
        try:
            ext = ".m4a" if ".m4a" in preview_url else ".mp3"
            raw_path = f"{base_name}{ext}"
            req = urllib.request.Request(preview_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp, open(raw_path, "wb") as out:
                out.write(resp.read())

            if os.path.exists(raw_path) and os.path.getsize(raw_path) > 1000:
                with open(raw_path, "rb") as audio:
                    bot.send_audio(
                        call.message.chat.id,
                        audio,
                        title=tr["title"],
                        performer=tr["artist"],
                        caption="🎵 @tezmedia_uz_bot (30s preview — to'liq manba cheklangan)"
                    )
                bot.delete_message(call.message.chat.id, wait_msg.message_id)
                sent = True
        except Exception:
            pass

    if not sent:
        bot.edit_message_text(
            "❌ Ushbu qo'shiq uchun audio topilmadi. Ro'yxatdan boshqa raqamni bosing.",
            call.message.chat.id,
            wait_msg.message_id
        )

    for f in glob.glob(f"{base_name}*"):
        try:
            os.remove(f)
        except Exception:
            pass

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    bot.infinity_polling(timeout=20, long_polling_timeout=15)
       
