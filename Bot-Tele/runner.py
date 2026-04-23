"""
runner.py — Orchestrator utama untuk menjalankan Scraper + Processor + Bot secara bersamaan.

Didesain untuk deployment VPS Ubuntu 24/7:
- Scraper (Telethon listener) berjalan di background
- Processor otomatis berjalan setiap 15 menit via scheduler
- Bot Telegram berjalan di foreground
"""

import asyncio
import logging
import sys
import os
import signal
from threading import Thread

from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from database import init_db
from processor import run_processor

load_dotenv()

# ================== KONFIGURASI ==================
PROCESS_INTERVAL_MINUTES: int = 15  # Interval auto-process (menit)
PROCESS_MAX_BATCHES: int = 50       # Max batch per sesi auto-process
# ===================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def scheduled_process() -> None:
    """Callback scheduler: jalankan Gemini processor."""
    logger.info("⏰ Scheduler: Memulai auto-process...")
    try:
        total = run_processor(max_batches=PROCESS_MAX_BATCHES)
        logger.info(f"⏰ Scheduler: Selesai, {total} pesan diproses.")
    except Exception as e:
        logger.error(f"⏰ Scheduler error: {e}")


def start_scraper_listener() -> None:
    """Jalankan Telethon real-time listener di thread terpisah."""
    from scraper import main as scraper_main

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(scraper_main("listener"))
    except Exception as e:
        logger.error(f"Scraper listener error: {e}")
    finally:
        loop.close()


def main() -> None:
    """Entry point utama runner."""
    # Import di sini untuk membaca .env yang sudah di-load
    from scraper import TARGET_GROUP_IDS

    print("=" * 60)
    print("  🚀 Telegram Group Intelligence Bot — Runner")
    print(f"  📡 Memantau {len(TARGET_GROUP_IDS)} grup")
    for gid in TARGET_GROUP_IDS:
        print(f"     • {gid}")
    print("=" * 60)

    # Inisialisasi database
    init_db()

    # 1. Setup scheduler untuk auto-process
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        scheduled_process,
        trigger=IntervalTrigger(minutes=PROCESS_INTERVAL_MINUTES),
        id="gemini_processor",
        name="Gemini AI Processor",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"⏰ Scheduler aktif: proses setiap {PROCESS_INTERVAL_MINUTES} menit")

    # 2. Jalankan initial processing
    logger.info("📦 Menjalankan initial processing...")
    try:
        run_processor(max_batches=10)
    except Exception as e:
        logger.warning(f"Initial processing warning: {e}")

    # 3. Start scraper listener di background thread
    scraper_thread = Thread(target=start_scraper_listener, daemon=True, name="scraper")
    scraper_thread.start()
    logger.info("👂 Scraper listener dimulai di background")

    # 4. Jalankan bot di foreground (blocking)
    from bot import main as bot_main

    try:
        logger.info("🤖 Memulai Telegram Bot...")
        bot_main()
    except KeyboardInterrupt:
        logger.info("⏹ Dihentikan oleh user (Ctrl+C)")
    finally:
        scheduler.shutdown(wait=False)
        logger.info("🔌 Semua service dihentikan.")


if __name__ == "__main__":
    main()
