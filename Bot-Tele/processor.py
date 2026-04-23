"""
processor.py — Modul pemrosesan pesan menggunakan Gemini AI.

Mengambil pesan yang belum diproses dari database, mengirimnya ke Gemini
untuk kategorisasi, ringkasan, dan ekstraksi keyword, lalu menyimpan
hasilnya kembali ke database.
"""

import json
import sys
import time
import argparse
from typing import Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv
import os

from database import init_db, get_unprocessed_messages, update_processed_message, get_db_stats

load_dotenv()

# ================== KONFIGURASI ==================
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME: str = "gemini-2.5-flash"
BATCH_SIZE: int = 10  # Pesan per batch ke Gemini
RATE_LIMIT_DELAY: float = 1.0  # Delay antar API call (detik)
# ===================================================

# Kategori yang valid
VALID_CATEGORIES = frozenset({
    "INFO", "DISKUSI", "PERTANYAAN", "PENGUMUMAN",
    "INSTRUKSI", "LAPORAN", "SPAM", "LAINNYA",
})

SYSTEM_PROMPT = """Kamu adalah analis pesan Telegram yang ahli. Tugasmu adalah menganalisis pesan dan memberikan output JSON yang valid.

ATURAN:
1. Output HARUS berupa JSON array yang valid, tanpa teks tambahan.
2. Setiap elemen array adalah objek dengan field: index, category, summary, keywords, importance.
3. Category HARUS salah satu dari: INFO, DISKUSI, PERTANYAAN, PENGUMUMAN, INSTRUKSI, LAPORAN, SPAM, LAINNYA
4. Summary: ringkasan singkat 1 kalimat dalam Bahasa Indonesia.
5. Keywords: array 2-5 keyword relevan dalam Bahasa Indonesia.
6. Importance: skor 1-5 (1=tidak penting, 5=sangat penting).
7. Jika pesan tidak bermakna (hanya emoji, stiker, sapaan singkat), beri category LAINNYA dan importance 1."""

BATCH_PROMPT_TEMPLATE = """Analisis {count} pesan berikut dan berikan output JSON array:

{messages}

Output JSON array (satu objek per pesan, gunakan field "index" sesuai nomor pesan):"""


def _configure_gemini() -> genai.Client:
    """Konfigurasi dan return Gemini client instance."""
    if not GEMINI_API_KEY:
        print("❌ Error: GEMINI_API_KEY belum diatur di .env")
        sys.exit(1)

    return genai.Client(
        vertexai=True,
        api_key=GEMINI_API_KEY
    )


def _build_batch_prompt(messages: list) -> str:
    """Bangun prompt batch dari list pesan."""
    lines: list[str] = []
    for i, msg in enumerate(messages):
        sender = msg["sender_name"]
        text = msg["text"][:500]  # Truncate pesan panjang
        date = msg["date"]
        lines.append(f'[Pesan {i+1}] ({date}) {sender}: "{text}"')

    return BATCH_PROMPT_TEMPLATE.format(
        count=len(messages),
        messages="\n".join(lines),
    )


def _parse_gemini_response(response_text: str, batch_size: int) -> list[dict]:
    """Parse response JSON dari Gemini dengan error handling."""
    try:
        results = json.loads(response_text)
        if not isinstance(results, list):
            results = [results]

        parsed: list[dict] = []
        for item in results:
            category = str(item.get("category", "LAINNYA")).upper()
            if category not in VALID_CATEGORIES:
                category = "LAINNYA"

            importance = item.get("importance", 1)
            if not isinstance(importance, int) or importance < 1 or importance > 5:
                importance = 1

            keywords = item.get("keywords", [])
            if not isinstance(keywords, list):
                keywords = []

            parsed.append({
                "index": item.get("index", len(parsed) + 1),
                "category": category,
                "summary": str(item.get("summary", "")),
                "keywords": keywords,
                "importance": importance,
            })

        return parsed

    except json.JSONDecodeError as e:
        print(f"   ⚠️ JSON parse error: {e}")
        print(f"   Response: {response_text[:200]}...")
        return []


def process_batch(client: genai.Client, messages: list) -> int:
    """
    Proses satu batch pesan dengan Gemini.

    Returns:
        Jumlah pesan yang berhasil diproses
    """
    prompt = _build_batch_prompt(messages)

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                top_p=0.8,
                max_output_tokens=4096,
                response_mime_type="application/json",
                system_instruction=SYSTEM_PROMPT,
            ),
        )
        results = _parse_gemini_response(response.text, len(messages))

        if not results:
            print("   ⚠️ Gemini tidak mengembalikan hasil valid.")
            return 0

        processed = 0
        for result in results:
            idx = result["index"] - 1  # Convert ke 0-based
            if 0 <= idx < len(messages):
                msg = messages[idx]
                update_processed_message(
                    msg_db_id=msg["id"],
                    category=result["category"],
                    summary=result["summary"],
                    keywords=result["keywords"],
                    importance=result["importance"],
                )
                processed += 1

        return processed

    except Exception as e:
        print(f"   ❌ Gemini API error: {e}")
        return 0


def run_processor(max_batches: Optional[int] = None) -> int:
    """
    Jalankan processor untuk memproses semua pesan yang belum dikategorikan.

    Args:
        max_batches: Limit jumlah batch (None = proses semua)

    Returns:
        Total pesan yang diproses
    """
    init_db()
    client = _configure_gemini()

    total_processed = 0
    batch_num = 0

    print("\n🤖 Memulai Gemini AI Processor...")
    print(f"   Model: {MODEL_NAME} | Batch size: {BATCH_SIZE}\n")

    while True:
        if max_batches is not None and batch_num >= max_batches:
            print(f"\n⏹ Limit batch tercapai ({max_batches}).")
            break

        rows = get_unprocessed_messages(limit=BATCH_SIZE)
        if not rows:
            print("\n✅ Semua pesan sudah diproses!")
            break

        batch_num += 1
        messages = [dict(row) for row in rows]
        print(f"📦 Batch #{batch_num}: {len(messages)} pesan...")

        processed = process_batch(client, messages)
        total_processed += processed
        print(f"   ✅ {processed}/{len(messages)} berhasil diproses.")

        # Rate limiting
        time.sleep(RATE_LIMIT_DELAY)

    # Tampilkan statistik
    stats = get_db_stats()
    print(f"\n📊 Statistik final:")
    print(f"   Total pesan   : {stats.get('total', 0)}")
    print(f"   Diproses      : {stats.get('processed', 0)}")
    print(f"   Belum proses  : {stats.get('unprocessed', 0)}")
    if stats.get("categories"):
        print(f"   Kategori      :")
        for cat, cnt in stats["categories"].items():
            print(f"     - {cat}: {cnt}")

    return total_processed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gemini AI Message Processor")
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="Limit jumlah batch yang diproses (default: semua)",
    )
    args = parser.parse_args()

    total = run_processor(max_batches=args.max_batches)
    print(f"\n🎯 Selesai. Total diproses sesi ini: {total}")
