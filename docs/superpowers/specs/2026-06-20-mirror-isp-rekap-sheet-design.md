# Desain: Rekap OLT Down/Up ke Google Sheet (mirror_isp.py)

Tanggal: 2026-06-20
File yang diubah: `mirror_isp.py`

## Tujuan

Selain mirroring laporan OLT down/up ke WhatsApp (perilaku yang sudah ada),
`mirror_isp.py` juga menulis rekap insiden ke sebuah tab Google Sheet sebagai
**papan insiden (incident log)** yang rapi dan tahan-restart.

- Spreadsheet: `1crQdVmqXoROtuiaB4-ce7sIwJh26oxKMPq3Mj6-GyLU`
  (spreadsheet yang **sama** dengan sumber metadata yang sudah dibaca script).
- Tab tujuan: **GID `320650666`**.

## Model data: incident-based logging

Satu baris = satu **insiden outage**. Baris menumpuk (akumulasi), tidak pernah
di-reset otomatis oleh script (user membersihkan manual bila perlu).

Definisi "insiden aktif untuk hostname X" = baris paling bawah yang
`HOSTNAME = X` **dan** `STATUS = DOWN`.

| Kejadian | Aksi di sheet |
|---|---|
| OLT DOWN pertama (tak ada insiden aktif untuk hostname itu) | **Append** baris baru, `STATUS=DOWN` |
| Alert 30 menit berikutnya (insiden masih aktif) | **Update in-place** baris aktif: refresh `DURASI DOWN`, `HIPOTESA`, `TIMESTAMP`. Tidak ada baris baru → tidak ada spam. |
| OLT UP | **Finalisasi** baris aktif: `STATUS=UP`, `DURASI DOWN` dibekukan ke total outage, `TIMESTAMP` = waktu recover. `HIPOTESA` dipertahankan apa adanya. |
| OLT DOWN lagi setelah pernah UP | Tak ada insiden aktif → **append** baris baru |

## Skema kolom (14 kolom, A–N)

```
NO | DISTRICT | HOSTNAME | DURASI DOWN | SEVERITY | NodeB | OLO | K2 | K3 | DH | DS | HIPOTESA | STATUS | TIMESTAMP
```

Contoh baris DOWN:

```
1 | DUMAI | GPON00-D1-BGU-3BGB | 05:50 | Very Low | 0 | 0 | 0 | 0 | NON | NOK | Kabel CUT | DOWN | 20/06/2026 07:08:24
```

Aturan isi per kolom:

- **NO** — nomor urut insiden = (jumlah baris data saat ini) + offset append. Hanya
  di-set saat baris pertama kali dibuat; tidak diubah saat update/finalisasi.
- **DISTRICT** — dari pesan (`nama_distrik`).
- **HOSTNAME** — hostname GPON ter-normalisasi.
- **DURASI DOWN**
  - Baris DOWN: durasi yang dilaporkan pesan (mis. `05:50`), di-refresh tiap alert.
  - Baris UP: total outage = `waktu_up − started_at` (format `HH:MM`). `started_at`
    sudah dihitung script di `data_gpon_down_meta` (`waktu_mulai_alarm`, line 228).
    Jika `started_at` hilang (mis. setelah restart), **pertahankan** nilai durasi
    terakhir yang sudah ada di sheet — jangan ditimpa kosong.
- **SEVERITY** — teks polos dari `mapping_metadata` (`Very Low`, dst.), TANPA emoji.
  Default `Very Low` bila tidak ada di metadata.
- **NodeB** — dari pesan (field ke-4 baris GPON), default `0`.
- **OLO / K2 / K3** — dari `mapping_metadata`, default `0`, mengikuti pola `format_baris_down` yang ada.
- **DS** — dari `mapping_metadata`, default `-` (mengikuti `format_baris_down`). Contoh nilai: `OK` / `NOK`.
- **DH** — dari `mapping_metadata` (`DH` / `NON`), default `-`.
- **HIPOTESA** — dari `tentukan_hipotesa_down(hostname, durasi)` (`Kabel CUT` /
  `Baterai Habis dan OLT DOWN`). Di-refresh tiap update DOWN; dibekukan saat UP.
- **STATUS** — `DOWN` atau `UP`.
- **TIMESTAMP** — `DD/MM/YYYY HH:MM:SS` (teks), waktu penulisan/refresh.

## Mekanik tulis (hemat kuota, tahan-restart)

Sumber kebenaran = isi sheet, bukan state memori. Per event yang `ada_perubahan`:

1. **Baca sekali** tab rekap (`get_all_values`) → bangun index in-memory
   `{hostname: nomor_baris}` untuk semua baris yang `STATUS=DOWN`.
2. Kumpulkan aksi dari OLT yang berubah di pesan ini:
   - OLT DOWN (di `hostname_terupdate`) → update baris aktif jika ada di index,
     selain itu siapkan baris append baru.
   - OLT UP → jika ada baris aktif di index, siapkan finalisasi.
3. **Eksekusi batch**: satu `batch_update` untuk semua update in-place + finalisasi,
   lalu satu `append_rows` untuk semua baris baru. Total ~1 baca + 1–2 tulis per
   event, berapapun jumlah OLT dalam pesan.

Karena lookup baris aktif dilakukan dari isi sheet, restart script tidak membuat
duplikat: alert 30-menit berikutnya untuk OLT yang masih down akan menemukan
kembali baris aktifnya dan meng-update.

Kasus tepi: OLT UP tanpa baris aktif di sheet (mis. script baru mulai setelah OLT
sudah down sebelumnya) → tidak ada yang difinalisasi; lewati saja (tidak menulis
baris UP "yatim").

## Autentikasi & prasyarat

- Scope OAuth diubah dari `spreadsheets.readonly` → `spreadsheets` (read + write).
  Dipakai bersama oleh pembacaan metadata dan penulisan rekap (spreadsheet sama).
- **Prasyarat manual (sekali):** spreadsheet harus di-*share* ke email service
  account dari `kunci_rahasia_google.json` sebagai **Editor**. Tanpa ini penulisan
  gagal (tapi lihat "Ketahanan" — mirroring WA tetap jalan).
- Header row ditulis sekali bila tab masih kosong. **Tidak ada** auto-format
  (warna/freeze) — diatur manual oleh user.

## Ketahanan (tidak mengganggu fungsi utama)

- Seluruh operasi tulis ke Sheet dibungkus `try/except` dan hanya di-`simpan_log`
  bila gagal. Kegagalan Sheets **tidak** menghentikan mirroring WhatsApp maupun
  eskalasi — itu tetap fungsi utama.
- Pola pemanggilan gspread (blocking di dalam handler async) mengikuti pola yang
  sudah ada di `ambil_mapping_metadata` — tidak diubah.

## Fungsi baru (rencana, detail di plan)

- `ambil_worksheet_rekap(spreadsheet)` — handle worksheet GID `320650666`,
  pastikan header ada.
- `bangun_baris_rekap(no, info, mapping_metadata, status, timestamp, durasi_override=None)`
  — hasilkan list 14 sel.
- `indeks_insiden_aktif(semua_nilai)` — `{hostname: nomor_baris}` untuk baris `STATUS=DOWN`.
- `tulis_rekap_perubahan(worksheet, mapping_metadata, down_hostnames, up_info, waktu)`
  — orkestrasi baca → kumpulkan → batch_update + append_rows.

Hook: dipanggil di dalam blok `if ada_perubahan:` pada `proses_pesan_baru`,
me-reuse `mapping_metadata` yang sudah di-fetch dan `hostname_terupdate`.

## Di luar lingkup (YAGNI)

- Tidak ada auto-format/warna/freeze.
- Tidak ada tab HISTORY terpisah (model hybrid ditolak).
- Tidak ada reset harian untuk sheet (akumulasi).
- Tidak mengubah format/isi laporan WhatsApp yang sudah ada.
