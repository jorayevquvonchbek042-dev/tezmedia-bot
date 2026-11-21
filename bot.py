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

    bot.answer_callback_query(call.id, "⏳ To'liq audio izlanmoqda...")
    wait_msg = bot.send_message(call.message.chat.id, f"⏳ «{tr['full']}» to'liq audio qilib yuklanmoqda...")

    base_name = f"audio_{call.message.chat.id}_{call.message.message_id}_{key.replace(':', '_')}"
    sent = False
    clean_full = re.sub(r'\s*\(.*?\)\s*', ' ', tr['full']).strip()

    # 1-bosqich: avval to'liq trekni yuklashga harakat qilamiz
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

    # 2-bosqich: to'liq trek o'tmasa, zaxira sifatida preview yuboramiz
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
