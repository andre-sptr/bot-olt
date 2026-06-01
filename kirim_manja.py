import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime

try:
    import gspread
except ModuleNotFoundError:
    gspread = None

try:
    import requests
except ModuleNotFoundError:
    requests = None

try:
    from oauth2client.service_account import ServiceAccountCredentials
except ModuleNotFoundError:
    ServiceAccountCredentials = None


SPREADSHEET_ID = "1Jl-povDud6JKpb4qqB8pRIA0FbpB6lbNomhs9iL5F98"
GID_SHEET = 1992709075
FILE_KREDENSIAL = "kunci_rahasia_google.json"

WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id"
WAHA_SESSION = "OLTReport"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"

DISTRIK_GRUP = {
    "BATAM": "ISI_GROUP_BATAM@g.us",
    "PEKANBARU": "ISI_GROUP_PEKANBARU@g.us",
    "DUMAI": "ISI_GROUP_DUMAI@g.us",
    "BUKITTINGGI": "ISI_GROUP_BUKITTINGGI@g.us",
    "PADANG": "ISI_GROUP_PADANG@g.us",
}
GRUP_INTI = "ISI_GROUP_INTI@g.us"
TARGET_DISTRIK = list(DISTRIK_GRUP.keys())

FOLDER_LOG = "logs"


TABLE_CONFIGS = {
    "MANJA": {
        "key": "MANJA",
        "title": "Alarm 3 Jam Manja Open",
        "start_row": 5,
        "display_cols": ["B", "C", "D", "E"],
        "district_col": "F",
        "header": "Tiket | Jam Booking | STO | SA",
        "send_inti": False,
    },
    "DIAMOND": {
        "key": "DIAMOND",
        "title": "Alarm 3 Jam Diamond",
        "start_row": 5,
        "display_cols": ["H", "I", "J", "K"],
        "district_col": "L",
        "header": "Tiket | Open Berjalan (Jam) | STO | SA",
        "send_inti": False,
    },
    "PLATINUM": {
        "key": "PLATINUM",
        "title": "Alarm 6 Jam Platinum",
        "start_row": 5,
        "display_cols": ["N", "O", "P", "Q"],
        "district_col": "R",
        "header": "Tiket | Open Berjalan (Jam) | STO | SA",
        "send_inti": False,
    },
    "JAM72": {
        "key": "JAM72",
        "title": "Alarm 72 Jam Tiket Open",
        "start_row": 5,
        "display_cols": ["U", "V", "W", "X"],
        "district_col": "X",
        "header": "Tiket | Open Berjalan (Jam) | STO | Distrik",
        "send_inti": True,
    },
}


@dataclass
class TableData:
    by_district: dict[str, list[list[str]]]
    all_rows: list[list[str]]
    skipped: list[tuple[int, str, list[str]]]


def tanggal_hari_ini():
    return datetime.now().strftime("%Y-%m-%d")


def nama_file_log():
    return os.path.join(FOLDER_LOG, "kirim_manja_log.txt")


def catat_log(pesan):
    waktu = datetime.now().strftime("%H:%M:%S")
    tanggal_sekarang = tanggal_hari_ini()
    pesan_log = f"[{waktu}] {pesan}"
    print(pesan_log)

    os.makedirs(FOLDER_LOG, exist_ok=True)
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


def kolom_ke_indeks(huruf):
    if not isinstance(huruf, str):
        raise ValueError(f"Kolom tidak valid: {huruf!r}")

    label = huruf.strip().upper()
    if not label or any(karakter < "A" or karakter > "Z" for karakter in label):
        raise ValueError(f"Kolom tidak valid: {huruf!r}")

    hasil = 0
    for karakter in label:
        hasil = hasil * 26 + (ord(karakter) - ord("A") + 1)
    return hasil - 1


def normalisasi_distrik(nama):
    return str(nama or "").strip().upper().replace(" ", "")


def nama_distrik_tampil(distrik_norm):
    mapping = {
        "BATAM": "Batam",
        "PEKANBARU": "Pekanbaru",
        "DUMAI": "Dumai",
        "BUKITTINGGI": "Bukittinggi",
        "PADANG": "Padang",
    }
    return mapping.get(distrik_norm, str(distrik_norm).title())


def nilai_cell(semua_nilai, row_idx, col_idx):
    if row_idx < 0 or row_idx >= len(semua_nilai):
        return ""
    row = semua_nilai[row_idx]
    if col_idx < 0 or col_idx >= len(row):
        return ""
    return str(row[col_idx]).strip()


def ekstrak_table(cfg, semua_nilai):
    by_district = {distrik: [] for distrik in TARGET_DISTRIK}
    all_rows = []
    skipped = []

    start_idx = int(cfg["start_row"]) - 1
    display_indices = [kolom_ke_indeks(col) for col in cfg["display_cols"]]
    district_idx = kolom_ke_indeks(cfg["district_col"])

    for row_idx in range(start_idx, len(semua_nilai)):
        display_row = [nilai_cell(semua_nilai, row_idx, col_idx) for col_idx in display_indices]
        tiket = display_row[0] if display_row else ""
        if not tiket:
            continue

        distrik_asli = nilai_cell(semua_nilai, row_idx, district_idx)
        distrik_norm = normalisasi_distrik(distrik_asli)
        all_rows.append(display_row)

        if distrik_norm in by_district:
            by_district[distrik_norm].append(display_row)
        else:
            skipped.append((row_idx + 1, distrik_asli, display_row))

    return TableData(by_district=by_district, all_rows=all_rows, skipped=skipped)


def buat_pesan_data(cfg, judul_suffix, rows):
    title = cfg["title"] if not judul_suffix else f'{cfg["title"]} | {judul_suffix}'
    lines = [title, "==============", cfg["header"]]
    lines.extend(" | ".join(row) for row in rows)
    return "\n".join(lines)


def buat_pesan_clear(cfg, judul_suffix):
    title = cfg["title"] if not judul_suffix else f'{cfg["title"]} | {judul_suffix}'
    return "\n".join([title, "==============", "CLEAR - Tidak ada tiket aktif."])


def hash_rows(rows):
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def proses_target(snapshot, snapshot_key, chat_id, cfg, suffix, rows, send_func):
    rows_hash = hash_rows(rows)
    previous_hash = snapshot.get(snapshot_key)

    if previous_hash == rows_hash:
        return False

    if previous_hash is None and not rows:
        snapshot[snapshot_key] = rows_hash
        return False

    pesan = buat_pesan_data(cfg, suffix, rows) if rows else buat_pesan_clear(cfg, suffix)
    if send_func(chat_id, pesan):
        snapshot[snapshot_key] = rows_hash
        return True

    return False


def buka_worksheet():
    missing = []
    if gspread is None:
        missing.append("gspread")
    if ServiceAccountCredentials is None:
        missing.append("oauth2client.service_account.ServiceAccountCredentials")
    if missing:
        pesan = "Dependency Google Sheet belum tersedia: " + ", ".join(missing)
        catat_log(pesan)
        raise RuntimeError(pesan)

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(FILE_KREDENSIAL, scope)
    client_gs = gspread.authorize(creds)
    spreadsheet = client_gs.open_by_key(SPREADSHEET_ID)
    return spreadsheet.get_worksheet_by_id(GID_SHEET)


def kirim_teks_wa(chat_id, teks):
    if requests is None:
        catat_log("Dependency WAHA belum tersedia: requests")
        return False

    url = f"{WAHA_URL.rstrip('/')}/api/sendText"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Api-Key": WAHA_API_KEY,
        "Connection": "close",
    }
    payload = {
        "session": WAHA_SESSION,
        "chatId": chat_id,
        "text": teks,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code in [200, 201]:
            catat_log(f"Berhasil mengirim ke WhatsApp: {chat_id}")
            return True
        catat_log(f"Gagal mengirim ke {chat_id}. Status: {response.status_code}, Response: {response.text}")
    except Exception as exc:
        catat_log(f"Error saat mengirim ke WAHA ({chat_id}): {exc}")

    return False


def proses_siklus(snapshot):
    worksheet = buka_worksheet()
    semua_nilai = worksheet.get_all_values()
    ada_perubahan = False

    for cfg in TABLE_CONFIGS.values():
        table_data = ekstrak_table(cfg, semua_nilai)

        for row_number, distrik_asli, display_row in table_data.skipped:
            catat_log(
                f"Baris {row_number} table {cfg['key']} dilewati untuk per-distrik: "
                f"DISTRIK='{distrik_asli}', DATA={display_row}"
            )

        for distrik_norm in TARGET_DISTRIK:
            rows = table_data.by_district[distrik_norm]
            suffix = nama_distrik_tampil(distrik_norm)
            chat_id = DISTRIK_GRUP[distrik_norm]
            sent = proses_target(
                snapshot,
                (cfg["key"], distrik_norm),
                chat_id,
                cfg,
                suffix,
                rows,
                kirim_teks_wa,
            )
            ada_perubahan = ada_perubahan or sent

        if cfg.get("send_inti"):
            sent = proses_target(
                snapshot,
                (cfg["key"], "__INTI__"),
                GRUP_INTI,
                cfg,
                "",
                table_data.all_rows,
                kirim_teks_wa,
            )
            ada_perubahan = ada_perubahan or sent

    return ada_perubahan


def main():
    snapshot = {}
    interval = 30
    max_interval = 300

    catat_log("Program Kirim Manja aktif. Memulai polling Google Sheet.")

    while True:
        try:
            try:
                ada_perubahan = proses_siklus(snapshot)
                if ada_perubahan:
                    interval = 30
                    catat_log("Perubahan terkirim. Interval polling kembali ke 30 detik.")
                else:
                    interval = min(max_interval, int(interval * 1.5))
                    catat_log(f"Tidak ada perubahan. Polling berikutnya dalam {interval} detik.")
            except Exception as exc:
                catat_log(f"Error dalam siklus utama: {exc}")

            time.sleep(interval)
        except KeyboardInterrupt:
            catat_log("Program dihentikan oleh pengguna.")
            raise


if __name__ == "__main__":
    main()
