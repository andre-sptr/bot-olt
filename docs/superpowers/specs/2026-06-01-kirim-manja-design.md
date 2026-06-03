# Desain: `kirim_manja.py`

**Tanggal:** 2026-06-01
**Status:** Disetujui untuk implementation planning

## Tujuan

`kirim_manja.py` adalah script polling Google Sheet yang mendeteksi perubahan pada
empat table alarm tiket, lalu mengirim laporan teks WhatsApp via WAHA API.

Script tidak memakai Telegram listener, screenshot, Playwright, PIL, atau pandas.
Referensi utama dari script existing:

- `mirror_insera.py`: konfigurasi WAHA dan Google credential.
- `mirror_isp.py`: pola kirim teks WAHA lewat `/api/sendText`.
- `kirim_wo.py`: pola helper Google Sheet jika dibutuhkan.

## Sumber Data

- Spreadsheet ID: `1Jl-povDud6JKpb4qqB8pRIA0FbpB6lbNomhs9iL5F98`
- Worksheet GID: `1992709075`
- Credential file: `kunci_rahasia_google.json`
- Data dibaca sekali per siklus dengan `worksheet.get_all_values()`.
- Header table berada di baris 4.
- Data mulai baris 5.

## Definisi Table

| Key | Judul | Range | Kolom tampil | Kolom distrik |
| --- | --- | --- | --- | --- |
| `MANJA` | `Alarm 3 Jam Manja Open` | `B5:F` | B, C, D, E | F |
| `DIAMOND` | `Alarm 3 Jam Diamond` | `H5:L` | H, I, J, K | L |
| `PLATINUM` | `Alarm 6 Jam Platinum` | `N5:R` | N, O, P, Q | R |
| `JAM72` | `Alarm 72 Jam Tiket Open` | `U5:X` | U, V, W, X | X |

Header pesan:

- MANJA: `Tiket | Jam Booking | STO | SA`
- DIAMOND: `Tiket | Open Berjalan (Jam) | STO | SA`
- PLATINUM: `Tiket | Open Berjalan (Jam) | STO | SA`
- JAM72: `Tiket | Open Berjalan (Jam) | STO | Distrik`

Baris dianggap kosong dan dilewati bila kolom tiket kosong.

## Distrik dan Routing

Distrik target:

- Batam
- Pekanbaru
- Dumai
- Bukittinggi
- Padang

Normalisasi distrik:

- Trim whitespace.
- Uppercase.
- Hapus semua spasi.
- `BUKIT TINGGI`, `Bukit Tinggi`, dan `Bukittinggi` diperlakukan sebagai `BUKITTINGGI`.

ID grup sementara di-hardcode:

```python
DISTRIK_GRUP = {
    "BATAM": "ISI_GROUP_BATAM@g.us",
    "PEKANBARU": "ISI_GROUP_PEKANBARU@g.us",
    "DUMAI": "ISI_GROUP_DUMAI@g.us",
    "BUKITTINGGI": "ISI_GROUP_BUKITTINGGI@g.us",
    "PADANG": "ISI_GROUP_PADANG@g.us",
}

GRUP_INTI = "ISI_GROUP_INTI@g.us"
```

Routing:

- MANJA: kirim per-distrik.
- DIAMOND: kirim per-distrik.
- PLATINUM: kirim per-distrik.
- JAM72: kirim per-distrik dan kirim versi utuh lintas distrik ke `GRUP_INTI`.

Jika distrik kosong atau di luar target:

- Untuk pesan per-distrik: baris di-skip dan dicatat ke log.
- Untuk JAM72 versi `GRUP_INTI`: baris tetap ikut dikirim karena tidak difilter distrik.

## Format Pesan

Semua pesan per-distrik memakai suffix judul `| <Nama Distrik>`.
Pesan JAM72 untuk `GRUP_INTI` tidak memakai suffix distrik.

Format data:

```text
Alarm 3 Jam Manja Open | Batam
==============
Tiket | Jam Booking | STO | SA
INC49847623 | 2026-06-01 15:00:00.0 | SLU | SA SAGULUNG
```

```text
Alarm 6 Jam Platinum | Batam
==============
Tiket | Open Berjalan (Jam) | STO | SA
INC49847623 | 1 | SLU | SA SAGULUNG
```

```text
Alarm 3 Jam Diamond | Batam
==============
Tiket | Open Berjalan (Jam) | STO | SA
INC49847623 | 1 | SLU | SA SAGULUNG
```

```text
Alarm 72 Jam Tiket Open
==============
Tiket | Open Berjalan (Jam) | STO | Distrik
INC49847623 | 12 | SLU | Batam
```

Format clear saat subset sebelumnya ada data lalu menjadi kosong:

```text
Alarm 3 Jam Manja Open | Batam
==============
CLEAR - Tidak ada tiket aktif.
```

Untuk JAM72 inti:

```text
Alarm 72 Jam Tiket Open
==============
CLEAR - Tidak ada tiket aktif.
```

## Deteksi Perubahan

Script memakai snapshot hash di memori.

Kunci snapshot:

- `(table_key, distrik_norm)` untuk pesan per-distrik.
- `("JAM72", "__INTI__")` untuk versi utuh ke `GRUP_INTI`.

Per siklus:

1. Baca semua nilai sheet.
2. Ekstrak data semua table.
3. Hitung hash deterministic untuk setiap subset.
4. Jika kunci belum ada di snapshot dan subset berisi data, kirim pesan pertama.
5. Jika hash berbeda dari snapshot:
   - subset berisi data: kirim pesan data terbaru.
   - subset kosong setelah sebelumnya berisi data: kirim pesan clear.
6. Update snapshot hanya setelah pengiriman sukses.

First run mengirim semua subset yang berisi data.

Snapshot hanya di memori. Jika script restart, data existing akan dikirim lagi pada siklus pertama.

## Polling

- Interval awal: 30 detik.
- Jika satu siklus penuh tidak mengirim perubahan apa pun, interval dinaikkan 1.5x.
- Interval maksimal: 300 detik.
- Jika ada pesan terkirim, interval kembali ke 30 detik.

## Error Handling dan Logging

- Log folder: `logs`
- Log file: `logs/kirim_manja_log.txt`
- Log auto-reset harian mengikuti pola script existing.
- Error Google Sheet, network, parsing, atau WAHA dicatat dan loop tetap lanjut.
- Jika WAHA gagal untuk sebuah target, snapshot target itu tidak diperbarui agar dicoba lagi pada siklus berikutnya.

## Struktur Fungsi

- `tanggal_hari_ini()`
- `nama_file_log()`
- `catat_log(pesan)`
- `kolom_ke_indeks(huruf)`
- `normalisasi_distrik(nama)`
- `nama_distrik_tampil(distrik_norm)`
- `buka_worksheet()`
- `nilai_cell(semua_nilai, row_idx, col_idx)`
- `ekstrak_table(cfg, semua_nilai)`
- `buat_pesan_data(cfg, judul_suffix, rows)`
- `buat_pesan_clear(cfg, judul_suffix)`
- `hash_rows(rows)`
- `kirim_teks_wa(chat_id, teks)`
- `proses_target(snapshot, key, chat_id, cfg, suffix, rows)`
- `proses_siklus(snapshot)`
- `main()`

## Di Luar Cakupan

- Tidak ada screenshot.
- Tidak ada Telegram listener.
- Tidak ada persist snapshot ke disk.
- Tidak ada sort ulang data.
- Tidak ada pengiriman pesan kosong pada first run untuk subset yang tidak punya data.

## Update 2026-06-03: Tag PIC di pesan grup inti

### Deteksi perubahan tahan jam berjalan

Kolom "Open Berjalan (Jam)" naik tiap recalc, sehingga hash baris ikut berubah dan
pesan terkirim berulang walau set tiket tidak berubah. Tiap table sekarang punya
`volatile_col_idx`: index kolom tampil yang dibuang sebelum hashing (`baris_identitas`).
MANJA `None` (Jam Booking statis), DIAMOND/PLATINUM/JAM72 = `1`.

### Routing tambahan

- MANJA sekarang juga dikirim ke `GRUP_INTI` (selain per-distrik).
- JAM72 tetap dikirim per-distrik dan ke `GRUP_INTI`.
- DIAMOND dan PLATINUM tetap per-distrik saja.

### Format pesan inti (MANJA dan JAM72)

- Judul pakai suffix tetap `| SBT` (`SUFFIX_INTI`).
- Baris dikelompokkan per distrik mengikuti urutan `TARGET_DISTRIK`
  (Batam, Pekanbaru, Dumai, Bukittinggi, Padang); baris distrik di luar target
  ditaruh paling akhir.
- Tiap baris diikuti baris `cc @<nomor> @<nomor> ...` berisi PIC distrik tersebut.
  Baris distrik tanpa PIC tampil tanpa baris `cc`.
- Antar blok baris dipisah satu baris kosong.

Contoh:

```text
Alarm 72 Jam Tiket Open | SBT
==============
Tiket | Open Berjalan (Jam) | STO | Distrik
INC49803589 | 90 | TAK | BATAM
cc @6281376836000 @6281277200469 @6281363210112

INC49803589 | 90 | TAK | PEKAN BARU
cc @6281261323575 @628126465895
```

### Mention WhatsApp

- `kirim_teks_wa(chat_id, teks, mentions=None)` menambahkan `mentions` ke payload
  `/api/sendText` bila ada. Tiap PIC muncul sebagai token `@<digit>` di teks dan
  `<digit>@c.us` di array `mentions` (di-dedup).
- Nomor PIC disimpan di `RAW_PIC_DISTRIK` (format bebas) lalu dinormalisasi ke
  `62...` oleh `normalisasi_nomor` menjadi `PIC_DISTRIK`.
- Catatan operasional: mention WhatsApp hanya memunculkan notifikasi bila nomor PIC
  adalah anggota grup inti.

### Hash pesan inti

`proses_target_inti` menghitung hash atas identitas baris (kolom volatile dibuang)
ditambah distrik ternormalisasi, sehingga perubahan distrik tetap memicu kirim ulang
tapi jam berjalan tidak.
