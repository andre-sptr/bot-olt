"""
bot.py — Telegram Bot Q&A berbasis riwayat percakapan grup.

Menggunakan python-telegram-bot v20+ (async) dan Gemini AI untuk menjawab
pertanyaan pengguna berdasarkan data yang tersimpan di database SQLite.
"""

import json
import logging
import sys
import os
import asyncio
from datetime import datetime

from google import genai
from google.genai import types
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode, ChatAction
from dotenv import load_dotenv

from database import (
    init_db,
    search_messages_fts,
    search_messages_like,
    get_recent_messages,
    get_messages_by_category,
    get_db_stats,
)
from processor import run_processor

load_dotenv()

# ================== KONFIGURASI ==================
BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME: str = "gemini-3-flash-preview"
MAX_CONTEXT_MESSAGES: int = 40
# ===================================================

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# Gemini Client (singleton)
_gemini_client: genai.Client | None = None

QA_SYSTEM_INSTRUCTION: str = (
    "Kamu adalah asisten AI yang menjawab pertanyaan berdasarkan riwayat "
    "percakapan grup Telegram. Jawab dengan ringkas, akurat, dan dalam "
    "Bahasa Indonesia. Jika informasi tidak ditemukan di riwayat, katakan "
    "dengan jelas bahwa data tersebut tidak ada di riwayat.\n\n"
    "Format jawaban:\n"
    "- Gunakan bullet points untuk kejelasan\n"
    "- Sebutkan nama pengirim dan tanggal jika relevan\n"
    "- Jangan mengarang informasi yang tidak ada di konteks"
)


def _get_gemini_client() -> genai.Client:
    """Konfigurasi dan return Gemini client (singleton) untuk Vertex AI Express."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(
            vertexai=True,
            api_key=GEMINI_API_KEY
        )
    return _gemini_client


def _generate_qa_response(prompt: str) -> str:
    """Generate jawaban Q&A dari Gemini."""
    client = _get_gemini_client()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.4,
            top_p=0.9,
            max_output_tokens=2048,
            system_instruction=QA_SYSTEM_INSTRUCTION,
        ),
    )
    return response.text


def _format_messages_context(messages: list) -> str:
    """Format pesan dari DB menjadi konteks teks untuk Gemini."""
    if not messages:
        return "(Tidak ada pesan relevan ditemukan)"

    lines: list[str] = []
    for msg in messages:
        date_str = msg["date"][:10] if msg["date"] else "?"
        sender = msg["sender_name"] or "Unknown"
        text = msg["text"][:300] if msg["text"] else ""
        category = msg.get("category", "")
        summary = msg.get("summary", "")

        line = f"[{date_str}] {sender}: {text}"
        if summary:
            line += f" (Ringkasan: {summary})"
        if category:
            line += f" [Kategori: {category}]"
        lines.append(line)

    return "\n".join(lines)


def _search_relevant_messages(query: str, limit: int = MAX_CONTEXT_MESSAGES) -> list:
    """Cari pesan relevan: coba FTS dulu, fallback ke LIKE."""
    results = search_messages_fts(query, limit=limit)
    if not results:
        results = search_messages_like(query, limit=limit)
    return results


# ==================== COMMAND HANDLERS ====================


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /start — Sambutan dan panduan."""
    welcome_text = (
        "👋 *Selamat datang di Telegram Group Intelligence Bot!*\n\n"
        "Saya dapat menjawab pertanyaan Anda berdasarkan riwayat "
        "percakapan grup yang tersimpan.\n\n"
        "📋 *Daftar Command:*\n"
        "🔹 `/tanya <pertanyaan>` — Tanya berdasarkan riwayat grup\n"
        "🔹 `/ringkasan` — Ringkasan pesan terbaru\n"
        "🔹 `/kategori <nama>` — Filter pesan berdasarkan kategori\n"
        "🔹 `/cari <keyword>` — Cari pesan berdasarkan kata kunci\n"
        "🔹 `/status` — Info statistik database\n"
        "🔹 `/proses` — Proses pesan baru dengan AI\n"
        "🔹 `/help` — Tampilkan bantuan\n\n"
        "💡 *Kategori tersedia:*\n"
        "INFO, DISKUSI, PERTANYAAN, PENGUMUMAN, INSTRUKSI, LAPORAN, SPAM, LAINNYA"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /help — Bantuan detail."""
    help_text = (
        "📖 *Panduan Penggunaan Bot*\n\n"
        "*1. Tanya Jawab AI:*\n"
        "```\n/tanya kapan jadwal meeting terakhir?\n```\n"
        "Bot akan mencari pesan relevan dan menjawab menggunakan AI.\n\n"
        "*2. Ringkasan:*\n"
        "```\n/ringkasan\n/ringkasan 20\n```\n"
        "Tampilkan ringkasan pesan terbaru (default 10).\n\n"
        "*3. Filter Kategori:*\n"
        "```\n/kategori PENGUMUMAN\n/kategori INFO\n```\n\n"
        "*4. Pencarian:*\n"
        "```\n/cari deadline proyek\n```\n\n"
        "*5. Statistik:*\n"
        "```\n/status\n```"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)


async def cmd_tanya(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /tanya — Q&A berbasis riwayat percakapan."""
    if not context.args:
        await update.message.reply_text(
            "❓ Gunakan: `/tanya <pertanyaan Anda>`\n"
            "Contoh: `/tanya kapan deadline proyek?`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    question = " ".join(context.args)
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        # Cari pesan relevan
        relevant_messages = _search_relevant_messages(question)

        if not relevant_messages:
            await update.message.reply_text(
                "🔍 Tidak ditemukan pesan relevan di riwayat grup untuk pertanyaan tersebut."
            )
            return

        # Bangun konteks
        context_text = _format_messages_context(relevant_messages)

        # Tanya Gemini
        prompt = (
            f"Berdasarkan riwayat percakapan grup Telegram berikut:\n\n"
            f"{context_text}\n\n"
            f"Pertanyaan pengguna: {question}\n\n"
            f"Jawab pertanyaan di atas berdasarkan riwayat di atas. "
            f"Sebutkan sumber (nama pengirim, tanggal) jika relevan."
        )

        answer = _generate_qa_response(prompt)

        reply = (
            f"🤖 *Jawaban:*\n\n{answer}\n\n"
            f"📊 _Berdasarkan {len(relevant_messages)} pesan relevan dari riwayat grup._"
        )
        await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Error cmd_tanya: {e}")
        await update.message.reply_text(f"❌ Terjadi kesalahan: {e}")


async def cmd_ringkasan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /ringkasan — Ringkasan pesan terbaru."""
    limit = 10
    if context.args:
        try:
            limit = min(int(context.args[0]), 50)
        except ValueError:
            pass

    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        messages = get_recent_messages(limit=limit)
        if not messages:
            await update.message.reply_text("📭 Belum ada pesan yang diproses di database.")
            return

        context_text = _format_messages_context(messages)

        prompt = (
            f"Buatkan ringkasan dari {len(messages)} pesan terbaru grup Telegram berikut:\n\n"
            f"{context_text}\n\n"
            f"Format ringkasan:\n"
            f"1. Poin-poin utama yang dibahas\n"
            f"2. Keputusan atau kesimpulan penting\n"
            f"3. Topik yang masih terbuka/belum selesai"
        )

        summary = _generate_qa_response(prompt)

        reply = (
            f"📝 *Ringkasan {len(messages)} Pesan Terbaru:*\n\n"
            f"{summary}"
        )
        await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Error cmd_ringkasan: {e}")
        await update.message.reply_text(f"❌ Terjadi kesalahan: {e}")


async def cmd_kategori(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /kategori — Lihat pesan berdasarkan kategori."""
    if not context.args:
        await update.message.reply_text(
            "📁 Gunakan: `/kategori <nama>`\n\n"
            "Kategori tersedia:\n"
            "INFO, DISKUSI, PERTANYAAN, PENGUMUMAN, INSTRUKSI, LAPORAN, SPAM, LAINNYA",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    category = context.args[0].upper()
    messages = get_messages_by_category(category, limit=15)

    if not messages:
        await update.message.reply_text(
            f"📭 Tidak ada pesan dengan kategori *{category}*.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    lines: list[str] = [f"📁 *Pesan Kategori: {category}* ({len(messages)} terbaru)\n"]
    for msg in messages:
        date_str = msg["date"][:10] if msg["date"] else "?"
        sender = msg["sender_name"] or "?"
        text = (msg["text"] or "")[:100]
        summary = msg["summary"] or ""
        line = f"🔹 `{date_str}` *{sender}*: {text}"
        if summary:
            line += f"\n   _📌 {summary}_"
        lines.append(line)

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_cari(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /cari — Pencarian pesan berdasarkan keyword."""
    if not context.args:
        await update.message.reply_text(
            "🔍 Gunakan: `/cari <keyword>`\n"
            "Contoh: `/cari deadline proyek`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    query = " ".join(context.args)
    results = _search_relevant_messages(query, limit=10)

    if not results:
        await update.message.reply_text(
            f'🔍 Tidak ditemukan hasil untuk "*{query}*".',
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    lines: list[str] = [f'🔍 *Hasil pencarian: "{query}"* ({len(results)} ditemukan)\n']
    for msg in results:
        date_str = msg["date"][:10] if msg["date"] else "?"
        sender = msg["sender_name"] or "?"
        text = (msg["text"] or "")[:120]
        lines.append(f"🔹 `{date_str}` *{sender}*: {text}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /status — Statistik database."""
    stats = get_db_stats()

    if not stats:
        await update.message.reply_text("❌ Tidak dapat mengambil statistik database.")
        return

    cat_lines: list[str] = []
    for cat, cnt in stats.get("categories", {}).items():
        cat_lines.append(f"   • {cat}: {cnt}")
    categories_str = "\n".join(cat_lines) if cat_lines else "   (belum ada)"

    reply = (
        f"📊 *Statistik Database*\n\n"
        f"📦 Total pesan: *{stats.get('total', 0)}*\n"
        f"✅ Diproses: *{stats.get('processed', 0)}*\n"
        f"⏳ Belum proses: *{stats.get('unprocessed', 0)}*\n\n"
        f"📅 Pesan tertua: `{stats.get('oldest_date', '-')}`\n"
        f"📅 Pesan terbaru: `{stats.get('latest_date', '-')}`\n\n"
        f"📁 *Kategori:*\n{categories_str}"
    )
    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)


async def cmd_proses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /proses — Trigger manual pemrosesan pesan oleh Gemini."""
    stats = get_db_stats()
    unprocessed = stats.get("unprocessed", 0)

    if unprocessed == 0:
        await update.message.reply_text("✅ Semua pesan sudah diproses!")
        return

    await update.message.reply_text(
        f"⏳ Memproses {unprocessed} pesan dengan Gemini AI...\n"
        f"Ini mungkin memakan waktu beberapa menit."
    )
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        # Jalankan processor di thread terpisah agar tidak blocking
        loop = asyncio.get_event_loop()
        total = await loop.run_in_executor(None, lambda: run_processor(max_batches=20))

        await update.message.reply_text(
            f"✅ Selesai! *{total}* pesan berhasil diproses.",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.error(f"Error cmd_proses: {e}")
        await update.message.reply_text(f"❌ Error saat memproses: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler untuk pesan teks biasa (tanpa command) — auto Q&A."""
    question = update.message.text
    if not question or len(question.strip()) < 3:
        return

    # Perlakukan sebagai pertanyaan langsung
    context.args = question.split()
    await cmd_tanya(update, context)


async def post_init(application: Application) -> None:
    """Set bot commands menu setelah inisialisasi."""
    commands = [
        BotCommand("start", "Mulai & panduan"),
        BotCommand("tanya", "Tanya berdasarkan riwayat grup"),
        BotCommand("ringkasan", "Ringkasan pesan terbaru"),
        BotCommand("kategori", "Filter berdasarkan kategori"),
        BotCommand("cari", "Cari pesan berdasarkan keyword"),
        BotCommand("status", "Statistik database"),
        BotCommand("proses", "Proses pesan baru dengan AI"),
        BotCommand("help", "Bantuan"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("✅ Bot commands menu berhasil diset.")


def main() -> None:
    """Entry point utama bot."""
    if not BOT_TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN belum diatur di .env")
        sys.exit(1)

    if not GEMINI_API_KEY:
        print("❌ Error: GEMINI_API_KEY belum diatur di .env")
        sys.exit(1)

    # Inisialisasi DB
    init_db()

    # Build application
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("tanya", cmd_tanya))
    app.add_handler(CommandHandler("ringkasan", cmd_ringkasan))
    app.add_handler(CommandHandler("kategori", cmd_kategori))
    app.add_handler(CommandHandler("cari", cmd_cari))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("proses", cmd_proses))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Start polling
    print("🤖 Bot siap! Menunggu pesan...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
