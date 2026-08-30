import asyncio
import logging

from telethon import TelegramClient, events

# Sozlamalar config.py orqali yuklanadi — shu bilan API_ID/API_HASH .env'da
# to'ldirilmagan bo'lsa, xato joyi noaniq bo'lib qolgan (1234567/"your_api_hash"
# soxta qiymatlar bilan urinish) o'rniga darhol aniq xabar bilan to'xtaydi.
import config
import db
from userbot import send_to_chat

logging.basicConfig(
    filename=config.LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("main")

API_ID = config.API_ID
API_HASH = config.API_HASH
NOTIFY_TARGET = config.NOTIFY_TARGET

client = TelegramClient("user_session", API_ID, API_HASH)

# client.start() dan keyin to'ldiriladi — har bir reply hodisasida qayta
# get_me() so'ramaslik uchun bir marta keshlanadi.
_me = None


# --- 1. GURUHLARGA SIKLLI VA ORALIQ BILAN YUBORISH ---
async def send_broadcast(chats, text, repeat_count, delay_seconds):
    """
    Belgilangan guruhlarga xabarni takroran va oraliq sekund bilan yuboradi.
    Har bir chatga yuborish uchun userbot.send_to_chat() dan foydalaniladi —
    u FloodWait'ni xavfsiz (cheksiz bo'lib qolmasdan, MAX_FLOODWAIT_SLEEP bilan
    chegaralab) qayta uradi, shuning uchun bu yerda alohida qayta-urinish
    mantig'ini takrorlashning hojati yo'q va bitta chatdagi kutilmagan xato
    butun jarayonni to'xtatib qo'ymaydi.
    """
    ok_total, fail_total = 0, 0
    for round_num in range(1, repeat_count + 1):
        print(f"\n[+] {round_num}/{repeat_count} - aylanma yuborilmoqda...")
        for chat in chats:
            ok, detail = await send_to_chat(client, chat, text=text, max_retries=2)
            if ok:
                ok_total += 1
                print(f"  -> Xabar yuborildi: {chat}")
            else:
                fail_total += 1
                print(f"  [-] Xatolik ({chat}): {detail}")

            # Telegram spam filtriga tushmaslik uchun chatlar orasida 2 soniya kutish
            await asyncio.sleep(2)

        if round_num < repeat_count:
            print(f"[i] Keyingi aylanmagacha {delay_seconds} soniya kutilmoqda...")
            await asyncio.sleep(delay_seconds)

    print(f"\n[✓] Yakunlandi: {ok_total} ta muvaffaqiyatli, {fail_total} ta xato.")
    db.add_audit_log(
        config.OWNER_ID,
        "avto_broadcast",
        {"chats": len(chats), "repeat_count": repeat_count, "ok": ok_total, "fail": fail_total},
    )


def _parse_chat(raw):
    """"@username" -> shundayligicha, "-100..." yoki oddiy raqamli ID -> int."""
    cleaned = raw.lstrip("-")
    if cleaned.isdigit():
        return int(raw)
    return raw


# --- 2. BUYRUQNI QABUL QILISH (.avto) ---
# Format: .avto | guruh1,guruh2 | Matn | Takrorlash_soni | Kutish_sekundi
# Masalan: .avto | -100123456789,@guruh_nomi | Salom hammaga! | 5 | 60
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.avto\s+(.+)"))
async def handle_avto_command(event):
    try:
        # ".avto" dan keyin ixtiyoriy "|" bilan boshlash mumkin (masalan
        # ".avto | chat1 | matn | 1 | 5"). Bu "|"ni olib tashlamasak, split("|")
        # boshida bo'sh bo'lak hosil bo'lib, hamma qism bittadan siljib ketadi
        # va chatlar ro'yxati o'rniga matn maydoniga tushib qoladi.
        raw_text = event.pattern_match.group(1).lstrip("|").strip()
        parts = [p.strip() for p in raw_text.split("|")]
        if len(parts) != 4:
            raise ValueError("4 ta qism kerak: chatlar | matn | soni | sekund")

        raw_chats = [c.strip() for c in parts[0].split(",") if c.strip()]
        if not raw_chats:
            raise ValueError("kamida bitta chat ko'rsatilishi kerak")
        chats = [_parse_chat(c) for c in raw_chats]

        text = parts[1]
        if not text:
            raise ValueError("xabar matni bo'sh bo'lishi mumkin emas")

        repeat_count = int(parts[2])
        delay_seconds = int(parts[3])
        if repeat_count < 1:
            raise ValueError("takrorlash soni kamida 1 bo'lishi kerak")
        if delay_seconds < 0:
            raise ValueError("kutish sekundi manfiy bo'lishi mumkin emas")
        if len(chats) > config.MAX_BROADCAST_TARGETS:
            raise ValueError(
                f"bir martada ko'pi bilan {config.MAX_BROADCAST_TARGETS} ta chatga yuborish mumkin"
            )

        await event.edit(
            f"🚀 **Avto-yuborish boshlandi:**\n"
            f"• Guruhlar soni: `{len(chats)} ta`\n"
            f"• Takrorlanish: `{repeat_count} marta`\n"
            f"• Oraliq vaqt: `{delay_seconds} sek`"
        )

        # Orqa fonda (background) yuborish
        asyncio.create_task(send_broadcast(chats, text, repeat_count, delay_seconds))

    except Exception as e:
        log.exception("handle_avto_command xato")
        await event.edit(
            f"⚠️ **Xato format!**\n\nIshlatish tartibi:\n`.avto | chat1,chat2 | Matn | Soni | Sekund`\n\nXatolik: `{e}`"
        )


# --- 3. REPLY KELGANDA HAVOLASINI FOYDALANUVCHIGA YUBORISH ---
@client.on(events.NewMessage)
async def catch_replies(event):
    if not event.is_group or not event.is_reply:
        return

    me = _me or await client.get_me()

    # Reply aynan sizning xabaringizga qilinganini tekshirish
    reply_msg = await event.get_reply_message()
    if reply_msg and reply_msg.sender_id == me.id and event.sender_id != me.id:
        chat = await event.get_chat()
        sender = await event.get_sender()

        sender_name = getattr(sender, "first_name", "Foydalanuvchi") or "Foydalanuvchi"
        username = f"@{sender.username}" if getattr(sender, "username", None) else "mavjud emas"
        chat_title = getattr(chat, "title", "Guruh")

        # Guruh turiga qarab havola (link) yasash
        if getattr(chat, "username", None):
            msg_link = f"https://t.me/{chat.username}/{event.id}"
        else:
            clean_id = str(event.chat_id).replace("-100", "").replace("-", "")
            msg_link = f"https://t.me/c/{clean_id}/{event.id}"

        alert_text = (
            f"🔔 **Sizning xabaringizga javob (Reply) keldi!**\n\n"
            f"👤 **Yozuvchi:** {sender_name} ({username})\n"
            f"💬 **Guruh:** {chat_title}\n"
            f"📝 **Xabar:** {event.text or '[Media/Boshqa]'}\n\n"
            f"🔗 **Xabar havolasi:** {msg_link}"
        )

        ok, detail = await send_to_chat(client, NOTIFY_TARGET, text=alert_text)
        if ok:
            print(f"[REPLY] Bildirishnoma {NOTIFY_TARGET} ga yuborildi.")
        else:
            log.warning("Reply bildirishnoma yuborilmadi: %s", detail)
            print(f"[REPLY XATOLIK]: {detail}")


async def main():
    global _me
    db.init_db()
    await client.start()
    _me = await client.get_me()
    print(f"Userbot muvaffaqiyatli ishga tushdi... (@{_me.username or _me.id})")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
