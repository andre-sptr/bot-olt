# Telegram Group Intelligence Bot

Bot Telegram cerdas yang mengekstrak, mengategorikan, dan menyimpan pesan dari grup Telegram menggunakan **Gemini AI**, lalu menjawab pertanyaan pengguna berdasarkan riwayat percakapan tersebut.

## Fitur

- 📡 **Scraping** — Ekstraksi seluruh riwayat pesan grup (incremental)
- 👂 **Real-time Listener** — Tangkap pesan baru secara otomatis
- 🤖 **Gemini AI** — Kategorisasi, ringkasan, dan ekstraksi keyword otomatis
- 🔍 **Full-Text Search** — Pencarian cepat dengan SQLite FTS5
- 💬 **Bot Q&A** — Tanya jawab berdasarkan riwayat via Telegram Bot
- 🔄 **Auto-Process** — Scheduler otomatis setiap 15 menit

## Prasyarat

- Python 3.11+
- Akun Telegram + API credentials
- Bot Token dari [@BotFather](https://t.me/BotFather)
- Gemini API Key dari [Google AI Studio](https://aistudio.google.com/app/apikey)

## Setup di VPS Ubuntu

```bash
# 1. Clone / upload project
cd /root
git clone <repo-url> Bot-Tele  # atau upload via scp

# 2. Setup virtual environment
cd Bot-Tele
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Konfigurasi environment
cp .env.example .env   # atau edit langsung .env
nano .env               # isi semua credential

# 5. Test koneksi & cek ID grup
python getTele_group.py

# 6. Jalankan scraping history pertama kali
python scraper.py --mode history

# 7. Proses pesan dengan Gemini AI
python processor.py

# 8. Test bot
python bot.py
```

## Deployment 24/7 (Systemd)

```bash
# Copy service file
sudo cp tele-bot.service /etc/systemd/system/

# Sesuaikan path di service file jika perlu
sudo nano /etc/systemd/system/tele-bot.service

# Enable dan start
sudo systemctl daemon-reload
sudo systemctl enable tele-bot
sudo systemctl start tele-bot

# Cek status
sudo systemctl status tele-bot

# Cek log
sudo journalctl -u tele-bot -f
```

## Commands Bot

| Command | Deskripsi |
|---|---|
| `/start` | Sambutan & panduan |
| `/tanya <pertanyaan>` | Tanya berdasarkan riwayat grup |
| `/ringkasan [jumlah]` | Ringkasan pesan terbaru |
| `/kategori <nama>` | Filter berdasarkan kategori |
| `/cari <keyword>` | Cari pesan |
| `/status` | Statistik database |
| `/proses` | Trigger AI processing manual |
| `/help` | Bantuan |

## Struktur Project

```
Bot-Tele/
├── .env                 # Credential (JANGAN commit!)
├── .gitignore
├── requirements.txt
├── getTele_group.py     # Utility: cek ID grup
├── scraper.py           # Ekstraksi pesan Telegram
├── processor.py         # Gemini AI processor
├── database.py          # SQLite + FTS5 manager
├── bot.py               # Telegram Bot Q&A
├── runner.py            # Orchestrator (scraper + processor + bot)
├── tele-bot.service     # Systemd service file
└── data/
    └── messages.db      # Database (auto-created)
```
