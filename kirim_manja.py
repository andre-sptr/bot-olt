import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

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
os.makedirs(FOLDER_LOG, exist_ok=True)


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
    hasil = 0
    for karakter in huruf.strip().upper():
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
