# Rekap OLT Down/Up ke Google Sheet — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `mirror_isp.py` menulis rekap insiden OLT (down/up) ke tab Google Sheet GID `320650666` sebagai incident-log: 1 baris/insiden, update in-place saat re-alert 30 menit, finalisasi saat UP.

**Architecture:** Logika dipisah jadi fungsi murni yang mudah diuji (`bangun_baris_rekap`, `indeks_insiden_aktif`, `rencana_tulis_rekap`) + satu fungsi I/O tipis (`tulis_rekap_olt`) yang membuka spreadsheet (scope tulis sendiri), membaca isi tab sekali, lalu menerapkan rencana via `batch_update` + `append_rows`. Hook dipasang di blok `if ada_perubahan:` pada `proses_pesan_baru`. Sumber kebenaran = isi sheet (tahan-restart, tanpa duplikat).

**Tech Stack:** Python 3, gspread 6.2.1, oauth2client, unittest (dijalankan via `python -m unittest`).

## Global Constraints

- Spreadsheet ID: `1crQdVmqXoROtuiaB4-ce7sIwJh26oxKMPq3Mj6-GyLU` (sama dengan sumber metadata; konstanta `SPREADSHEET_ID_METADATA` yang sudah ada).
- Tab tujuan GID: `320650666`.
- Skema 14 kolom A–N, urutan persis: `NO | DISTRICT | HOSTNAME | DURASI DOWN | SEVERITY | NodeB | OLO | K2 | K3 | DH | DS | HIPOTESA | STATUS | TIMESTAMP`.
- SEVERITY = teks polos (mis. `Very Low`), TANPA emoji. Default `Very Low`.
- TIMESTAMP = format `%d/%m/%Y %H:%M:%S` (teks).
- Semua tulis ke Sheets pakai `value_input_option="RAW"` agar string (durasi `05:50`, timestamp) tidak diparse Sheets.
- Kegagalan Sheets TIDAK boleh menghentikan mirroring WhatsApp — bungkus pemanggilan rekap dengan `try/except` + `simpan_log`.
- Test runner: `.venv/Scripts/python.exe -m unittest tests.test_mirror_isp -v`.
- gspread 6.x: gunakan `append_row(...)` untuk header (hindari `update()` yang signature-nya berubah di 6.0).
- Prasyarat manual user (bukan langkah kode): spreadsheet di-share ke email service account `kunci_rahasia_google.json` sebagai **Editor**.

---

### Task 1: Konstanta rekap + helper waktu/durasi

**Files:**
- Modify: `mirror_isp.py` (blok `KONFIGURASI METADATA OLT`, sekitar baris 64–68)
- Test: `tests/test_mirror_isp.py`

**Interfaces:**
- Produces:
  - `GID_SHEET_REKAP = 320650666`
  - `HEADER_REKAP: list[str]` (14 elemen, urutan sesuai Global Constraints)
  - `format_timestamp_rekap(waktu: datetime) -> str` → `"%d/%m/%Y %H:%M:%S"`
  - `hitung_durasi_total(started_at: datetime|None, waktu_up: datetime|None) -> str|None` → `"HH:MM"` total outage, atau `None` bila tak bisa dihitung/negatif.

- [ ] **Step 1: Write the failing test**

Tambahkan di akhir `tests/test_mirror_isp.py`:

```python
class TestHelperRekap(TestCase):
    def test_header_punya_14_kolom_urutan_benar(self):
        self.assertEqual(
            mi.HEADER_REKAP,
            ["NO", "DISTRICT", "HOSTNAME", "DURASI DOWN", "SEVERITY",
             "NodeB", "OLO", "K2", "K3", "DH", "DS", "HIPOTESA",
             "STATUS", "TIMESTAMP"],
        )
        self.assertEqual(mi.GID_SHEET_REKAP, 320650666)

    def test_format_timestamp_rekap(self):
        from datetime import datetime
        hasil = mi.format_timestamp_rekap(datetime(2026, 6, 20, 7, 8, 24))
        self.assertEqual(hasil, "20/06/2026 07:08:24")

    def test_hitung_durasi_total_jam_menit(self):
        from datetime import datetime
        started = datetime(2026, 6, 20, 1, 18, 24)
        up = datetime(2026, 6, 20, 7, 8, 24)
        self.assertEqual(mi.hitung_durasi_total(started, up), "05:50")

    def test_hitung_durasi_total_none_saat_started_kosong(self):
        from datetime import datetime
        self.assertIsNone(mi.hitung_durasi_total(None, datetime(2026, 6, 20, 7, 0)))

    def test_hitung_durasi_total_none_saat_negatif(self):
        from datetime import datetime
        started = datetime(2026, 6, 20, 8, 0)
        up = datetime(2026, 6, 20, 7, 0)
        self.assertIsNone(mi.hitung_durasi_total(started, up))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_mirror_isp.TestHelperRekap -v`
Expected: FAIL dengan `AttributeError: module 'mirror_isp' has no attribute 'HEADER_REKAP'`.

- [ ] **Step 3: Write minimal implementation**

Di `mirror_isp.py`, dalam blok `KONFIGURASI METADATA OLT` setelah baris `GID_SHEET_DH = 1918665126` (baris 67), tambahkan:

```python
GID_SHEET_REKAP = 320650666

HEADER_REKAP = [
    "NO", "DISTRICT", "HOSTNAME", "DURASI DOWN", "SEVERITY",
    "NodeB", "OLO", "K2", "K3", "DH", "DS", "HIPOTESA",
    "STATUS", "TIMESTAMP",
]
```

Tambahkan dua fungsi helper. Letakkan tepat setelah fungsi `normalisasi_waktu` (sekitar baris 225, sebelum `waktu_mulai_alarm`):

```python
def format_timestamp_rekap(waktu):
    waktu = normalisasi_waktu(waktu) or datetime.now()
    return waktu.strftime("%d/%m/%Y %H:%M:%S")


def hitung_durasi_total(started_at, waktu_up):
    started_at = normalisasi_waktu(started_at)
    waktu_up = normalisasi_waktu(waktu_up)
    if started_at is None or waktu_up is None:
        return None
    total_menit = int((waktu_up - started_at).total_seconds() // 60)
    if total_menit < 0:
        return None
    return f"{total_menit // 60:02d}:{total_menit % 60:02d}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_mirror_isp.TestHelperRekap -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add mirror_isp.py tests/test_mirror_isp.py
git commit -m "feat(rekap): tambah konstanta header + helper timestamp/durasi rekap OLT"
```

---

### Task 2: `bangun_baris_rekap` — pembentuk baris 14 sel

**Files:**
- Modify: `mirror_isp.py` (tambah fungsi setelah `ambil_mapping_metadata`, sekitar baris 503)
- Test: `tests/test_mirror_isp.py`

**Interfaces:**
- Consumes: `normalisasi_hostname`, `normalisasi_severity`, `tentukan_hipotesa_down` (sudah ada).
- Produces: `bangun_baris_rekap(no, info, mapping_metadata, status, timestamp) -> list[str]` (14 elemen string). `info` = `"DISTRICT | HOSTNAME | DURASI | NODEB | ..."` (format `data_gpon_down`). `mapping_metadata` boleh `None`/`{}`.

- [ ] **Step 1: Write the failing test**

Tambahkan di `tests/test_mirror_isp.py`:

```python
class TestBangunBarisRekap(TestCase):
    def setUp(self):
        self.data_pln_down_lama = mi.data_pln_down.copy()
        mi.data_pln_down.clear()

    def tearDown(self):
        mi.data_pln_down.clear()
        mi.data_pln_down.update(self.data_pln_down_lama)

    def test_baris_down_lengkap_severity_polos(self):
        info = "DUMAI | GPON00-D1-BGU-3BGB | 05:50 | 0"
        metadata = {
            "GPON00-D1-BGU-3BGB": {
                "severity": "Very Low", "olo": "0", "k2": "0",
                "k3": "0", "dh": "NON", "ds": "NOK",
            }
        }
        baris = mi.bangun_baris_rekap(
            1, info, metadata, "DOWN", "20/06/2026 07:08:24"
        )
        self.assertEqual(
            baris,
            ["1", "DUMAI", "GPON00-D1-BGU-3BGB", "05:50", "Very Low",
             "0", "0", "0", "0", "NON", "NOK", "Kabel CUT",
             "DOWN", "20/06/2026 07:08:24"],
        )

    def test_default_saat_metadata_kosong(self):
        info = "PADANG | GPON00-D1-XYZ | 00:20 | NB"
        baris = mi.bangun_baris_rekap(3, info, {}, "DOWN", "20/06/2026 08:00:00")
        # severity default 'Very Low', olo/k2/k3 '0', dh/ds '-'
        self.assertEqual(baris[0], "3")
        self.assertEqual(baris[4], "Very Low")
        self.assertEqual(baris[5], "NB")
        self.assertEqual(baris[6:11], ["0", "0", "0", "-", "-"])
        self.assertEqual(baris[12], "DOWN")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_mirror_isp.TestBangunBarisRekap -v`
Expected: FAIL `AttributeError: ... 'bangun_baris_rekap'`.

- [ ] **Step 3: Write minimal implementation**

Di `mirror_isp.py`, setelah fungsi `ambil_mapping_metadata` (baris 503):

```python
def bangun_baris_rekap(no, info, mapping_metadata, status, timestamp):
    """Bentuk satu baris rekap 14 kolom (A-N) untuk Google Sheet."""
    bagian = [nilai.strip() for nilai in str(info or "").split("|")]
    bagian += [""] * (4 - len(bagian))

    district = bagian[0] or "-"
    hostname = normalisasi_hostname(bagian[1]) or "-"
    durasi_down = bagian[2] or "-"
    node_b = bagian[3] or "0"

    metadata = (mapping_metadata or {}).get(hostname, {})
    severity = normalisasi_severity(metadata.get("severity", "")) or "Very Low"
    olo = str(metadata.get("olo", "") or "").strip() or "0"
    k2 = str(metadata.get("k2", "") or "").strip() or "0"
    k3 = str(metadata.get("k3", "") or "").strip() or "0"
    dh = str(metadata.get("dh", "") or "").strip() or "-"
    ds = str(metadata.get("ds", "") or "").strip() or "-"
    hipotesa = tentukan_hipotesa_down(hostname, durasi_down)

    return [
        str(no), district, hostname, durasi_down, severity,
        node_b, olo, k2, k3, dh, ds, hipotesa, status, timestamp,
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_mirror_isp.TestBangunBarisRekap -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add mirror_isp.py tests/test_mirror_isp.py
git commit -m "feat(rekap): bangun_baris_rekap (14 kolom, severity polos)"
```

---

### Task 3: `indeks_insiden_aktif` — peta hostname→baris untuk STATUS=DOWN

**Files:**
- Modify: `mirror_isp.py` (tambah fungsi setelah `bangun_baris_rekap`)
- Test: `tests/test_mirror_isp.py`

**Interfaces:**
- Consumes: `normalisasi_hostname`.
- Produces: `indeks_insiden_aktif(semua_nilai: list[list[str]]) -> dict[str, int]`. Key = hostname ter-normalisasi; value = nomor baris 1-based di sheet. Hanya baris dengan `STATUS=DOWN`. Baris 0 (header) dilewati. Bila hostname muncul lebih dari sekali sebagai DOWN, ambil yang paling bawah.

- [ ] **Step 1: Write the failing test**

```python
class TestIndeksInsidenAktif(TestCase):
    def test_hanya_status_down_dan_paling_bawah(self):
        semua_nilai = [
            mi.HEADER_REKAP,
            ["1", "DUMAI", "GPON00-A", "05:50", "Very Low", "0", "0", "0",
             "0", "NON", "NOK", "Kabel CUT", "UP", "20/06/2026 07:00:00"],
            ["2", "DUMAI", "GPON00-B", "01:00", "Very Low", "0", "0", "0",
             "0", "NON", "NOK", "Kabel CUT", "DOWN", "20/06/2026 07:30:00"],
            ["3", "DUMAI", "GPON00-B", "00:10", "Very Low", "0", "0", "0",
             "0", "NON", "NOK", "Kabel CUT", "DOWN", "20/06/2026 09:00:00"],
        ]
        indeks = mi.indeks_insiden_aktif(semua_nilai)
        self.assertNotIn("GPON00-A", indeks)   # UP, bukan aktif
        self.assertEqual(indeks["GPON00-B"], 4)  # baris paling bawah (1-based)

    def test_sheet_kosong_header_saja(self):
        self.assertEqual(mi.indeks_insiden_aktif([mi.HEADER_REKAP]), {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_mirror_isp.TestIndeksInsidenAktif -v`
Expected: FAIL `AttributeError: ... 'indeks_insiden_aktif'`.

- [ ] **Step 3: Write minimal implementation**

```python
def indeks_insiden_aktif(semua_nilai):
    """Peta hostname -> nomor baris (1-based) untuk baris STATUS=DOWN."""
    indeks = {}
    for i, baris in enumerate(semua_nilai):
        if i == 0:
            continue  # header
        nilai = [str(item or "").strip() for item in baris]
        nilai += [""] * (14 - len(nilai))
        hostname = normalisasi_hostname(nilai[2])
        status = nilai[12].strip().upper()
        if hostname and status == "DOWN":
            indeks[hostname] = i + 1
    return indeks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_mirror_isp.TestIndeksInsidenAktif -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add mirror_isp.py tests/test_mirror_isp.py
git commit -m "feat(rekap): indeks_insiden_aktif untuk lookup baris DOWN"
```

---

### Task 4: `rencana_tulis_rekap` — planner inti (append vs update vs finalisasi)

**Files:**
- Modify: `mirror_isp.py` (tambah fungsi setelah `indeks_insiden_aktif`)
- Test: `tests/test_mirror_isp.py`

**Interfaces:**
- Consumes: `bangun_baris_rekap`, `indeks_insiden_aktif`, `hitung_durasi_total`, `normalisasi_hostname`, `format_timestamp_rekap`.
- Produces: `rencana_tulis_rekap(semua_nilai, mapping_metadata, down_items, up_items, waktu) -> tuple[list[tuple[int, list[str]]], list[list[str]]]`.
  - `down_items`: `list[str]` info string OLT down.
  - `up_items`: `list[dict]` `{"hostname": str, "started_at": datetime|None}`.
  - Return `(updates, appends)`: `updates` = list `(nomor_baris_1based, baris14)`; `appends` = list `baris14`.
  - Asumsi: `semua_nilai[0]` = header (dijamin caller).

- [ ] **Step 1: Write the failing test**

```python
class TestRencanaTulisRekap(TestCase):
    def setUp(self):
        from datetime import datetime
        self.dt = datetime
        self.data_pln_down_lama = mi.data_pln_down.copy()
        mi.data_pln_down.clear()
        self.metadata = {
            "GPON00-D1-BGU-3BGB": {
                "severity": "Very Low", "olo": "0", "k2": "0",
                "k3": "0", "dh": "NON", "ds": "NOK",
            }
        }

    def tearDown(self):
        mi.data_pln_down.clear()
        mi.data_pln_down.update(self.data_pln_down_lama)

    def test_down_baru_diappend_dengan_no_berurutan(self):
        semua_nilai = [mi.HEADER_REKAP]
        updates, appends = mi.rencana_tulis_rekap(
            semua_nilai, self.metadata,
            ["DUMAI | GPON00-D1-BGU-3BGB | 05:50 | 0"], [],
            self.dt(2026, 6, 20, 7, 8, 24),
        )
        self.assertEqual(updates, [])
        self.assertEqual(len(appends), 1)
        self.assertEqual(appends[0][0], "1")            # NO
        self.assertEqual(appends[0][3], "05:50")        # DURASI
        self.assertEqual(appends[0][12], "DOWN")        # STATUS
        self.assertEqual(appends[0][13], "20/06/2026 07:08:24")

    def test_re_alert_update_in_place_pertahankan_no(self):
        baris_lama = ["7", "DUMAI", "GPON00-D1-BGU-3BGB", "05:50", "Very Low",
                      "0", "0", "0", "0", "NON", "NOK", "Kabel CUT",
                      "DOWN", "20/06/2026 07:08:24"]
        semua_nilai = [mi.HEADER_REKAP, baris_lama]
        updates, appends = mi.rencana_tulis_rekap(
            semua_nilai, self.metadata,
            ["DUMAI | GPON00-D1-BGU-3BGB | 06:20 | 0"], [],
            self.dt(2026, 6, 20, 7, 38, 24),
        )
        self.assertEqual(appends, [])
        self.assertEqual(len(updates), 1)
        nomor_baris, baris = updates[0]
        self.assertEqual(nomor_baris, 2)
        self.assertEqual(baris[0], "7")                 # NO dipertahankan
        self.assertEqual(baris[3], "06:20")             # DURASI refresh
        self.assertEqual(baris[12], "DOWN")
        self.assertEqual(baris[13], "20/06/2026 07:38:24")

    def test_up_finalisasi_bekukan_durasi_total(self):
        baris_lama = ["1", "DUMAI", "GPON00-D1-BGU-3BGB", "05:30", "Very Low",
                      "0", "0", "0", "0", "NON", "NOK", "Kabel CUT",
                      "DOWN", "20/06/2026 06:50:00"]
        semua_nilai = [mi.HEADER_REKAP, baris_lama]
        updates, appends = mi.rencana_tulis_rekap(
            semua_nilai, self.metadata, [],
            [{"hostname": "GPON00-D1-BGU-3BGB",
              "started_at": self.dt(2026, 6, 20, 1, 18, 24)}],
            self.dt(2026, 6, 20, 7, 8, 24),
        )
        self.assertEqual(appends, [])
        nomor_baris, baris = updates[0]
        self.assertEqual(nomor_baris, 2)
        self.assertEqual(baris[0], "1")                 # NO dipertahankan
        self.assertEqual(baris[3], "05:50")             # total outage beku
        self.assertEqual(baris[11], "Kabel CUT")        # HIPOTESA dipertahankan
        self.assertEqual(baris[12], "UP")
        self.assertEqual(baris[13], "20/06/2026 07:08:24")

    def test_up_tanpa_started_at_pertahankan_durasi_lama(self):
        baris_lama = ["1", "DUMAI", "GPON00-D1-BGU-3BGB", "06:20", "Very Low",
                      "0", "0", "0", "0", "NON", "NOK", "Kabel CUT",
                      "DOWN", "20/06/2026 06:50:00"]
        semua_nilai = [mi.HEADER_REKAP, baris_lama]
        updates, _ = mi.rencana_tulis_rekap(
            semua_nilai, self.metadata, [],
            [{"hostname": "GPON00-D1-BGU-3BGB", "started_at": None}],
            self.dt(2026, 6, 20, 7, 8, 24),
        )
        _, baris = updates[0]
        self.assertEqual(baris[3], "06:20")             # durasi lama dipertahankan
        self.assertEqual(baris[12], "UP")

    def test_up_yatim_dilewati(self):
        updates, appends = mi.rencana_tulis_rekap(
            [mi.HEADER_REKAP], self.metadata, [],
            [{"hostname": "GPON00-TIDAK-ADA", "started_at": None}],
            self.dt(2026, 6, 20, 7, 0, 0),
        )
        self.assertEqual((updates, appends), ([], []))

    def test_down_lagi_setelah_up_append_baris_baru(self):
        baris_up = ["1", "DUMAI", "GPON00-D1-BGU-3BGB", "05:50", "Very Low",
                    "0", "0", "0", "0", "NON", "NOK", "Kabel CUT",
                    "UP", "20/06/2026 07:08:24"]
        semua_nilai = [mi.HEADER_REKAP, baris_up]
        updates, appends = mi.rencana_tulis_rekap(
            semua_nilai, self.metadata,
            ["DUMAI | GPON00-D1-BGU-3BGB | 00:05 | 0"], [],
            self.dt(2026, 6, 20, 14, 0, 0),
        )
        self.assertEqual(updates, [])
        self.assertEqual(len(appends), 1)
        self.assertEqual(appends[0][0], "2")            # NO berikutnya
        self.assertEqual(appends[0][12], "DOWN")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_mirror_isp.TestRencanaTulisRekap -v`
Expected: FAIL `AttributeError: ... 'rencana_tulis_rekap'`.

- [ ] **Step 3: Write minimal implementation**

```python
def rencana_tulis_rekap(semua_nilai, mapping_metadata, down_items, up_items, waktu):
    """Tentukan update in-place & baris append untuk rekap insiden OLT.

    Return (updates, appends):
      updates = [(nomor_baris_1based, baris14), ...]
      appends = [baris14, ...]
    """
    aktif = indeks_insiden_aktif(semua_nilai)
    timestamp = format_timestamp_rekap(waktu)
    no_berikutnya = len(semua_nilai)  # header(1)+data(D) -> NO baru = D+1 = len

    updates = []
    appends = []

    for info in down_items or []:
        bagian = [nilai.strip() for nilai in str(info or "").split("|")]
        bagian += [""] * (2 - len(bagian))
        hostname = normalisasi_hostname(bagian[1])
        if not hostname:
            continue
        if hostname in aktif:
            nomor_baris = aktif[hostname]
            baris_lama = semua_nilai[nomor_baris - 1]
            no_lama = str((baris_lama[0] if baris_lama else "") or no_berikutnya)
            baris = bangun_baris_rekap(
                no_lama, info, mapping_metadata, "DOWN", timestamp
            )
            updates.append((nomor_baris, baris))
        else:
            baris = bangun_baris_rekap(
                no_berikutnya, info, mapping_metadata, "DOWN", timestamp
            )
            appends.append(baris)
            no_berikutnya += 1

    for item in up_items or []:
        hostname = normalisasi_hostname(item.get("hostname"))
        if not hostname or hostname not in aktif:
            continue  # tak ada insiden aktif -> tak ada yang difinalisasi
        nomor_baris = aktif[hostname]
        baris = [str(x or "").strip() for x in semua_nilai[nomor_baris - 1]]
        baris += [""] * (14 - len(baris))
        durasi_total = hitung_durasi_total(item.get("started_at"), waktu)
        if durasi_total:
            baris[3] = durasi_total
        baris[12] = "UP"
        baris[13] = timestamp
        updates.append((nomor_baris, baris))

    return updates, appends
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_mirror_isp.TestRencanaTulisRekap -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add mirror_isp.py tests/test_mirror_isp.py
git commit -m "feat(rekap): rencana_tulis_rekap (append/update/finalisasi insiden)"
```

---

### Task 5: `tulis_rekap_olt` — I/O ke Google Sheet (scope tulis sendiri)

**Files:**
- Modify: `mirror_isp.py` (tambah fungsi setelah `rencana_tulis_rekap`)
- Test: `tests/test_mirror_isp.py`

**Interfaces:**
- Consumes: `rencana_tulis_rekap`, `HEADER_REKAP`, `GID_SHEET_REKAP`, `SPREADSHEET_ID_METADATA`, `FILE_KREDENSIAL_GOOGLE`, modul `gspread` & `ServiceAccountCredentials`.
- Produces: `tulis_rekap_olt(mapping_metadata, down_items, up_items, waktu) -> None`. Membuka spreadsheet dengan scope tulis sendiri (`https://www.googleapis.com/auth/spreadsheets`), pastikan header, baca `get_all_values`, terapkan `batch_update` (range `A{n}:N{n}`, RAW) + `append_rows` (RAW). No-op bila `down_items` & `up_items` kosong atau dependency belum ada.

- [ ] **Step 1: Write the failing test**

```python
class TestTulisRekapOlt(TestCase):
    def setUp(self):
        self.data_pln_down_lama = mi.data_pln_down.copy()
        mi.data_pln_down.clear()

    def tearDown(self):
        mi.data_pln_down.clear()
        mi.data_pln_down.update(self.data_pln_down_lama)

    def _fake_worksheet(self, semua_nilai):
        ws = mock.Mock()
        ws.get_all_values.return_value = semua_nilai
        return ws

    def test_append_baris_baru_dan_header_saat_kosong(self):
        from datetime import datetime
        ws = self._fake_worksheet([])  # sheet benar-benar kosong
        with (
            mock.patch.object(mi, "gspread") as gspread_mock,
            mock.patch.object(mi, "ServiceAccountCredentials"),
            mock.patch.object(mi, "simpan_log"),
        ):
            (gspread_mock.authorize.return_value
             .open_by_key.return_value
             .get_worksheet_by_id.return_value) = ws
            mi.tulis_rekap_olt(
                {"GPON00-D1-BGU-3BGB": {"severity": "Very Low", "olo": "0",
                 "k2": "0", "k3": "0", "dh": "NON", "ds": "NOK"}},
                ["DUMAI | GPON00-D1-BGU-3BGB | 05:50 | 0"],
                [],
                datetime(2026, 6, 20, 7, 8, 24),
            )
        ws.append_row.assert_called_once_with(
            mi.HEADER_REKAP, value_input_option="RAW"
        )
        ws.append_rows.assert_called_once()
        baris_baru = ws.append_rows.call_args.args[0]
        self.assertEqual(baris_baru[0][2], "GPON00-D1-BGU-3BGB")
        self.assertEqual(baris_baru[0][12], "DOWN")

    def test_update_in_place_pakai_batch_update(self):
        from datetime import datetime
        baris_lama = ["1", "DUMAI", "GPON00-D1-BGU-3BGB", "05:50", "Very Low",
                      "0", "0", "0", "0", "NON", "NOK", "Kabel CUT",
                      "DOWN", "20/06/2026 07:08:24"]
        ws = self._fake_worksheet([mi.HEADER_REKAP, baris_lama])
        with (
            mock.patch.object(mi, "gspread") as gspread_mock,
            mock.patch.object(mi, "ServiceAccountCredentials"),
            mock.patch.object(mi, "simpan_log"),
        ):
            (gspread_mock.authorize.return_value
             .open_by_key.return_value
             .get_worksheet_by_id.return_value) = ws
            mi.tulis_rekap_olt(
                {}, ["DUMAI | GPON00-D1-BGU-3BGB | 06:20 | 0"], [],
                datetime(2026, 6, 20, 7, 38, 24),
            )
        ws.append_rows.assert_not_called()
        ws.batch_update.assert_called_once()
        data = ws.batch_update.call_args.args[0]
        self.assertEqual(data[0]["range"], "A2:N2")
        self.assertEqual(data[0]["values"][0][3], "06:20")

    def test_noop_saat_tidak_ada_item(self):
        from datetime import datetime
        with mock.patch.object(mi, "gspread") as gspread_mock:
            mi.tulis_rekap_olt({}, [], [], datetime(2026, 6, 20, 7, 0, 0))
        gspread_mock.authorize.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_mirror_isp.TestTulisRekapOlt -v`
Expected: FAIL `AttributeError: ... 'tulis_rekap_olt'`.

- [ ] **Step 3: Write minimal implementation**

```python
def tulis_rekap_olt(mapping_metadata, down_items, up_items, waktu):
    """Tulis rekap insiden OLT ke tab GID_SHEET_REKAP (incident log)."""
    if not down_items and not up_items:
        return
    if gspread is None or ServiceAccountCredentials is None:
        simpan_log("Lewati tulis rekap OLT: dependency gspread/oauth2client belum ada")
        return

    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        FILE_KREDENSIAL_GOOGLE, scope
    )
    client_gs = gspread.authorize(credentials)
    spreadsheet = client_gs.open_by_key(SPREADSHEET_ID_METADATA)
    worksheet = spreadsheet.get_worksheet_by_id(GID_SHEET_REKAP)

    semua_nilai = worksheet.get_all_values()
    if not semua_nilai:
        worksheet.append_row(HEADER_REKAP, value_input_option="RAW")
        semua_nilai = [HEADER_REKAP]

    updates, appends = rencana_tulis_rekap(
        semua_nilai, mapping_metadata, down_items, up_items, waktu
    )

    if updates:
        data = [
            {"range": f"A{nomor_baris}:N{nomor_baris}", "values": [baris]}
            for nomor_baris, baris in updates
        ]
        worksheet.batch_update(data, value_input_option="RAW")
    if appends:
        worksheet.append_rows(appends, value_input_option="RAW")

    simpan_log(
        f"✅ Rekap OLT Sheet diperbarui: {len(updates)} update, "
        f"{len(appends)} baris baru (GID {GID_SHEET_REKAP})"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_mirror_isp.TestTulisRekapOlt -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add mirror_isp.py tests/test_mirror_isp.py
git commit -m "feat(rekap): tulis_rekap_olt I/O batch ke Sheet GID 320650666"
```

---

### Task 6: Hook ke `proses_pesan_baru` (kumpulkan down/up items + panggil writer)

**Files:**
- Modify: `mirror_isp.py` (`proses_pesan_baru`, baris ~649–757)
- Test: `tests/test_mirror_isp.py`

**Interfaces:**
- Consumes: `tulis_rekap_olt`, `data_gpon_down`, `data_gpon_down_meta`, `hostname_terupdate`.
- Produces: efek samping — pemanggilan `tulis_rekap_olt(mapping_metadata, down_rekap_items, up_rekap_items, now)` di blok `if ada_perubahan:`, dibungkus `try/except`.

- [ ] **Step 1: Write the failing test**

```python
class TestHookRekapProsesPesan(TestCase):
    def setUp(self):
        self.snapshot = {
            name: getattr(mi, name).copy()
            for name in ("data_gpon_down", "data_gpon_up", "data_gpon_down_meta",
                         "data_pln_down", "data_pln_down_meta")
        }
        for name in self.snapshot:
            getattr(mi, name).clear()

    def tearDown(self):
        for name, nilai in self.snapshot.items():
            getattr(mi, name).clear()
            getattr(mi, name).update(nilai)

    def test_event_down_memanggil_tulis_rekap_dengan_down_items(self):
        event = SimpleNamespace(
            text=(
                "!PROGRAM ZERO GAMAS OLT!\n"
                "- DISTRICT DUMAI\n"
                "GPON00-D1-BGU-3BGB | 05:50 | 0"
            ),
            date=datetime(2026, 6, 20, 7, 8),
        )
        with (
            mock.patch.object(mi, "ambil_mapping_metadata", return_value={}),
            mock.patch.object(mi, "simpan_ke_file_laporan"),
            mock.patch.object(mi, "kirim_pesan_wa"),
            mock.patch.object(mi, "tulis_rekap_olt") as tulis_mock,
            mock.patch.object(mi, "simpan_log"),
        ):
            asyncio.run(mi.proses_pesan_baru(event))

        tulis_mock.assert_called_once()
        down_items = tulis_mock.call_args.args[1]
        self.assertTrue(any("GPON00-D1-BGU-3BGB" in s for s in down_items))

    def test_event_up_mengirim_started_at(self):
        # Pra-kondisi: OLT sedang down dengan started_at diketahui
        mi.data_gpon_down["GPON00-D1-BGU-3BGB"] = (
            "DUMAI | GPON00-D1-BGU-3BGB | 05:50 | 0"
        )
        mi.data_gpon_down_meta["GPON00-D1-BGU-3BGB"] = {
            "duration": "05:50",
            "started_at": datetime(2026, 6, 20, 1, 18),
        }
        event = SimpleNamespace(
            text="GPON00-D1-BGU-3BGB | UP",
            date=datetime(2026, 6, 20, 7, 8),
        )
        with (
            mock.patch.object(mi, "ambil_mapping_metadata", return_value={}),
            mock.patch.object(mi, "simpan_ke_file_laporan"),
            mock.patch.object(mi, "kirim_pesan_wa"),
            mock.patch.object(mi, "tulis_rekap_olt") as tulis_mock,
            mock.patch.object(mi, "simpan_log"),
        ):
            asyncio.run(mi.proses_pesan_baru(event))

        up_items = tulis_mock.call_args.args[2]
        self.assertEqual(up_items[0]["hostname"], "GPON00-D1-BGU-3BGB")
        self.assertEqual(up_items[0]["started_at"], datetime(2026, 6, 20, 1, 18))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_mirror_isp.TestHookRekapProsesPesan -v`
Expected: FAIL — `tulis_rekap_olt` belum dipanggil (`assert_called_once` gagal / `AttributeError` di `up_items`).

- [ ] **Step 3: Write minimal implementation**

Di `proses_pesan_baru`:

(a) Setelah `hostname_terupdate = set()` (baris 650), tambahkan:

```python
        up_rekap_items = []
```

(b) Di branch GPON UP, ganti blok (baris 706–711):

```python
                        if hostname in data_gpon_down:
                            hapus_alarm_down(
                                data_gpon_down,
                                data_gpon_down_meta,
                                hostname,
                            )
```

menjadi:

```python
                        if hostname in data_gpon_down:
                            started_at = data_gpon_down_meta.get(
                                hostname, {}
                            ).get("started_at")
                            up_rekap_items.append({
                                "hostname": hostname,
                                "started_at": started_at,
                            })
                            hapus_alarm_down(
                                data_gpon_down,
                                data_gpon_down_meta,
                                hostname,
                            )
```

(c) Di blok `if ada_perubahan:`, setelah `kirim_pesan_wa(teks_laporan_baru)` (baris 747), tambahkan:

```python
            down_rekap_items = [
                data_gpon_down[h]
                for h in hostname_terupdate
                if h in data_gpon_down
            ]
            if down_rekap_items or up_rekap_items:
                try:
                    tulis_rekap_olt(
                        mapping_metadata,
                        down_rekap_items,
                        up_rekap_items,
                        datetime.now(),
                    )
                except Exception as exc:
                    simpan_log(f"❌ Gagal menulis rekap OLT ke Sheet: {exc}")
```

- [ ] **Step 4: Run full suite to verify it passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_mirror_isp -v`
Expected: PASS semua (18 lama + tambahan baru). Tidak ada regресi.

- [ ] **Step 5: Commit**

```bash
git add mirror_isp.py tests/test_mirror_isp.py
git commit -m "feat(rekap): hook proses_pesan_baru menulis rekap OLT ke Sheet"
```

---

## Self-Review

**Spec coverage:**
- Model incident-log (append/update/finalisasi/down-lagi) → Task 4 (planner) + Task 6 (hook).
- Skema 14 kolom + HIPOTESA + SEVERITY polos → Task 2.
- DURASI saat UP = total outage, fallback durasi lama → Task 1 (`hitung_durasi_total`) + Task 4.
- Tahan-restart (lookup dari sheet) → Task 3 + Task 4.
- Batch read/write hemat kuota, RAW → Task 5.
- Header otomatis tanpa auto-format → Task 5.
- Scope tulis terpisah + try/except tak ganggu WA → Task 5 + Task 6.
- Prasyarat Editor = aksi manual user (Global Constraints), bukan langkah kode.

**Placeholder scan:** Tidak ada TODO/TBD; semua step berisi kode nyata + perintah + output yang diharapkan.

**Type consistency:** `bangun_baris_rekap` → `list[str]` 14 elemen dipakai konsisten di Task 4/5. `rencana_tulis_rekap` return `(updates: list[(int,list)], appends: list[list])` dipakai persis di `tulis_rekap_olt`. `up_items` dict `{"hostname","started_at"}` konsisten Task 4 ↔ Task 6.

**Catatan deviasi dari spec (disengaja):** scope OAuth tulis ditaruh di fungsi writer baru; `ambil_mapping_metadata` (sudah ada & teruji) tetap readonly — lebih kecil risikonya, intent sama.
