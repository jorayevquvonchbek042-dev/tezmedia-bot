import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
import yt_dlp

TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

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

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "Assalomu alaykum! TezMedia botiga xush kelibsiz.\n\n"
        "Instagram, TikTok yoki YouTube video havolasini yuboring — men uni yuklab beraman!"
    )

@bot.message_handler(func=lambda m: m.text and ("http://" in m.text or "https://" in m.text))
def download_video(message):
    url = message.text.strip()
    wait_msg = bot.reply_to(message, "⏳ Video yuklanmoqda, biroz kuting...")
    filename = f"video_{message.chat.id}_{message.message_id}.mp4"

    ydl_opts = {
        'format': 'best[ext=mp4][filesize<50M]/best[ext=mp4]/best',
        'outtmpl': filename,
        'quiet': True,
        'noplaylist': True,
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
        bot.edit_message_text("❌ Xatolik yuz berdi. Havola ochiq ekanligini tekshiring.", message.chat.id, wait_msg.message_id)
    finally:
        if os.path.exists(filename):
            os.remove(filename)

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    bot.infinity_polling()
