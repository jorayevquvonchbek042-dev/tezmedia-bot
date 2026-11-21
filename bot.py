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

    bot.answer_callback_query(call.id, "⏳ MP3 tayyorlanmoqda...")
    wait_msg = bot.send_message(call.message.chat.id, f"⏳ «{tr['full']}» MP3 qilib yuklanmoqda...")

    base_name = f"audio_{call.message.chat.id}_{call.message.message_id}_{key.replace(':', '_')}"
    sent = False
    clean_full = re.sub(r'\s*\(.*?\)\s*', ' ', tr['full']).strip()

    candidates = [
        (f"ytsearch1:{clean_full} official audio", ['android', 'ios', 'web']),
        (f"ytsearch1:{clean_full}", ['web', 'mweb', 'android']),
        (f"ytsearch2:{tr['full']}", ['ios', 'web']),
        (f"scsearch2:{clean_full}", None),
    ]

    for target, clients in candidates:
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

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([target])

            mp3_files = glob.glob(f"{base_name}*.mp3")
            files = mp3_files or [
                f for f in glob.glob(f"{base_name}*")
                if not f.endswith((".part", ".ytdl", ".temp"))
            ]
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
        except Exception as e:
            print(f"MP3 skip [{target}]: {e}")

    if not sent:
        bot.edit_message_text(
            "❌ Hozircha ushbu qo'shiq manbalari cheklangan. Ro'yxatdan boshqa raqamni bosing yoki boshqa qo'shiq nomini yozing.",
            call.message.chat.id,
            wait_msg.message_id
        )

    for f in glob.glob(f"{base_name}*"):
        try:
            os.remove(f)
        except Exception:
            pass
