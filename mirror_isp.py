from telethon import TelegramClient, events
from datetime import datetime
import requests
import os
import sys
import traceback

try:
    import gspread
except ModuleNotFoundError:
    gspread = None

try:
    from oauth2client.service_account import ServiceAccountCredentials
except ModuleNotFoundError:
    ServiceAccountCredentials = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ================== KONFIGURASI TELEGRAM ==================
api_id = 35153027
api_hash = '275a7916b30391e446366433d5427086'

ID_GRUP_BTM = -1001267017385
ID_GRUP_DUM = -332267455
ID_GRUP_PKU = -1001481602761
ID_GRUP_PDG = -1001281180665
ID_GRUP_BKT = -1003652501250
ID_GRUP_TESTING = -4883113309

daftar_grup_target = [ID_GRUP_BTM, ID_GRUP_DUM, ID_GRUP_PKU, ID_GRUP_PDG, ID_GRUP_BKT, ID_GRUP_TESTING]

# ================== KONFIGURASI WAHA ==================
WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id" 
WAHA_SESSION = "OLTReport"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"
# 120363425065142845@g.us = real
# 120363423984319917@g.us = test
GROUP_ISP = "120363425065142845@g.us"
GROUP_POSKO = "120363427217043012@g.us"
GROUP_ID_TUJUAN = [
    GROUP_ISP,
    GROUP_POSKO
]

# ================== KONFIGURASI SEVERITY ==================
SPREADSHEET_ID_SEVERITY = "1impgFooLJCAaJQ6zgZ8kdRLRgHhBetCfHjge4CsXh-4"
GID_SHEET_SEVERITY = 876436999
FILE_KREDENSIAL_GOOGLE = "kunci_rahasia_google.json"

SEVERITY_VALID = {
    "low": "Low",
    "minor": "Minor",
    "major": "Major",
    "critical": "Critical",
}

EMOJI_SEVERITY = {
    "Low": "🟡 Low",
    "Minor": "🟠 Minor",
    "Major": "🔴 Major",
    "Critical": "🟥 Critical",
}

# ======================================================

FOLDER_LOG = "logs"
os.makedirs(FOLDER_LOG, exist_ok=True)

client = TelegramClient('sesi_mirror_isp', api_id, api_hash)

data_gpon_down = {}
data_gpon_up = {}

tanggal_data_sekarang = datetime.now().strftime("%Y-%m-%d")


def nama_file_log():
    """KONSISTENSI: Nama log sistem menjadi statis agar hanya ada 1 file"""
    return os.path.join(FOLDER_LOG, "mirror_isp_log.txt")


def simpan_log(pesan):
    """Mencatat log dengan fitur auto-reset jika masuk hari baru."""
    waktu_log = datetime.now().strftime("%H:%M:%S")
    tanggal_sekarang = datetime.now().strftime("%Y-%m-%d")
    pesan_full = f"[{waktu_log}] {pesan}"
    print(pesan_full)

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
        f.write(pesan_full + "\n")


def normalisasi_hostname(hostname):
    return str(hostname or "").strip().strip("*`_").upper()


def normalisasi_severity(severity):
    return SEVERITY_VALID.get(str(severity or "").strip().casefold(), "")


def buat_mapping_severity(semua_nilai):
    """Buat mapping HOSTNAME -> SEVERITY dari kolom A:B."""
    mapping = {}

    for baris in semua_nilai[1:]:
        if not baris:
            continue

        hostname = normalisasi_hostname(baris[0])
        severity = normalisasi_severity(baris[1] if len(baris) > 1 else "")
        if hostname and severity:
            mapping[hostname] = severity

    return mapping


def ambil_mapping_severity():
    """Ambil HOSTNAME dan SEVERITY dari tab Sev Mini OLT."""
    missing = []
    if gspread is None:
        missing.append("gspread")
    if ServiceAccountCredentials is None:
        missing.append("oauth2client")
    if missing:
        raise RuntimeError(
            "Dependency Google Sheet belum tersedia: " + ", ".join(missing)
        )

    scope = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
    ]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        FILE_KREDENSIAL_GOOGLE,
        scope,
    )
    client_gs = gspread.authorize(credentials)
    spreadsheet = client_gs.open_by_key(SPREADSHEET_ID_SEVERITY)
    worksheet = spreadsheet.get_worksheet_by_id(GID_SHEET_SEVERITY)
    return buat_mapping_severity(worksheet.get("A:B"))


def format_baris_down(no, info, mapping_severity):
    bagian = [nilai.strip() for nilai in str(info or "").split("|")]
    bagian += [""] * (5 - len(bagian))

    district = bagian[0] or "-"
    hostname = normalisasi_hostname(bagian[1]) or "-"
    durasi_down = bagian[2] or "-"
    node_b = bagian[3] or "-"
    id_pln = bagian[4] or "-"

    severity = normalisasi_severity(mapping_severity.get(hostname, ""))
    severity_tampil = EMOJI_SEVERITY.get(severity, "-")

    return (
        f"{no} | {district} | {hostname} | {durasi_down} | "
        f"{node_b} | {severity_tampil} | {id_pln}"
    )


def buat_laporan_list(mapping_severity=None):
    if mapping_severity is None:
        try:
            mapping_severity = ambil_mapping_severity()
            simpan_log(
                f"Berhasil mengambil {len(mapping_severity)} data severity "
                f"dari GID {GID_SHEET_SEVERITY}"
            )
        except Exception as exc:
            mapping_severity = {}
            simpan_log(
                f"Gagal mengambil data severity, menggunakan '-': {exc}"
            )

    teks_laporan = "*OLT DOWN*\n"
    teks_laporan += (
        "NO | DISTRICT | HOSTNAME | DURASI DOWN | "
        "NodeB | SEVERITY | IdPLN\n"
    )
    
    no = 1
    for hostname, info in data_gpon_down.items():
        teks_laporan += format_baris_down(no, info, mapping_severity) + "\n"
        no += 1
        
    teks_laporan += "\n*OLT UP*\n"
    teks_laporan += "NO | HOSTNAME | STATUS\n"
    
    no = 1
    for hostname, info in data_gpon_up.items():
        teks_laporan += f"{no}. {info}\n"
        no += 1
        
    return teks_laporan


def simpan_ke_file_laporan(teks):
    """KONSISTENSI: Menyimpan teks list laporan ke dalam satu file statis agar tidak menumpuk."""
    nama_file = os.path.join(FOLDER_LOG, "isp_new_report.txt")
    
    try:
        with open(nama_file, "w", encoding="utf-8") as file:
            file.write(teks)
        simpan_log(f"✅ Berhasil mengupdate file {nama_file}")
    except Exception as e:
        simpan_log(f"❌ Error saat membuat file laporan: {e}")


def kirim_pesan_wa(teks):
    url = f"{WAHA_URL.rstrip('/')}/api/sendText"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Api-Key": WAHA_API_KEY,
        "Connection": "close"
    }

    semua_berhasil = True

    for chat_id in GROUP_ID_TUJUAN:
        payload = {
            "session": WAHA_SESSION,
            "chatId": chat_id, 
            "text": teks
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code in [200, 201]:
                simpan_log(f"✅ Berhasil mirroring ke WhatsApp (Grup: {chat_id})")
            else:
                simpan_log(f"❌ Gagal mirroring ke {chat_id}. Status: {response.status_code}, Response: {response.text}")
                semua_berhasil = False
        except Exception as e:
            simpan_log(f"❌ Error saat mengirim ke WAHA ({chat_id}): {e}")
            semua_berhasil = False
            
    return semua_berhasil


@client.on(events.NewMessage(chats=daftar_grup_target))
async def proses_pesan_baru(event):
    global tanggal_data_sekarang
    
    try:
        tanggal_hari_ini = datetime.now().strftime("%Y-%m-%d")
        if tanggal_hari_ini != tanggal_data_sekarang:
            simpan_log("🕛 Pergantian hari terdeteksi. Mereset data laporan kemarin...")
            data_gpon_up.clear()
            tanggal_data_sekarang = tanggal_hari_ini
            
        teks_pesan = event.text.strip() if event.text else ""
        teks_pesan_upper = teks_pesan.upper()
        baris_pesan = teks_pesan.split('\n')
        
        ada_perubahan = False

        if '!PROGRAM ZERO GAMAS OLT!' in teks_pesan_upper:
            nama_distrik = "UNKNOWN"
            for baris in baris_pesan:
                if 'DISTRICT' in baris.upper():
                    parts = baris.split('DISTRICT')
                    if len(parts) > 1:
                        nama_distrik = parts[1].strip().replace('*', '')
            
            for baris in baris_pesan:
                if 'GPON' in baris.upper() and '|' in baris:
                    bagian = [b.strip() for b in baris.split('|')]
                    if len(bagian) >= 1:
                        hostname = normalisasi_hostname(bagian[0])
                        data_gabungan = f"{nama_distrik} | {baris.strip()}"
                        data_gpon_down[hostname] = data_gabungan
                        ada_perubahan = True
                        
                        if hostname in data_gpon_up:
                            del data_gpon_up[hostname]

        elif '| UP' in teks_pesan_upper:
            for baris in baris_pesan:
                if 'GPON' in baris.upper() and '| UP' in baris.upper() and 'UPLINK' not in baris.upper():
                    bagian = [b.strip() for b in baris.split('|')]
                    hostname = next((b for b in bagian if 'GPON' in b.upper()), None)
                    if hostname:
                        hostname = normalisasi_hostname(hostname)
                        data_gpon_up[hostname] = baris.strip()
                        ada_perubahan = True
                        
                        if hostname in data_gpon_down:
                            del data_gpon_down[hostname]

        if ada_perubahan:
            simpan_log("🔔 Perubahan data GPON terdeteksi. Memperbarui laporan...")
            teks_laporan_baru = buat_laporan_list()
            simpan_ke_file_laporan(teks_laporan_baru)
            kirim_pesan_wa(teks_laporan_baru)

    except Exception as e:
        simpan_log(f"❌ Error dalam proses_pesan_baru: {e}")
        simpan_log(traceback.format_exc())


async def main():
    simpan_log("Memulai koneksi ke Telegram...")
    await client.start()
    simpan_log(f"🚀 Program Mirroring Aktif! Mendengarkan {len(daftar_grup_target)} grup...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    with client:
        client.loop.run_until_complete(main())
