import os
import json
import time
import requests
import base64
from datetime import datetime
from flask import Flask, request, jsonify
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)

# ================== KONFIGURASI WAHA ==================
WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id"
WAHA_SESSION = "OLTReport"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"

# ================== KONFIGURASI GOOGLE SLIDES ==========
FILE_KREDENSIAL = "kunci_rahasia_google.json"
SCOPES = ['https://www.googleapis.com/auth/presentations.readonly']
PRESENTATION_ID = "10V4c-yYukRfD1Yq6XyUqPyItavFzubbqXEm8BLNYqRk"

# ================== KONFIGURASI ADMIN & KEAMANAN =======
ADMIN_NUMBERS = [
    "6282387025429@c.us",
    "232701932138501@lid",
    "6282269171322@c.us",
]

PASSWORD_BOT = "T1FSBT"

# ======================================================

FOLDER_GAMBAR = "images"
FOLDER_LOG = "logs"
FOLDER_DATA = "data"
FILE_COMMANDS = os.path.join(FOLDER_DATA, "commands.json")
FILE_SESSIONS = os.path.join(FOLDER_DATA, "sessions.json")

os.makedirs(FOLDER_GAMBAR, exist_ok=True)
os.makedirs(FOLDER_LOG, exist_ok=True)
os.makedirs(FOLDER_DATA, exist_ok=True)


def tanggal_hari_ini():
    return datetime.now().strftime("%Y-%m-%d")


def nama_file_log():
    return os.path.join(FOLDER_LOG, "bot-topologi-isp_log.txt")


def catat_log(pesan):
    """Mencatat log dengan fitur auto-reset jika masuk hari baru."""
    waktu = datetime.now().strftime("%H:%M:%S")
    tanggal_sekarang = tanggal_hari_ini()
    pesan_log = f"[{waktu}] {pesan}"
    print(pesan_log)

    file_log = nama_file_log()
    mode = "a"

    if os.path.exists(file_log):
        timestamp_modifikasi = os.path.getmtime(file_log)
        tanggal_modifikasi = datetime.fromtimestamp(timestamp_modifikasi).strftime("%Y-%m-%d")
        
        if tanggal_modifikasi != tanggal_sekarang:
            mode = "w"

    with open(file_log, mode, encoding="utf-8") as f:
        if mode == "w":
            f.write(f"=== Log Hari Ini: {tanggal_sekarang} ===\n")
        f.write(pesan_log + "\n")


# ================== FUNGSI SESI LOGIN ==================
def load_sessions():
    """Memuat data sesi login dari file JSON."""
    if os.path.exists(FILE_SESSIONS):
        try:
            with open(FILE_SESSIONS, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            catat_log(f"⚠️ Error loading sessions: {e}")
            return {}
    return {}


def save_sessions(sessions):
    """Menyimpan data sesi login ke file JSON."""
    try:
        with open(FILE_SESSIONS, 'w', encoding='utf-8') as f:
            json.dump(sessions, f, indent=2)
    except Exception as e:
        catat_log(f"❌ Error saving sessions: {e}")


def is_authenticated(chat_id):
    """
    Mengecek apakah user sudah memasukkan sandi hari ini.
    Mengembalikan True jika tanggal login user sama dengan tanggal hari ini.
    """
    sessions = load_sessions()
    if chat_id in sessions:
        if sessions[chat_id] == tanggal_hari_ini():
            return True
    return False


def authenticate_user(chat_id):
    """Mencatat nomor WA beserta tanggal login hari ini ke dalam sistem."""
    sessions = load_sessions()
    sessions[chat_id] = tanggal_hari_ini()
    save_sessions(sessions)
# =============================================================


def load_commands():
    """Memuat commands dari file JSON."""
    if os.path.exists(FILE_COMMANDS):
        try:
            with open(FILE_COMMANDS, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            catat_log(f"⚠️ Error loading commands: {e}")
            return {}
    else:
        default_commands = {
            "topologi_isp_batam": {
                "slide_id": "g3c8f0e7723c_0_0",
                "description": "Topologi ISP Batam",
                "created_by": "system",
                "created_at": datetime.now().isoformat()
            }
        }
        save_commands(default_commands)
        return default_commands


def save_commands(commands):
    """Menyimpan commands ke file JSON."""
    try:
        with open(FILE_COMMANDS, 'w', encoding='utf-8') as f:
            json.dump(commands, f, indent=2, ensure_ascii=False)
        catat_log("✅ Commands berhasil disimpan")
        return True
    except Exception as e:
        catat_log(f"❌ Error saving commands: {e}")
        return False


def is_admin(chat_id):
    """Cek apakah user adalah admin."""
    return chat_id in ADMIN_NUMBERS


def get_all_slides():
    """Mendapatkan daftar semua slide dari presentation."""
    try:
        creds = Credentials.from_service_account_file(FILE_KREDENSIAL, scopes=SCOPES)
        service = build('slides', 'v1', credentials=creds)
        
        presentation = service.presentations().get(presentationId=PRESENTATION_ID).execute()
        slides = presentation.get('slides', [])
        
        slide_list = []
        for idx, slide in enumerate(slides, start=1):
            slide_info = {
                'nomor': idx,
                'object_id': slide['objectId'],
                'title': ''
            }
            
            for element in slide.get('pageElements', []):
                if 'shape' in element:
                    shape = element['shape']
                    if shape.get('shapeType') == 'TEXT_BOX':
                        text_elements = shape.get('text', {}).get('textElements', [])
                        for text_elem in text_elements:
                            if 'textRun' in text_elem:
                                content = text_elem['textRun'].get('content', '').strip()
                                if content and len(content) > 5:
                                    slide_info['title'] = content[:50]  
                                    break
                    if slide_info['title']:
                        break
            
            slide_list.append(slide_info)
        
        catat_log(f"✅ Berhasil mendapatkan {len(slide_list)} slide dari presentation")
        return slide_list
    
    except Exception as e:
        catat_log(f"❌ Error getting slides: {str(e)}")
        return []


def hapus_gambar(path_gambar):
    """Menghapus gambar dari server untuk menghemat storage VPS."""
    try:
        if os.path.exists(path_gambar):
            os.remove(path_gambar)
            catat_log("🗑️ File gambar berhasil dihapus dari storage VPS.")
    except Exception as e:
        catat_log(f"⚠️ Gagal menghapus file gambar: {e}")


def ambil_gambar_slide_via_api(slide_object_id, output_path):
    try:
        creds = Credentials.from_service_account_file(FILE_KREDENSIAL, scopes=SCOPES)
        service = build('slides', 'v1', credentials=creds)
        
        response = service.presentations().pages().getThumbnail(
            presentationId=PRESENTATION_ID,
            pageObjectId=slide_object_id,
            thumbnailProperties_thumbnailSize='LARGE'
        ).execute()
        
        image_url = response.get('contentUrl')
        
        if not image_url:
            catat_log("❌ URL Thumbnail tidak ditemukan dari response API.")
            return False
            
        img_data = requests.get(image_url).content
        with open(output_path, 'wb') as handler:
            handler.write(img_data)
            
        catat_log("✅ Gambar slide berhasil diunduh.")
        return True
    except Exception as e:
        catat_log(f"❌ Error API Slides: {str(e)}")
        return False


def kirim_wa_gambar(chat_id, caption, file_path):
    url = f"{WAHA_URL.rstrip('/')}/api/sendImage"
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": WAHA_API_KEY
    }
    
    try:
        with open(file_path, "rb") as f:
            encoded_string = base64.b64encode(f.read()).decode("utf-8")
            
        payload = {
            "session": WAHA_SESSION,
            "chatId": chat_id,
            "file": {
                "mimetype": "image/png",
                "filename": os.path.basename(file_path),
                "data": encoded_string
            },
            "caption": caption
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code in [200, 201]:
            catat_log("✅ Berhasil mengirim gambar topologi ke WA!")
        else:
            catat_log(f"❌ Gagal mengirim gambar. Status: {response.status_code}")
        return response.status_code
    except Exception as e:
        catat_log(f"❌ Error saat mengirim gambar WA: {e}")
        return None


def kirim_wa_teks(chat_id, teks):
    url = f"{WAHA_URL.rstrip('/')}/api/sendText"
    headers = {"Content-Type": "application/json", "X-Api-Key": WAHA_API_KEY}
    payload = {"session": WAHA_SESSION, "chatId": chat_id, "text": teks}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        return response.status_code
    except Exception as e:
        catat_log(f"❌ Error saat mengirim teks WA: {e}")
        return None


def handle_help_command(chat_id, is_admin_user=False):
    """Menampilkan menu bantuan."""
    commands = load_commands()
    
    help_text = "🤖 *Bot Topologi Network Automation*\n\n"
    help_text += "📋 *Perintah Umum:*\n"
    help_text += "• `/help` - Tampilkan menu ini\n"
    help_text += "• `/list` - Lihat semua command\n"
    help_text += "• `/slides` - Lihat semua slide\n\n"
    
    if is_admin_user:
        help_text += "👑 *Perintah Admin:*\n"
        help_text += "• `/add [nomor_slide] [nama_command]`\n"
        help_text += "• `/delete [nama_command]`\n"
        help_text += "• `/reload`\n\n"
    
    help_text += f"📊 *Total Command Tersedia:* {len(commands)}\n\n"
    help_text += "💡 *Cara Pakai:*\n"
    help_text += "Ketik nama command untuk mendapatkan gambar topologi.\n"
    help_text += "Contoh: `topologi_isp_batam`"
    
    kirim_wa_teks(chat_id, help_text)


def handle_list_command(chat_id):
    """Menampilkan daftar semua command."""
    commands = load_commands()
    
    if not commands:
        kirim_wa_teks(chat_id, "⚠️ Belum ada command yang terdaftar.")
        return
    
    list_text = "📋 *Daftar Command Topologi:*\n\n"
    for idx, (cmd_name, cmd_data) in enumerate(commands.items(), start=1):
        desc = cmd_data.get('description', 'Tidak ada deskripsi')
        list_text += f"{idx}. `{cmd_name}`\n   _{desc}_\n\n"
    
    list_text += f"\n💡 Ketik nama command untuk mendapatkan gambar."
    kirim_wa_teks(chat_id, list_text)


def handle_slides_command(chat_id):
    """Menampilkan daftar semua slide dari presentation."""
    kirim_wa_teks(chat_id, "⏳ Mengambil daftar slide dari Google Slides...")
    
    slides = get_all_slides()
    
    if not slides:
        kirim_wa_teks(chat_id, "❌ Gagal mengambil daftar slide. Coba lagi nanti.")
        return
    
    slides_text = "📊 *Daftar Slide di Presentation:*\n\n"
    for slide in slides:
        title = slide['title'] if slide['title'] else "_(tanpa judul)_"
        slides_text += f"*{slide['nomor']}.* {title}\n"
        slides_text += f"   ID: `{slide['object_id']}`\n\n"
    
    slides_text += f"\n💡 Total: {len(slides)} slide"
    kirim_wa_teks(chat_id, slides_text)


def handle_add_command(chat_id, args):
    """Menambahkan command baru (admin only)."""
    if len(args) < 2:
        kirim_wa_teks(chat_id, "❌ Format salah!\n\nContoh:\n`/add 3 topologi_medan`\natau\n`/add g3c8f0e7723c_0_0 topologi_batam`")
        return
    
    slide_identifier = args[0]
    command_name = args[1].lower().strip()
    description = " ".join(args[2:]) if len(args) > 2 else f"Topologi dari slide {slide_identifier}"
    
    if not command_name.replace('_', '').isalnum():
        kirim_wa_teks(chat_id, "❌ Nama command hanya boleh huruf, angka, dan underscore!")
        return
    
    slide_object_id = None
    if slide_identifier.isdigit():
        slides = get_all_slides()
        slide_num = int(slide_identifier)
        if 1 <= slide_num <= len(slides):
            slide_object_id = slides[slide_num - 1]['object_id']
        else:
            kirim_wa_teks(chat_id, f"❌ Nomor slide {slide_num} tidak ditemukan! Gunakan `/slides` untuk melihat daftar.")
            return
    else:
        slide_object_id = slide_identifier
    
    commands = load_commands()
    
    if command_name in commands:
        kirim_wa_teks(chat_id, f"⚠️ Command `{command_name}` sudah ada!\n\nGunakan `/delete {command_name}` dulu jika ingin menggantinya.")
        return
    
    commands[command_name] = {
        "slide_id": slide_object_id,
        "description": description,
        "created_by": chat_id,
        "created_at": datetime.now().isoformat()
    }
    
    if save_commands(commands):
        success_text = f"✅ *Command baru berhasil ditambahkan!*\n\n"
        success_text += f"📌 Command: `{command_name}`\n"
        success_text += f"📄 Slide ID: `{slide_object_id}`\n"
        success_text += f"📝 Deskripsi: {description}\n\n"
        success_text += f"💡 User sekarang bisa ketik `{command_name}` untuk mendapatkan gambar."
        kirim_wa_teks(chat_id, success_text)
    else:
        kirim_wa_teks(chat_id, "❌ Gagal menyimpan command. Cek log server.")


def handle_delete_command(chat_id, args):
    """Menghapus command (admin only)."""
    if len(args) < 1:
        kirim_wa_teks(chat_id, "❌ Format salah!\n\nContoh: `/delete topologi_medan`")
        return
    
    command_name = args[0].lower().strip()
    commands = load_commands()
    
    if command_name not in commands:
        kirim_wa_teks(chat_id, f"❌ Command `{command_name}` tidak ditemukan!")
        return
    
    deleted_cmd = commands.pop(command_name)
    
    if save_commands(commands):
        delete_text = f"🗑️ *Command berhasil dihapus!*\n\n"
        delete_text += f"📌 Command: `{command_name}`\n"
        delete_text += f"📝 Deskripsi: {deleted_cmd.get('description', 'N/A')}"
        kirim_wa_teks(chat_id, delete_text)
    else:
        kirim_wa_teks(chat_id, "❌ Gagal menghapus command. Cek log server.")


def handle_reload_command(chat_id):
    """Reload daftar slide dari Google (admin only)."""
    kirim_wa_teks(chat_id, "🔄 Memuat ulang daftar slide dari Google Slides...")
    
    slides = get_all_slides()
    
    if slides:
        reload_text = f"✅ *Berhasil memuat {len(slides)} slide*\n\n"
        reload_text += "Gunakan `/slides` untuk melihat daftar lengkap."
        kirim_wa_teks(chat_id, reload_text)
    else:
        kirim_wa_teks(chat_id, "❌ Gagal memuat slide. Periksa kredensial dan ID presentation.")


@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    
    if data and data.get("event") == "message":
        payload = data.get("payload", {})
        chat_id = payload.get("from")
        body = payload.get("body", "").strip()
        dari_bot_sendiri = payload.get("fromMe", False)
        
        if chat_id and ("@c.us" in chat_id or "@lid" in chat_id) and not dari_bot_sendiri:
            
            # ================= LOGIKA AUTENTIKASI KATA SANDI =================
            if not is_authenticated(chat_id):
                if body == PASSWORD_BOT:
                    authenticate_user(chat_id)
                    pesan_sukses = "✅ *Sandi Diterima!*\n\nAkses bot Anda telah dibuka untuk hari ini. Silakan ketik `/help` untuk melihat panduan atau langsung ketik nama command topologi."
                    kirim_wa_teks(chat_id, pesan_sukses)
                    catat_log(f"🔓 User {chat_id} berhasil login dengan sandi.")
                else:
                    catat_log(f"🔒 Pesan diabaikan, {chat_id} belum memasukkan sandi hari ini.")
                
                return jsonify({"status": "ok"}), 200
            # ========================================================================
            
            is_admin_user = is_admin(chat_id)
            
            parts = body.split()
            command = parts[0].lower() if parts else ""
            args = parts[1:] if len(parts) > 1 else []
            
            catat_log(f"📨 Pesan dari {chat_id}: {body}")
            
            if command == "/help":
                handle_help_command(chat_id, is_admin_user)
            
            elif command == "/list":
                handle_list_command(chat_id)
            
            elif command == "/slides":
                handle_slides_command(chat_id)
            
            elif command == "/add":
                if is_admin_user:
                    handle_add_command(chat_id, args)
                else:
                    kirim_wa_teks(chat_id, "🚫 Maaf, hanya admin yang bisa menggunakan perintah ini.")
            
            elif command == "/delete":
                if is_admin_user:
                    handle_delete_command(chat_id, args)
                else:
                    kirim_wa_teks(chat_id, "🚫 Maaf, hanya admin yang bisa menggunakan perintah ini.")
            
            elif command == "/reload":
                if is_admin_user:
                    handle_reload_command(chat_id)
                else:
                    kirim_wa_teks(chat_id, "🚫 Maaf, hanya admin yang bisa menggunakan perintah ini.")
            
            else:
                commands = load_commands()
                command_lower = body.lower().strip()
                
                if command_lower in commands:
                    catat_log(f"🎯 Memproses command: {command_lower} dari {chat_id}")
                    
                    cmd_data = commands[command_lower]
                    slide_id = cmd_data["slide_id"]
                    description = cmd_data.get("description", command_lower)
                    
                    filename = f"topologi_{int(time.time())}.png"
                    output_path = os.path.join(FOLDER_GAMBAR, filename)
                    
                    kirim_wa_teks(chat_id, f"⏳ Sedang memproses gambar untuk *{description}*... Mohon tunggu.")
                    
                    success = ambil_gambar_slide_via_api(slide_id, output_path)
                    
                    if success:
                        caption = f"✅ *{description.upper()}*\n"
                        caption += f"📅 Dicetak pada: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        caption += f"🤖 Bot Topologi Automation"
                        kirim_wa_gambar(chat_id, caption, output_path)
                    else:
                        kirim_wa_teks(chat_id, "❌ Gagal mengambil screenshot. Pastikan bot memiliki akses viewer.")
                    
                    hapus_gambar(output_path)
                
                elif body.strip() and not body.startswith("/"):
                    kirim_wa_teks(chat_id, f"❓ Command `{body}` tidak dikenali.\n\nKetik `/help` untuk melihat panduan atau `/list` untuk melihat command yang tersedia.")

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    print("=" * 60)
    print("  🤖 Bot Topologi Network Automation v2.0")
    print("  📡 Dynamic Command Management System")
    print("  🔒 Password Protection Enabled")
    print("=" * 60)
    
    commands = load_commands()
    sessions = load_sessions()
    print(f"  ✅ {len(commands)} command dimuat dari database")
    print(f"  ✅ {len(sessions)} sesi user dimuat")
    print(f"  🔐 {len(ADMIN_NUMBERS)} admin terdaftar")
    print("=" * 60)
    
    app.run(host="0.0.0.0", port=5000)