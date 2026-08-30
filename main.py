import os
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

# .env faylidan sozlamalarni yuklash
load_dotenv()
API_ID = int(os.getenv("API_ID", 1234567))
API_HASH = os.getenv("API_HASH", "your_api_hash")
NOTIFY_TARGET = os.getenv("NOTIFY_TARGET", "foydalanuvchikuu")

client = TelegramClient("user_session", API_ID, API_HASH)


# --- 1. GURUHLARGA SIKLLI VA ORALIQ BILAN YUBORISH ---
async def send_broadcast(chats, text, repeat_count, delay_seconds):
    """
    Belgilangan guruhlarga xabarni takroran va oraliq sekund bilan yuboradi.
    """
    for round_num in range(1, repeat_count + 1):
        print(f"\n[+] {round_num}/{repeat_count} - aylanma yuborilmoqda...")
        for chat in chats:
            try:
                await client.send_message(chat, text)
                print(f"  -> Xabar yuborildi: {chat}")
            except FloodWaitError as e:
                print(f"  [!] FloodWait: {e.seconds} soniya kutilmoqda...")
                await asyncio.sleep(e.seconds)
                await client.send_message(chat, text)
            except Exception as ex:
                print(f"  [-] Xatolik ({chat}): {ex}")

            # Telegram spam filtriga tushmaslik uchun chatlar orasida 2 soniya kutish
            await asyncio.sleep(2)

        if round_num < repeat_count:
            print(f"[i] Keyingi aylanmagacha {delay_seconds} soniya kutilmoqda...")
            await asyncio.sleep(delay_seconds)

    print("\n[✓] Barcha xabarlar to'liq yuborildi!")


# --- 2. BUYRUQNI QABUL QILISH (.avto) ---
# Format: .avto | guruh1,guruh2 | Matn | Takrorlash_soni | Kutish_sekundi
# Masalan: .avto | -100123456789,@guruh_nomi | Salom hammaga! | 5 | 60
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.avto (.+)"))
async def handle_avto_command(event):
    try:
        raw_text = event.pattern_match.group(1)
        parts = [p.strip() for p in raw_text.split("|")]

        raw_chats = [c.strip() for c in parts[0].split(",")]
        # Raqamli guruh ID yoki @username'larni ajratib olish
        chats = [int(c) if c.startswith("-100") or c.lstrip("-").isdigit() else c for c in raw_chats]
        text = parts[1]
        repeat_count = int(parts[2])
        delay_seconds = int(parts[3])

        await event.edit(
            f"🚀 **Avto-yuborish boshlandi:**\n"
            f"• Guruhlar soni: `{len(chats)} ta`\n"
            f"• Takrorlanish: `{repeat_count} marta`\n"
            f"• Oraliq vaqt: `{delay_seconds} sek`"
        )

        # Orqa fonda (background) yuborish
        asyncio.create_task(send_broadcast(chats, text, repeat_count, delay_seconds))

    except Exception as e:
        await event.edit(
            f"⚠️ **Xato format!**\n\nIshlatish tartibi:\n`.avto | chat1,chat2 | Matn | Soni | Sekund`\n\nXatolik: `{e}`"
        )


# --- 3. REPLY KELGANDA HAVOLASINI FOYDALANUVCHIGA YUBORISH ---
@client.on(events.NewMessage)
async def catch_replies(event):
    if not event.is_group or not event.is_reply:
        return

    me = await client.get_me()

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

        try:
            await client.send_message(NOTIFY_TARGET, alert_text)
            print(f"[REPLY] Bildirishnoma @{NOTIFY_TARGET} ga yuborildi.")
        except Exception as e:
            print(f"[REPLY XATOLIK]: {e}")


async def main():
    await client.start()
    print("Userbot muvaffaqiyatli ishga tushdi...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())