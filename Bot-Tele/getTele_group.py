"""
getTele_group.py — Utility untuk mendapatkan daftar ID grup/channel Telegram.

Jalankan script ini sekali untuk mengetahui TARGET_GROUP_IDS yang perlu
diisi di file .env sebelum menjalankan scraper.

Usage:
    python getTele_group.py
"""

import asyncio
import os
import sys
import io

from telethon import TelegramClient
from dotenv import load_dotenv

# Fix encoding untuk Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()

# ================== KONFIGURASI (dari .env) ==================
API_ID: int = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH: str = os.getenv("TELEGRAM_API_HASH", "")
SESSION_NAME: str = "getTele_group"
# =============================================================


async def main() -> None:
    if not API_ID or not API_HASH:
        print("❌ Error: TELEGRAM_API_ID dan TELEGRAM_API_HASH belum diatur di .env")
        sys.exit(1)

    print("📡 Memulai koneksi ke Telegram untuk mendapatkan ID grup...")
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    try:
        await client.start()
        print("✅ Koneksi berhasil! Mengambil daftar dialog...\n")

        dialogs = await client.get_dialogs()

        print("📋 Daftar Grup & Channel Anda:")
        print("=" * 60)
        for dialog in dialogs:
            if dialog.is_group or dialog.is_channel:
                kind = "Channel" if dialog.is_channel else "Grup"
                print(f"[{kind}] {dialog.title}")
                print(f"        ID: {dialog.id}")
                print()
        print("=" * 60)
        print("\n💡 Salin ID grup target ke TARGET_GROUP_IDS di file .env\n")

    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}")
        print("Pastikan Anda telah memasukkan nomor telepon dan kode verifikasi dengan benar.")
    finally:
        await client.disconnect()
        print("🔌 Koneksi ditutup.")


if __name__ == "__main__":
    asyncio.run(main())

