from telethon import TelegramClient, events
from datetime import datetime
import requests
import os
import sys
import io
import traceback

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

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


def buat_laporan_list():
    teks_laporan = "*OLT DOWN*\n"
    teks_laporan += "NO | DISTRICT | HOSTNAME | DURASI DOWN | NodeB | IdPLN\n"
    
    no = 1
    for hostname, info in data_gpon_down.items():
        teks_laporan += f"{no}. {info}\n"
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
                        hostname = bagian[0]
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