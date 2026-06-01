# Desain: `kirim_manja.py`

**Tanggal:** 2026-06-01
**Status:** Disetujui (menunggu review spec)

## Tujuan

Script pemantau Google Sheet yang mendeteksi perubahan pada 4 table alarm tiket,
lalu mengirim laporan **teks** (bukan screenshot) ke grup WhatsApp via WAHA API.
MANJA/DIAMOND/PLATINUM dirutekan per-distrik; >72 JAM dirutekan per-distrik **dan**
versi utuh ke grup inti.

Referensi pola dari script existing:
- `kirim_wo.py` — baca gspread (`_buka_sheet`, `_kolom_ke_indeks`), auth service account.
- `mirror_isp.py` — kirim teks WAHA (`/api/sendText`, payload `{session, chatId, text}`).
- `mirror_tikor.py` — polling dengan backoff (diadaptasi ke versi sinkron).

**Catatan arah:** Karena output berupa teks saja, logika screenshot `mirror_insera.py`
(Playwright, Telethon, asyncio, PIL) **tidak dipakai**. Script ini sinkron sederhana:
`gspread` + `requests` + loop `while True`.

## Sumber Data

- Satu Google Sheet, satu worksheet (GID). Semua 4 table ada di worksheet yang sama.
- Data dibaca sekali per siklus via `sheet.get_all_values()` (1 API read/siklus → hemat kuota).
- Baris 4 = header tiap table. Data mulai **baris 5** ke bawah.

## Definisi 4 Table

Tiap table dikonfigurasi deklaratif (dict). Kolom dipetakan via huruf → indeks 0-based.

| Table key | Judul caption | Range | Kolom (urut) | Kolom DISTRIK (filter) | Field tampil + header |
|---|---|---|---|---|---|
| `MANJA`    | Alarm 3 Jam Manja Open | B5:F | B,C,D,E,F | **F** | Tiket(B), Jam Booking(C), STO(D), SA(E) |
| `DIAMOND`  | Alarm 3 Jam Diamond    | H5:L | H,I,J,K,L | **L** | Tiket(H), Open Berjalan (Jam)(I), STO(J), SA(K) |
| `PLATINUM` | Alarm 6 Jam Platinum   | N5:R | N,O,P,Q,R | **R** | Tiket(N), Open Berjalan (Jam)(O), STO(P), SA(Q) |
| `JAM72`    | Alarm 72 Jam Tiket Open | U5:X | U,V,W,X | **X** | Tiket(U), Open Berjalan (Jam)(V), STO(W), Distrik(X) |

Aturan kolom:
- **MANJA / DIAMOND / PLATINUM**: field ke-4 = SA. Kolom DISTRIK dipakai **filter saja**
  (tidak ditampilkan di caption).
- **JAM72**: hanya 4 kolom. Kolom DISTRIK (X) dipakai **filter sekaligus ditampilkan**
  sebagai field ke-4 (tidak ada SA).

Baris dianggap kosong (dilewati) bila kolom Tiket kosong/whitespace.

## Header Caption per Table

- MANJA: `Tiket | Jam Booking | STO | SA`
- DIAMOND: `Tiket | Open Berjalan (Jam) | STO | SA`
- PLATINUM: `Tiket | Open Berjalan (Jam) | STO | SA`
- JAM72: `Tiket | Open Berjalan (Jam) | STO | Distrik`

## Distrik → Grup (placeholder)

5 distrik kanonik. Nama dinormalisasi: uppercase + hapus semua spasi, sehingga
`"Bukit Tinggi"`, `"BUKIT TINGGI"`, `"Bukittinggi"` → `"BUKITTINGGI"`.

```python
DISTRIK_GRUP = {
    "BATAM":       "120363xxxBATAM@g.us",
    "PEKANBARU":   "120363xxxPKU@g.us",
    "DUMAI":       "120363xxxDUMAI@g.us",
    "BUKITTINGGI": "120363xxxBKT@g.us",
    "PADANG":      "120363xxxPDG@g.us",
}
GRUP_INTI = "120363xxxINTI@g.us"
```

Baris dengan nilai distrik di luar 5 kanonik → dilewati (di-log sebagai peringatan),
tidak dikirim ke grup mana pun (kecuali tetap masuk hitungan versi inti JAM72).

## Routing

| Table | Per-distrik (grup masing2) | Grup inti (utuh) |
|---|---|---|
| MANJA | ✅ | — |
| DIAMOND | ✅ | — |
| PLATINUM | ✅ | — |
| JAM72 | ✅ (judul `... \| <Distrik>`) | ✅ (judul tanpa suffix, semua baris lintas distrik) |

## Format Caption

Judul **semua versi per-distrik** memakai suffix `| <Distrik>` (nama distrik asli/ditampilkan rapi).
Versi grup inti JAM72 **tanpa** suffix.

Contoh MANJA (Batam):
```
Alarm 3 Jam Manja Open | Batam
==============
Tiket | Jam Booking | STO | SA
INC49847623 | 2026-06-01 15:00:00.0 | SLU | SA SAGULUNG
```

Contoh JAM72 grup inti (utuh):
```
Alarm 72 Jam Tiket Open
==============
Tiket | Open Berjalan (Jam) | STO | Distrik
INC49847623 | 12 | SLU | Batam
```

Struktur: `judul` + newline + `==============` + newline + `header` + newline +
satu baris per data (field di-join dengan ` | `). Sel kosong → string kosong.

## Deteksi Perubahan

- Snapshot di memori: `dict` dengan kunci `(table_key, distrik_norm)` → hash subset.
- Untuk JAM72 versi inti, kunci khusus `("JAM72", "__INTI__")` → hash seluruh baris JAM72
  lintas distrik (urut sesuai sheet).
- Hash = deterministik atas konten subset (mis. `hashlib.md5` dari representasi baris).
- Per siklus: hitung ulang hash tiap (table × distrik) yang punya baris + kunci inti JAM72.
  - Hash berbeda dari snapshot → **kirim** ke tujuannya, lalu perbarui snapshot.
  - Hash sama → lewati.
  - Distrik tanpa baris → snapshot di-set ke nilai "kosong" (mis. hash string kosong),
    tidak kirim pesan kosong. (Transisi ada-data → kosong dianggap perubahan? Tidak — kita
    tidak mengirim pesan "kosong"; hanya update snapshot agar tidak salah deteksi nanti.)

### First-run = baseline diam
Siklus pertama mengisi seluruh snapshot **tanpa mengirim apa pun**. Pesan baru hanya
terkirim untuk perubahan yang terjadi setelah start. Snapshot hanya di memori (tidak
persist ke disk) — restart = baseline ulang.

## Polling Adaptif (backoff sinkron)

- Interval awal: **30 detik**.
- Satu siklus penuh tanpa perubahan apa pun → interval ×1.5 (dibulatkan), maks **300 detik**.
- Ada minimal satu perubahan terkirim → reset interval ke 30 detik.
- `time.sleep(interval)` di akhir tiap siklus.

## Ketahanan & Logging

- `catat_log(pesan)` + folder `logs/`, file `logs/kirim_manja_log.txt`, auto-reset harian
  (pola identik script lain).
- Error dalam satu siklus (network, API gspread/WAHA, parsing) di-`try/except`, di-log,
  loop **lanjut** ke siklus berikutnya (tidak crash).
- WAHA `sendText` gagal (status non-2xx / exception) → di-log; snapshot untuk (table×distrik)
  itu **tidak** diperbarui agar dicoba lagi siklus berikutnya.

## Struktur Fungsi (unit kecil)

- `_buka_sheet()` — auth service account + ambil worksheet by GID. (dari `kirim_wo.py`)
- `_kolom_ke_indeks(huruf)` — huruf kolom → indeks 1-based. (dari `kirim_wo.py`)
- `tanggal_hari_ini()`, `catat_log(pesan)` — util tanggal & logging. (pola existing)
- `normalisasi_distrik(nama)` — uppercase + hapus spasi → kunci kanonik.
- `ekstrak_table(cfg, semua_nilai)` — kembalikan `dict[distrik_norm] -> list[baris_field]`
  (baris non-kosong, field sudah dipotong sesuai kolom tampil) + list utuh (untuk inti).
- `buat_caption(cfg, judul_suffix, baris_list)` — rakit string caption.
- `hash_subset(baris_list)` — hash deterministik.
- `kirim_teks_wa(chat_id, teks)` — POST `/api/sendText`. (dari `mirror_isp.py`)
- `proses_siklus(snapshot)` — satu putaran: baca sheet, ekstrak, deteksi, kirim. Return
  `(ada_perubahan: bool)`; mutasi `snapshot` di tempat.
- `main()` — loop `while True` + backoff + try/except per siklus.

## Konfigurasi (placeholder yang harus diisi nanti)

- `SPREADSHEET_ID` / `URL_SPREADSHEET`, `GID_SHEET`.
- `FILE_KREDENSIAL = "kunci_rahasia_google.json"` (sudah ada di repo).
- `WAHA_URL`, `WAHA_SESSION`, `WAHA_API_KEY` (samakan dengan script lain).
- `DISTRIK_GRUP` (5 grup) + `GRUP_INTI`.

## Dependensi

`gspread`, `oauth2client`, `requests`, `hashlib` (stdlib). Tidak butuh Playwright/Telethon/PIL/pandas.

## Di Luar Cakupan (YAGNI)

- Tidak ada screenshot/gambar.
- Tidak ada persist snapshot ke disk (baseline ulang saat restart — diterima).
- Tidak ada penyortiran/agregasi baris di luar urutan asli sheet.
- Tidak ada penanganan multi-worksheet/multi-spreadsheet.
