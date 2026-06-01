# Kirim Manja Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `kirim_manja.py`, a polling Google Sheet monitor that sends WAHA text alerts for MANJA, DIAMOND, PLATINUM, and JAM72 ticket tables.

**Architecture:** Keep the script as one import-safe Python module with pure parsing, formatting, hashing, and change-detection helpers. The runtime loop only wires Google Sheets reads, WAHA sends, logging, and adaptive polling.

**Tech Stack:** Python, `gspread`, `oauth2client`, `requests`, `pytest`, Google Sheets service account JSON, WAHA `/api/sendText`.

---

## File Structure

- Create: `C:\Users\anant\Downloads\OLT\kirim_manja.py`
  - Owns configuration, Google Sheet access, table extraction, message formatting, snapshot change detection, WAHA text sending, logging, and polling loop.
  - Must be import-safe: importing this module must not start the infinite loop.
- Create: `C:\Users\anant\Downloads\OLT\tests\test_kirim_manja.py`
  - Owns unit tests for column conversion, district normalization, table extraction, message formatting, change detection, and one cycle of routing.
- Modify: no existing runtime script needs modification.

## Public Interfaces To Implement

`kirim_manja.py` should expose these names because the tests depend on them:

```python
TABLE_CONFIGS
DISTRIK_GRUP
GRUP_INTI
TARGET_DISTRIK
TableData
kolom_ke_indeks(huruf)
normalisasi_distrik(nama)
nama_distrik_tampil(distrik_norm)
nilai_cell(semua_nilai, row_idx, col_idx)
ekstrak_table(cfg, semua_nilai)
buat_pesan_data(cfg, judul_suffix, rows)
buat_pesan_clear(cfg, judul_suffix)
hash_rows(rows)
proses_target(snapshot, snapshot_key, chat_id, cfg, suffix, rows, send_func)
proses_siklus(snapshot)
kirim_teks_wa(chat_id, teks)
main()
```

`TableData`:

```python
@dataclass
class TableData:
    by_district: dict[str, list[list[str]]]
    all_rows: list[list[str]]
    skipped: list[tuple[int, str, list[str]]]
```

---

### Task 1: Write Tests For Normalization And Extraction

**Files:**
- Create: `C:\Users\anant\Downloads\OLT\tests\test_kirim_manja.py`
- Test target: `C:\Users\anant\Downloads\OLT\kirim_manja.py`

- [ ] **Step 1: Create the failing unit tests**

Add this file:

```python
import kirim_manja as km


def make_sheet_values():
    values = [["" for _ in range(24)] for _ in range(9)]

    # MANJA B5:F => B tiket, C jam booking, D STO, E SA, F DISTRIK
    values[4][1] = "INC-MANJA-BTM"
    values[4][2] = "2026-06-01 15:00:00.0"
    values[4][3] = "SLU"
    values[4][4] = "SA SAGULUNG"
    values[4][5] = "Batam"

    values[5][1] = "INC-MANJA-BKT"
    values[5][2] = "2026-06-01 16:00:00.0"
    values[5][3] = "BKT"
    values[5][4] = "SA BUKITTINGGI"
    values[5][5] = "Bukit Tinggi"

    values[6][1] = "INC-MANJA-UNK"
    values[6][2] = "2026-06-01 17:00:00.0"
    values[6][3] = "UNK"
    values[6][4] = "SA UNKNOWN"
    values[6][5] = "Riau"

    # DIAMOND H5:L => H tiket, I lama, J STO, K SA, L DISTRIK
    values[4][7] = "INC-DIAMOND-PKU"
    values[4][8] = "1"
    values[4][9] = "PKU"
    values[4][10] = "SA PEKANBARU"
    values[4][11] = "Pekanbaru"

    # PLATINUM N5:R => N tiket, O lama, P STO, Q SA, R DISTRIK
    values[4][13] = "INC-PLATINUM-DUM"
    values[4][14] = "6"
    values[4][15] = "DUM"
    values[4][16] = "SA DUMAI"
    values[4][17] = "Dumai"

    # JAM72 U5:X => U tiket, V lama, W STO, X DISTRIK
    values[4][20] = "INC-72-PDG"
    values[4][21] = "72"
    values[4][22] = "PDG"
    values[4][23] = "Padang"

    values[5][20] = "INC-72-OTHER"
    values[5][21] = "80"
    values[5][22] = "OTH"
    values[5][23] = "Other"

    return values


def test_kolom_ke_indeks_uses_zero_based_indices():
    assert km.kolom_ke_indeks("A") == 0
    assert km.kolom_ke_indeks("B") == 1
    assert km.kolom_ke_indeks("L") == 11
    assert km.kolom_ke_indeks("X") == 23


def test_normalisasi_distrik_handles_target_variants():
    assert km.normalisasi_distrik(" Batam ") == "BATAM"
    assert km.normalisasi_distrik("Pekanbaru") == "PEKANBARU"
    assert km.normalisasi_distrik("Dumai") == "DUMAI"
    assert km.normalisasi_distrik("Bukit Tinggi") == "BUKITTINGGI"
    assert km.normalisasi_distrik("BUKIT TINGGI") == "BUKITTINGGI"
    assert km.normalisasi_distrik("Bukittinggi") == "BUKITTINGGI"
    assert km.normalisasi_distrik("Padang") == "PADANG"


def test_ekstrak_table_groups_known_districts_and_logs_unknown_rows():
    data = km.ekstrak_table(km.TABLE_CONFIGS["MANJA"], make_sheet_values())

    assert data.by_district["BATAM"] == [
        ["INC-MANJA-BTM", "2026-06-01 15:00:00.0", "SLU", "SA SAGULUNG"]
    ]
    assert data.by_district["BUKITTINGGI"] == [
        ["INC-MANJA-BKT", "2026-06-01 16:00:00.0", "BKT", "SA BUKITTINGGI"]
    ]
    assert data.by_district["PEKANBARU"] == []
    assert data.by_district["DUMAI"] == []
    assert data.by_district["PADANG"] == []
    assert data.skipped == [
        (7, "Riau", ["INC-MANJA-UNK", "2026-06-01 17:00:00.0", "UNK", "SA UNKNOWN"])
    ]


def test_jam72_keeps_all_rows_for_inti_even_when_district_is_unknown():
    data = km.ekstrak_table(km.TABLE_CONFIGS["JAM72"], make_sheet_values())

    assert data.by_district["PADANG"] == [["INC-72-PDG", "72", "PDG", "Padang"]]
    assert data.by_district["BATAM"] == []
    assert data.all_rows == [
        ["INC-72-PDG", "72", "PDG", "Padang"],
        ["INC-72-OTHER", "80", "OTH", "Other"],
    ]
    assert data.skipped == [
        (6, "Other", ["INC-72-OTHER", "80", "OTH", "Other"])
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
rtk pytest tests/test_kirim_manja.py -q
```

Expected: FAIL because `kirim_manja.py` does not exist yet.

- [ ] **Step 3: Commit the failing tests**

Run:

```bash
rtk git add tests/test_kirim_manja.py
rtk git commit -m "test: define kirim manja parsing behavior"
```

Expected: commit succeeds with only the new test file staged.

---

### Task 2: Implement Configuration And Pure Parsing Helpers

**Files:**
- Create: `C:\Users\anant\Downloads\OLT\kirim_manja.py`
- Test: `C:\Users\anant\Downloads\OLT\tests\test_kirim_manja.py`

- [ ] **Step 1: Create the initial implementation**

Create `kirim_manja.py` with this content:

```python
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import gspread
import requests
from oauth2client.service_account import ServiceAccountCredentials


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
```

- [ ] **Step 2: Run the parsing tests**

Run:

```bash
rtk pytest tests/test_kirim_manja.py -q
```

Expected: PASS for the four tests from Task 1.

- [ ] **Step 3: Commit parsing helpers**

Run:

```bash
rtk git add kirim_manja.py tests/test_kirim_manja.py
rtk git commit -m "feat: parse kirim manja sheet tables"
```

Expected: commit succeeds.

---

### Task 3: Test And Implement Formatting Plus Snapshot Decisions

**Files:**
- Modify: `C:\Users\anant\Downloads\OLT\tests\test_kirim_manja.py`
- Modify: `C:\Users\anant\Downloads\OLT\kirim_manja.py`

- [ ] **Step 1: Add tests for message formatting and target processing**

Append these tests to `tests/test_kirim_manja.py`:

```python

def test_buat_pesan_data_uses_expected_manja_format():
    text = km.buat_pesan_data(
        km.TABLE_CONFIGS["MANJA"],
        "Batam",
        [["INC49847623", "2026-06-01 15:00:00.0", "SLU", "SA SAGULUNG"]],
    )

    assert text == "\n".join([
        "Alarm 3 Jam Manja Open | Batam",
        "==============",
        "Tiket | Jam Booking | STO | SA",
        "INC49847623 | 2026-06-01 15:00:00.0 | SLU | SA SAGULUNG",
    ])


def test_buat_pesan_clear_uses_expected_format():
    text = km.buat_pesan_clear(km.TABLE_CONFIGS["JAM72"], "")

    assert text == "\n".join([
        "Alarm 72 Jam Tiket Open",
        "==============",
        "CLEAR - Tidak ada tiket aktif.",
    ])


def test_proses_target_sends_first_run_data_and_skips_unchanged_rows():
    sent = []

    def fake_send(chat_id, text):
        sent.append((chat_id, text))
        return True

    snapshot = {}
    rows = [["INC49847623", "1", "SLU", "SA SAGULUNG"]]

    changed = km.proses_target(
        snapshot,
        ("DIAMOND", "BATAM"),
        "group-batam@g.us",
        km.TABLE_CONFIGS["DIAMOND"],
        "Batam",
        rows,
        fake_send,
    )

    assert changed is True
    assert len(sent) == 1
    assert sent[0][0] == "group-batam@g.us"
    assert sent[0][1].splitlines()[0] == "Alarm 3 Jam Diamond | Batam"

    changed_again = km.proses_target(
        snapshot,
        ("DIAMOND", "BATAM"),
        "group-batam@g.us",
        km.TABLE_CONFIGS["DIAMOND"],
        "Batam",
        rows,
        fake_send,
    )

    assert changed_again is False
    assert len(sent) == 1


def test_proses_target_sends_clear_when_existing_rows_become_empty():
    sent = []

    def fake_send(chat_id, text):
        sent.append((chat_id, text))
        return True

    snapshot = {}
    rows = [["INC49847623", "1", "SLU", "SA SAGULUNG"]]

    km.proses_target(
        snapshot,
        ("PLATINUM", "DUMAI"),
        "group-dumai@g.us",
        km.TABLE_CONFIGS["PLATINUM"],
        "Dumai",
        rows,
        fake_send,
    )
    changed = km.proses_target(
        snapshot,
        ("PLATINUM", "DUMAI"),
        "group-dumai@g.us",
        km.TABLE_CONFIGS["PLATINUM"],
        "Dumai",
        [],
        fake_send,
    )

    assert changed is True
    assert sent[-1] == (
        "group-dumai@g.us",
        "\n".join([
            "Alarm 6 Jam Platinum | Dumai",
            "==============",
            "CLEAR - Tidak ada tiket aktif.",
        ]),
    )


def test_proses_target_does_not_update_snapshot_when_send_fails():
    def failing_send(chat_id, text):
        return False

    snapshot = {}
    rows = [["INC49847623", "1", "SLU", "SA SAGULUNG"]]

    changed = km.proses_target(
        snapshot,
        ("DIAMOND", "BATAM"),
        "group-batam@g.us",
        km.TABLE_CONFIGS["DIAMOND"],
        "Batam",
        rows,
        failing_send,
    )

    assert changed is False
    assert snapshot == {}
```

- [ ] **Step 2: Run tests to verify missing implementation fails**

Run:

```bash
rtk pytest tests/test_kirim_manja.py -q
```

Expected: FAIL because `proses_target` is not implemented.

- [ ] **Step 3: Add `proses_target` implementation**

Append this function to `kirim_manja.py` after `hash_rows`:

```python

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
rtk pytest tests/test_kirim_manja.py -q
```

Expected: PASS for all tests.

- [ ] **Step 5: Commit formatting and snapshot behavior**

Run:

```bash
rtk git add kirim_manja.py tests/test_kirim_manja.py
rtk git commit -m "feat: format and detect kirim manja changes"
```

Expected: commit succeeds.

---

### Task 4: Test And Implement One Full Processing Cycle

**Files:**
- Modify: `C:\Users\anant\Downloads\OLT\tests\test_kirim_manja.py`
- Modify: `C:\Users\anant\Downloads\OLT\kirim_manja.py`

- [ ] **Step 1: Add a full-cycle routing test**

Append this test to `tests/test_kirim_manja.py`:

```python

def test_proses_siklus_routes_per_district_and_jam72_to_inti(monkeypatch):
    sent = []

    class FakeWorksheet:
        def get_all_values(self):
            return make_sheet_values()

    def fake_buka_worksheet():
        return FakeWorksheet()

    def fake_send(chat_id, text):
        sent.append((chat_id, text))
        return True

    logs = []

    monkeypatch.setattr(km, "buka_worksheet", fake_buka_worksheet)
    monkeypatch.setattr(km, "kirim_teks_wa", fake_send)
    monkeypatch.setattr(km, "catat_log", lambda pesan: logs.append(pesan))

    snapshot = {}
    changed = km.proses_siklus(snapshot)

    assert changed is True
    assert any(chat_id == "ISI_GROUP_BATAM@g.us" and text.startswith("Alarm 3 Jam Manja Open | Batam") for chat_id, text in sent)
    assert any(chat_id == "ISI_GROUP_BUKITTINGGI@g.us" and text.startswith("Alarm 3 Jam Manja Open | Bukittinggi") for chat_id, text in sent)
    assert any(chat_id == "ISI_GROUP_PEKANBARU@g.us" and text.startswith("Alarm 3 Jam Diamond | Pekanbaru") for chat_id, text in sent)
    assert any(chat_id == "ISI_GROUP_DUMAI@g.us" and text.startswith("Alarm 6 Jam Platinum | Dumai") for chat_id, text in sent)
    assert any(chat_id == "ISI_GROUP_PADANG@g.us" and text.startswith("Alarm 72 Jam Tiket Open | Padang") for chat_id, text in sent)
    assert any(chat_id == "ISI_GROUP_INTI@g.us" and text.startswith("Alarm 72 Jam Tiket Open\n") for chat_id, text in sent)
    assert any("dilewati" in pesan for pesan in logs)

    sent.clear()
    changed_again = km.proses_siklus(snapshot)

    assert changed_again is False
    assert sent == []
```

- [ ] **Step 2: Run tests to verify full-cycle functions are missing**

Run:

```bash
rtk pytest tests/test_kirim_manja.py -q
```

Expected: FAIL because `buka_worksheet`, `kirim_teks_wa`, and `proses_siklus` are not implemented.

- [ ] **Step 3: Add Google Sheet, WAHA, and cycle functions**

Append this code to `kirim_manja.py` after `proses_target`:

```python

def buka_worksheet():
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
rtk pytest tests/test_kirim_manja.py -q
```

Expected: PASS for all tests.

- [ ] **Step 5: Commit processing cycle**

Run:

```bash
rtk git add kirim_manja.py tests/test_kirim_manja.py
rtk git commit -m "feat: route kirim manja alerts"
```

Expected: commit succeeds.

---

### Task 5: Add Main Loop, Import Guard, And Verification

**Files:**
- Modify: `C:\Users\anant\Downloads\OLT\kirim_manja.py`
- Test: `C:\Users\anant\Downloads\OLT\tests\test_kirim_manja.py`

- [ ] **Step 1: Add polling main loop and import guard**

Append this code to `kirim_manja.py`:

```python

def main():
    snapshot = {}
    interval = 30
    max_interval = 300

    catat_log("Program Kirim Manja aktif. Memulai polling Google Sheet.")

    while True:
        try:
            ada_perubahan = proses_siklus(snapshot)
            if ada_perubahan:
                interval = 30
                catat_log("Perubahan terkirim. Interval polling kembali ke 30 detik.")
            else:
                interval = min(max_interval, int(interval * 1.5))
                catat_log(f"Tidak ada perubahan. Polling berikutnya dalam {interval} detik.")
        except KeyboardInterrupt:
            catat_log("Program dihentikan oleh pengguna.")
            raise
        except Exception as exc:
            catat_log(f"Error dalam siklus utama: {exc}")

        time.sleep(interval)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run all kirim manja tests**

Run:

```bash
rtk pytest tests/test_kirim_manja.py -q
```

Expected: PASS.

- [ ] **Step 3: Verify module imports without starting the loop**

Run:

```bash
rtk python -c "import kirim_manja; print(kirim_manja.SPREADSHEET_ID); print(kirim_manja.GID_SHEET)"
```

Expected output contains:

```text
1Jl-povDud6JKpb4qqB8pRIA0FbpB6lbNomhs9iL5F98
1992709075
```

- [ ] **Step 4: Run the full test suite**

Run:

```bash
rtk pytest -q
```

Expected: PASS for existing tests and `tests/test_kirim_manja.py`.

- [ ] **Step 5: Inspect the final diff**

Run:

```bash
rtk git diff -- kirim_manja.py tests/test_kirim_manja.py docs/superpowers/specs/2026-06-01-kirim-manja-design.md docs/superpowers/plans/2026-06-01-kirim-manja.md
```

Expected: diff only includes the new script, new tests, updated design spec, and this plan.

- [ ] **Step 6: Commit final loop and docs**

Run:

```bash
rtk git add kirim_manja.py tests/test_kirim_manja.py docs/superpowers/specs/2026-06-01-kirim-manja-design.md docs/superpowers/plans/2026-06-01-kirim-manja.md
rtk git commit -m "feat: add kirim manja polling script"
```

Expected: commit succeeds.

---

## Self-Review

- Spec coverage: the plan covers spreadsheet ID/GID, all four table ranges, per-district routing, JAM72 inti routing, first-run sends, clear notifications, district normalization, unknown-district behavior, WAHA text sends, logging, retry-on-send-failure, and adaptive polling.
- Red-flag scan: group IDs use the exact temporary strings approved by the user; no ambiguous implementation steps remain.
- Type consistency: `TableData`, `TABLE_CONFIGS`, `proses_target`, and `proses_siklus` signatures are consistent across tests and implementation snippets.
