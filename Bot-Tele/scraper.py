"""
scraper.py — Modul ekstraksi pesan dari grup Telegram menggunakan Telethon.

Mendukung dua mode:
1. History  — Scrape seluruh riwayat pesan (incremental, tidak duplikasi)
2. Listener — Real-time listener untuk pesan baru yang masuk
"""

import asyncio
import argparse
import sys
import io
from datetime import datetime, timezone
from typing import Optional

from telethon import TelegramClient, events
from telethon.tl.types import User, Channel, Chat
from dotenv import load_dotenv
import os

from database import init_db, insert_messages_batch, log_scrape_session, get_last_scraped_msg_id

# Fix encoding untuk Windows
if sys.platform == "win32" and not isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()

# ================== KONFIGURASI ==================
API_ID: int = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH: str = os.getenv("TELEGRAM_API_HASH", "")

# Parse TARGET_GROUP_IDS: comma-separated list of group IDs
_raw_ids: str = os.getenv("TARGET_GROUP_IDS", "")
TARGET_GROUP_IDS: list[int] = [
    int(gid.strip()) for gid in _raw_ids.split(",") if gid.strip()
]

SESSION_NAME: str = "scraper_session"
BATCH_SIZE: int = 100  # Jumlah pesan per batch insert ke DB
# ===================================================


def _extract_sender_name(sender: Optional[User | Channel | Chat]) -> str:
    """Ekstrak nama pengirim dari entity Telegram."""
    if sender is None:
        return "Unknown"
    if isinstance(sender, User):
        parts = [sender.first_name or "", sender.last_name or ""]
        name = " ".join(p for p in parts if p).strip()
        return name if name else (sender.username or "Unknown")
    if isinstance(sender, (Channel, Chat)):
        return sender.title or "Unknown"
    return "Unknown"


async def scrape_history(client: TelegramClient, group_id: int, min_id: int = 0) -> int:
    """
    Scrape seluruh riwayat pesan dari grup.

    Args:
        client: TelegramClient yang sudah terkoneksi
        group_id: ID grup target
        min_id: Message ID minimum (untuk incremental scraping)

    Returns:
        Total pesan yang berhasil disimpan
    """
    entity = await client.get_entity(group_id)
    print(f"\n📡 Scraping grup: {getattr(entity, 'title', group_id)}")
    print(f"   Min ID: {min_id} (incremental={'ya' if min_id > 0 else 'tidak'})")

    total_saved = 0
    batch: list[dict] = []
    msg_count = 0
    last_msg_id = 0

    async for message in client.iter_messages(entity, min_id=min_id, reverse=True):
        msg_count += 1

        # Skip pesan tanpa teks (media only, service messages, dll)
        if not message.text:
            continue

        sender = await message.get_sender()
        sender_name = _extract_sender_name(sender)
        sender_id = sender.id if sender else 0

        batch.append({
            "message_id": message.id,
            "sender_name": sender_name,
            "sender_id": sender_id,
            "text": message.text,
            "date": message.date.isoformat(),
            "reply_to_msg_id": message.reply_to_msg_id if message.reply_to else None,
        })

        last_msg_id = max(last_msg_id, message.id)

        # Batch insert setiap BATCH_SIZE pesan
        if len(batch) >= BATCH_SIZE:
            saved = insert_messages_batch(batch)
            total_saved += saved
            print(f"   💾 Batch: {saved}/{len(batch)} disimpan | Total scan: {msg_count}")
            batch.clear()

    # Sisanya
    if batch:
        saved = insert_messages_batch(batch)
        total_saved += saved
        print(f"   💾 Final batch: {saved}/{len(batch)} disimpan | Total scan: {msg_count}")

    # Log sesi
    if total_saved > 0 and last_msg_id > 0:
        log_scrape_session(group_id, last_msg_id, total_saved, mode="history")

    print(f"\n✅ Scraping selesai! Total disimpan: {total_saved} dari {msg_count} pesan di-scan.")
    return total_saved


async def start_listener(client: TelegramClient, group_ids: list[int]) -> None:
    """
    Real-time listener untuk pesan baru dari SEMUA grup target.
    Satu event handler menangani seluruh grup sekaligus.

    Args:
        client: TelegramClient yang sudah terkoneksi
        group_ids: List ID grup yang dipantau
    """
    # Resolve semua entity untuk mendapatkan judul grup
    titles: dict[int, str] = {}
    for gid in group_ids:
        try:
            entity = await client.get_entity(gid)
            titles[gid] = getattr(entity, "title", str(gid))
        except Exception as e:
            titles[gid] = str(gid)
            print(f"   ⚠️ Tidak bisa resolve grup {gid}: {e}")

    print(f"\n👂 Listener aktif untuk {len(group_ids)} grup:")
    for gid, title in titles.items():
        print(f"   • [{gid}] {title}")
    print("   Tekan Ctrl+C untuk berhenti.\n")

    @client.on(events.NewMessage(chats=group_ids))
    async def handler(event: events.NewMessage.Event) -> None:
        if not event.text:
            return

        # Identifikasi sumber grup
        chat_id = event.chat_id
        group_label = titles.get(chat_id, str(chat_id))

        sender = await event.get_sender()
        sender_name = _extract_sender_name(sender)
        sender_id = sender.id if sender else 0

        msg_data = [{
            "message_id": event.id,
            "sender_name": sender_name,
            "sender_id": sender_id,
            "text": event.text,
            "date": event.date.isoformat(),
            "reply_to_msg_id": event.reply_to_msg_id if event.reply_to else None,
        }]

        saved = insert_messages_batch(msg_data)
        if saved > 0:
            timestamp = event.date.strftime("%H:%M:%S")
            print(f"   [{timestamp}] [{group_label}] 💬 {sender_name}: {event.text[:80]}")
            log_scrape_session(chat_id, event.id, saved, mode="realtime")

    await client.run_until_disconnected()


async def main(mode: str) -> None:
    """Entry point utama scraper — mendukung multiple grup."""
    if not API_ID or not API_HASH:
        print("❌ Error: TELEGRAM_API_ID dan TELEGRAM_API_HASH belum diatur di .env")
        sys.exit(1)
    if not TARGET_GROUP_IDS:
        print("❌ Error: TARGET_GROUP_IDS belum diatur di .env")
        sys.exit(1)

    # Inisialisasi DB
    init_db()

    print(f"\n🎯 Target: {len(TARGET_GROUP_IDS)} grup → {TARGET_GROUP_IDS}")

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    try:
        await client.start()
        print("✅ Terkoneksi ke Telegram.")

        if mode == "history":
            # Scrape history semua grup secara berurutan (incremental)
            grand_total = 0
            for group_id in TARGET_GROUP_IDS:
                last_id = get_last_scraped_msg_id(group_id)
                min_id = last_id if last_id else 0
                saved = await scrape_history(client, group_id, min_id=min_id)
                grand_total += saved
            print(f"\n🏁 Total semua grup: {grand_total} pesan disimpan.")

        elif mode == "listener":
            # Satu listener untuk semua grup sekaligus
            await start_listener(client, TARGET_GROUP_IDS)

        elif mode == "both":
            # Scrape history semua grup dulu, lalu listener semua sekaligus
            grand_total = 0
            for group_id in TARGET_GROUP_IDS:
                last_id = get_last_scraped_msg_id(group_id)
                min_id = last_id if last_id else 0
                saved = await scrape_history(client, group_id, min_id=min_id)
                grand_total += saved
            print(f"\n🏁 History selesai. Total: {grand_total} pesan disimpan.")
            await start_listener(client, TARGET_GROUP_IDS)

    except KeyboardInterrupt:
        print("\n⏹ Dihentikan oleh user.")
    except Exception as e:
        print(f"❌ Error: {e}")
        raise
    finally:
        await client.disconnect()
        print("🔌 Koneksi Telegram ditutup.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telegram Group Message Scraper")
    parser.add_argument(
        "--mode",
        choices=["history", "listener", "both"],
        default="both",
        help="Mode operasi: history (scrape riwayat), listener (real-time), both (keduanya)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.mode))
