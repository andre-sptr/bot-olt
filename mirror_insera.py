from telethon import TelegramClient, events
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os

# ==========================================
# 1. KONFIGURASI TELEGRAM
# ==========================================
api_id = 35153027
api_hash = '275a7916b30391e446366433d5427086'
# -1003202563880 Real
# -4883113309 Test
ID_GRUP_TARGET = -1003202563880

client = TelegramClient('sesi_mirror_insera', api_id, api_hash)

# ==========================================
# 2. KONFIGURASI GOOGLE SHEETS
# ==========================================
scope = ["https://spreadsheets.google.com/feeds", 
         "https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive.file", 
         "https://www.googleapis.com/auth/drive"]

creds = ServiceAccountCredentials.from_json_keyfile_name("kunci_rahasia_google.json", scope)
client_gs = gspread.authorize(creds)

SPREADSHEET_ID = "1Jl-povDud6JKpb4qqB8pRIA0FbpB6lbNomhs9iL5F98"
GID_SHEET_TARGET = 0

# ==========================================
# 3. MANAJEMEN FOLDER & LOG
# ==========================================
FOLDER_LOG = "logs"
os.makedirs(FOLDER_LOG, exist_ok=True)

def tanggal_hari_ini():
    return datetime.now().strftime("%Y-%m-%d")

def nama_file_log():
    return os.path.join(FOLDER_LOG, "mirror_insera_log.txt")

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

def hapus_file(path_file):
    """Menghapus file dari server untuk menghemat storage VPS."""
    try:
        if os.path.exists(path_file):
            os.remove(path_file)
            catat_log(f"🗑️ File lokal '{path_file}' berhasil dihapus dari storage VPS.")
    except Exception as e:
        catat_log(f"⚠️ Gagal menghapus file lokal: {e}")


# ==========================================
# 4. LOGIK UTAMA BOT
# ==========================================
@client.on(events.NewMessage(chats=ID_GRUP_TARGET))
async def proses_dokumen_baru(event):
    if event.message.document:
        nama_file = event.message.file.name
        
        if nama_file and "Report TTR WSA" in nama_file and nama_file.endswith(".xlsx"):
            catat_log(f"🔔 File target terdeteksi: {nama_file}")
            
            lokasi_unduh = f"./{nama_file}"
                
            try:
                catat_log("-> Sedang mengunduh file dari Telegram...")
                await client.download_media(event.message, file=lokasi_unduh)
                catat_log("-> File berhasil diunduh. Sedang membaca dan menyaring data...")
                
                df = pd.read_excel(lokasi_unduh, sheet_name="Insera")
                df.columns = df.columns.astype(str).str.strip()
                
                cabang_target = ["BATAM", "PADANG", "BUKIT TINGGI", "BUKITTINGGI", "PEKANBARU", "DUMAI"]
                
                if "BRANCH" in df.columns:
                    df["BRANCH"] = df["BRANCH"].astype(str).str.strip().str.upper()
                    df = df[df["BRANCH"].isin(cabang_target)]
                else:
                    col_cc = df.columns[80]
                    df[col_cc] = df[col_cc].astype(str).str.strip().str.upper()
                    df = df[df[col_cc].isin(cabang_target)]
                
                df = df.iloc[:, :80]
                df = df.fillna("")
                
                data_untuk_dikirim = df.values.tolist()
                
                catat_log(f"-> Data berhasil difilter: {len(data_untuk_dikirim)} baris ditemukan. Bersiap memperbarui Google Sheets...")
                
                spreadsheet = client_gs.open_by_key(SPREADSHEET_ID)
                worksheet = spreadsheet.get_worksheet_by_id(GID_SHEET_TARGET)
                
                catat_log("-> Menghapus data lama di Google Sheets (Hanya area A2:CB)...")
                worksheet.batch_clear(["A2:CB"])
                
                if len(data_untuk_dikirim) > 0:
                    catat_log("-> Menulis data baru ke Google Sheets mulai dari baris 2...")
                    worksheet.update(range_name='A2', values=data_untuk_dikirim)
                    catat_log(f"✅ SUKSES! {len(data_untuk_dikirim)} baris data berhasil ditimpa ke sheet.")
                else:
                    catat_log("⚠️ Proses selesai. Namun tidak ada data yang masuk kriteria (Cabang tidak ditemukan).")

            except Exception as e:
                catat_log(f"❌ TERJADI KESALAHAN saat memproses {nama_file}: {e}")
                
            finally:
                if lokasi_unduh:
                    hapus_file(lokasi_unduh)

# ==========================================
# 5. MENJALANKAN BOT
# ==========================================
async def main():
    catat_log("Memulai koneksi ke Telegram...")
    await client.get_dialogs() 
    catat_log("🚀 Program Pemantau Report TTR WSA Aktif! Mendengarkan grup...")
    await client.run_until_disconnected()

with client:
    client.loop.run_until_complete(main())