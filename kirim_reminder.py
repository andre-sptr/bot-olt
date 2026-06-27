import os
import requests
from datetime import datetime

try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
except ImportError:
    print("Harap install gspread dan oauth2client: pip install gspread oauth2client")
    exit(1)

# ================== KONFIGURASI WAHA ==================
WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id"
WAHA_SESSION = "OLTReport"  # Sesuaikan dengan session WAHA yang aktif
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"
GROUP_ID_TUJUAN = "120363425048343238@g.us"
# ======================================================

SPREADSHEET_ID = "1PsJJCJfAdrELwarSsLsYfjdKn_0pRhFrO6B_4q6RDPI"
FILE_KREDENSIAL = "kunci_rahasia_google.json"

def get_google_sheet_data():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive"
    ]
    # Autentikasi menggunakan file credential JSON
    creds = ServiceAccountCredentials.from_json_keyfile_name(FILE_KREDENSIAL, scope)
    client = gspread.authorize(creds)
    
    # Buka spreadsheet berdasarkan ID dan ambil sheet pertama (index 0)
    sheet = client.open_by_key(SPREADSHEET_ID).get_worksheet(0)
    return sheet.get_all_values()

def parse_date(date_str):
    if not date_str:
        return None
    
    # Translate nama bulan Indonesia ke English agar strptime bisa memproses
    BULAN_ID_KE_EN = {
        "Januari": "January", "Februari": "February", "Maret": "March",
        "April": "April", "Mei": "May", "Juni": "June",
        "Juli": "July", "Agustus": "August", "September": "September",
        "Oktober": "October", "November": "November", "Desember": "December",
        "Jan": "Jan", "Feb": "Feb", "Mar": "Mar", "Apr": "Apr",
        "Mei": "May", "Jun": "Jun", "Jul": "Jul", "Agu": "Aug",
        "Ags": "Aug", "Agt": "Aug", "Sep": "Sep", "Okt": "Oct",
        "Nov": "Nov", "Des": "Dec",
    }
    
    cleaned = date_str.strip()
    for id_bulan, en_bulan in BULAN_ID_KE_EN.items():
        if id_bulan in cleaned:
            cleaned = cleaned.replace(id_bulan, en_bulan)
            break
    
    # Beberapa format tanggal yang mungkin ada di Google Sheets
    formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", 
        "%d %b %Y", "%d %B %Y", "%Y/%m/%d", "%d-%b-%y"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None

def kirim_waha_teks(chat_id, teks):
    url = f"{WAHA_URL.rstrip('/')}/api/sendText"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Api-Key": WAHA_API_KEY,
    }
    payload = {
        "session": WAHA_SESSION,
        "chatId": chat_id,
        "text": teks
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code in [200, 201]:
            print("✅ Pesan berhasil dikirim ke WA.")
        else:
            print(f"❌ Gagal mengirim pesan. Status: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"❌ Error mengirim pesan ke WA: {e}")

def main():
    print("=" * 50)
    print("Mengecek Reminder Tanggal Kontrak...")
    print("=" * 50)
    
    try:
        data = get_google_sheet_data()
    except Exception as e:
        print(f"❌ Gagal mengambil data dari Google Sheets: {e}")
        return

    today = datetime.now()
    today_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
    is_monday = today.weekday() == 0  # 0 berarti hari Senin
    
    # Daftar perangkat berdasarkan sisa waktu kontrak
    h30_items = []
    h90_items = []

    # Loop setiap baris, dimulai dari baris ke-3 (indeks 2)
    # Format Google Sheets yg diminta: C (District) = index 2, E (Perangkat) = index 4, I (Tgl Kontrak) = index 8
    for i, row in enumerate(data):
        if i < 2:
            continue
        
        # Skip jika panjang kolom kurang (belum diisi sampai kolom I)
        if len(row) <= 8:
            continue
            
        district = row[2].strip()
        perangkat = row[4].strip()
        tgl_str = row[8].strip()
        
        if not district or not perangkat or not tgl_str:
            continue
            
        tgl_kontrak = parse_date(tgl_str)
        if not tgl_kontrak:
            # Jika ada format aneh, skip saja
            continue
            
        # Hitung selisih hari
        days_left = (tgl_kontrak - today_date).days
        
        item = {
            "district": district,
            "perangkat": perangkat,
            "tgl": tgl_str,
            "days_left": days_left
        }
        
        # Aturan Reminder:
        # H-30 & Expired: <= 30 hari (diingatkan setiap hari)
        if days_left <= 30:
            h30_items.append(item)
        # H-90: antara 31 sampai 90 hari (diingatkan setiap minggu, yaitu hari Senin)
        elif 30 < days_left <= 90:
            h90_items.append(item)

    pesan_terkirim = False
    
    # ==========================
    # 1. Kirim Pesan H-30 (Harian)
    # ==========================
    if h30_items:
        pesan = "⚠️ *REMINDER H-30 & EXPIRED KONTRAK* ⚠️\n"
        pesan += "Berikut adalah daftar perangkat/alpro yang kontraknya sudah habis atau akan habis dalam 30 hari ke depan:\n\n"
        
        # Kelompokkan berdasarkan distrik agar lebih rapi
        grouped_h30 = {}
        for it in h30_items:
            grouped_h30.setdefault(it["district"], []).append(it)
            
        for dist, items in grouped_h30.items():
            pesan += f"📍 *{dist}*\n"
            for it in items:
                if it['days_left'] < 0:
                    status = f"Sudah Expired {-it['days_left']} hari lalu"
                elif it['days_left'] == 0:
                    status = "Habis Hari Ini"
                else:
                    status = f"{it['days_left']} hari lagi"
                
                pesan += f"   ⚙️ {it['perangkat']}\n"
                pesan += f"   ⏳ {it['tgl']} ({status})\n"
            pesan += "\n"
        
        pesan += "Mohon segera ditindaklanjuti. Terima kasih."
        
        print("Mengirim pesan reminder H-30...")
        kirim_waha_teks(GROUP_ID_TUJUAN, pesan)
        pesan_terkirim = True
        
    # ==========================
    # 2. Kirim Pesan H-90 (Hanya Hari Senin)
    # ==========================
    if is_monday and h90_items:
        pesan = "🔔 *REMINDER H-90 HABIS KONTRAK* 🔔\n"
        pesan += "Berikut adalah daftar perangkat/alpro yang kontraknya akan habis dalam 30-90 hari ke depan:\n\n"
        
        grouped_h90 = {}
        for it in h90_items:
            grouped_h90.setdefault(it["district"], []).append(it)
            
        for dist, items in grouped_h90.items():
            pesan += f"📍 *{dist}*\n"
            for it in items:
                pesan += f"   ⚙️ {it['perangkat']}\n"
                pesan += f"   ⏳ {it['tgl']} ({it['days_left']} hari lagi)\n"
            pesan += "\n"
            
        pesan += "Mohon agar disiapkan proses perpanjangannya. Terima kasih."
        
        print("Mengirim pesan reminder H-90...")
        kirim_waha_teks(GROUP_ID_TUJUAN, pesan)
        pesan_terkirim = True
        
    if not pesan_terkirim:
        print("✅ Tidak ada reminder yang perlu dikirim saat ini.")
        
    print("=" * 50)
    print("Selesai.")

if __name__ == "__main__":
    main()
