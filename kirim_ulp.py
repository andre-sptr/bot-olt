# -*- coding: utf-8 -*-
"""
kirim_ulp.py
============
Bot penerima Laporan Kehandalan Harian per ULP.

ALUR:
  1. User mengirim CHAT PRIBADI ke bot WhatsApp (session WAHA "OLTReport")
     berisi laporan harian dengan format standar (lihat CONTOH_LAPORAN di bawah).
  2. WAHA meneruskan pesan ke endpoint webhook /webhook (event "message").
  3. Script mem-parse teks laporan -> baris-baris ternormalisasi.
  4. Baris ditulis ke sheet INPUT (gid=0) pada spreadsheet REKAP PEMELIHARAAN
     HARIAN PER ULP, di-append AMAN setelah baris data terakhir (anchor kolom A/NO).
  5. Bot membalas ke pengirim: ringkasan jumlah baris yang ditulis + daftar baris
     yang TIDAK dikenali (tidak ditebak, supaya data produksi tidak rusak).

GROUNDING (sudah diverifikasi via kunci_rahasia_google.json, service account
bot-olt@bot-olt.iam.gserviceaccount.com sebagai editor):
  Sheet INPUT (gid=0) kolom:
    A=NO  B=TANGGAL(serial date)  C=ULP  D=PENYULANG  E=ZONA  F=KELOMPOK
    G=JENIS PEKERJAAN  H=VOLUME(number)  I=STN  J=PELAKSANA  K=KET
    L=HARI  M=BULAN  N=TAHUN
  - Locale in_ID, TZ Asia/Jakarta.
  - Data riil berakhir di baris ber-NO terakhir; baris di bawahnya hanya
    placeholder L/M/N. Append di-anchor ke kolom A.

CATATAN PENTING:
  - Tabel ATURAN_JENIS di bawah adalah PEMETAAN teks-bebas -> kosakata terkontrol
    kolom G. Ini titik paling rawan; silakan tambah/ubah sesuai istilah lapangan.
  - Baris tanpa angka volume di-SKIP (dianggap baris template kosong).
  - Baris ber-angka tapi tak cocok aturan TIDAK ditulis, dilaporkan balik.
  - Bagian *Gangguan/Trip* TIDAK ditulis (sheet ini khusus PEMELIHARAAN).

JALANKAN:
  Uji parser offline (tanpa menyentuh spreadsheet/WA):
      python kirim_ulp.py --test
  Uji 1 laporan dari file teks, lalu TULIS ke sheet:
      python kirim_ulp.py --kirim laporan.txt
  Jalankan server webhook:
      python kirim_ulp.py            (atau: uvicorn kirim_ulp:app --port 8010)
"""

import os
import re
import sys
import threading
import unicodedata
from datetime import date, datetime

# Kunci global: jamin penulisan ke sheet berurutan walau beberapa bubble laporan
# datang hampir bersamaan (mencegah dua request meng-append ke baris yang sama).
_LOCK_TULIS = threading.Lock()

try:
    import gspread
except ModuleNotFoundError:
    gspread = None

try:
    import requests
    try:
        from urllib3.exceptions import InsecureRequestWarning
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    except Exception:
        pass
except ModuleNotFoundError:
    requests = None

try:
    from oauth2client.service_account import ServiceAccountCredentials
except ModuleNotFoundError:
    ServiceAccountCredentials = None


# ====================== KONFIGURASI ======================
SPREADSHEET_ID = "17bLyqige_iyjpDJfFnnmKw4Qfb0E4_OhkzNbaLZo9Ng"
GID_SHEET = 0
FILE_KREDENSIAL = "kunci_rahasia_google.json"

# WAHA (untuk membalas pengirim). Samakan dgn skrip lain di workspace ini.
WAHA_URL = "https://waha-256b9f.app2.flaz.my.id"
WAHA_SESSION = "azam"
WAHA_API_KEY = "57d5a79dae7422022773b3ced1f6c507"

FOLDER_LOG = "logs"

# WAHA memakai sertifikat SSL self-signed -> lewati verifikasi SSL utk panggilan
# ke WAHA. Set False kalau WAHA sudah pakai cert valid.
WAHA_VERIFY_SSL = False

# Kolom sheet INPUT (huruf -> indeks 0-based dipakai saat baca).
KOL = {
    "no": "A", "tanggal": "B", "ulp": "C", "penyulang": "D", "zona": "E",
    "kelompok": "F", "jenis": "G", "volume": "H", "stn": "I",
    "pelaksana": "J", "ket": "K", "hari": "L", "bulan": "M", "tahun": "N",
}
TOTAL_KOLOM = 14  # A..N

# Format tampilan tanggal sesuai baris existing ("Kamis, 29 Januari 2026").
FORMAT_TANGGAL = "dddd, d mmmm yyyy"
EPOCH_SERIAL = date(1899, 12, 30)  # epoch serial Google Sheets / Excel
# =========================================================


# ---------------------- Util tanggal ----------------------
BULAN_ID = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11,
    "desember": 12,
}
HARI_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN_ID_NAMA = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
                 "Juli", "Agustus", "September", "Oktober", "November", "Desember"]


def serial_tanggal(d):
    return (d - EPOCH_SERIAL).days


def teks_tanggal(d):
    return f"{HARI_ID[d.weekday()]}, {d.day} {BULAN_ID_NAMA[d.month]} {d.year}"


# ---------------------- Normalisasi teks ----------------------
def bersih(s):
    """Hilangkan zero-width / NBSP / bullet aneh, rapikan spasi."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    for ch in ["‎", "‏", "‪", "‬", "⁠", "﻿"]:
        s = s.replace(ch, "")
    s = s.replace(" ", " ").replace(" ", " ")
    s = s.replace("⁣", "").replace("⁢", "")
    return s


def norm(s):
    return bersih(s).strip().lower()


# ---------------------- Logging ----------------------
def catat_log(pesan):
    waktu = datetime.now().strftime("%H:%M:%S")
    baris = f"[{waktu}] {pesan}"
    print(baris)
    try:
        os.makedirs(FOLDER_LOG, exist_ok=True)
        path = os.path.join(FOLDER_LOG, "ulp_log.txt")
        tgl = datetime.now().strftime("%Y-%m-%d")
        mode = "a"
        if os.path.exists(path):
            mtgl = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d")
            if mtgl != tgl:
                mode = "w"
        with open(path, mode, encoding="utf-8") as f:
            if mode == "w":
                f.write(f"=== Log Hari Ini: {tgl} ===\n")
            f.write(baris + "\n")
    except Exception:
        pass


# ====================== KAMUS PEMETAAN ======================
# 1) ULP: teks "Unit :" pada laporan -> nilai kolom C (mengikuti gaya data
#    existing yang dominan = HURUF KAPITAL dgn underscore).
ULP_ALIAS = [
    (("rumbai",), "RUMBAI"),
    (("kerinci",), "KERINCI"),            # "Pangkalan Kerinci"
    (("kotim",), "KOTA_TIMUR"),
    (("kota timur",), "KOTA_TIMUR"),
    (("kota barat",), "KOTA_BARAT"),
    (("kotbar",), "KOTA_BARAT"),
    (("simpang",), "SIMPANG_TIGA"),
    (("perawang",), "PERAWANG"),
    (("panam",), "PANAM"),
    (("siak",), "SIAK"),
]

# 2) PELAKSANA: kolom J -> kategori (PLN ES / P0 YANDAL / PDKB / VENDOR).
def tebak_pelaksana(teks, section_default):
    t = norm(teks)
    if not t:
        return section_default
    if "pdkb" in t:
        return "PDKB"
    if "yandal" in t or "yantek" in t or "posko" in t:
        return "P0 YANDAL"
    if "pln es" in t or re.search(r"\bes\b", t) or "pln" in t:
        return "PLN ES"
    # kontraktor pihak ketiga (PT ITA, PT GMTR, dll)
    if re.search(r"\bpt\b", t) or "vendor" in t:
        return "VENDOR"
    return section_default


# 3) SATUAN: token unit pada laporan -> nilai kolom I (kosakata: kms, titik,
#    gardu, btg, gwg, bh).
SATUAN_ALIAS = {
    "kms": "kms", "km": "kms",
    "btg": "btg", "batang": "btg", "btng": "btg",
    "titik": "titik", "ttk": "titik", "tiik": "titik", "tik": "titik", "ttik": "titik",
    "gardu": "gardu", "unit": "gardu", "grd": "gardu",
    "gwg": "gwg", "gawang": "gwg",
    "bh": "bh", "buah": "bh", "set": "bh", "pcs": "bh", "bj": "bh",
}

# 4) JENIS PEKERJAAN: aturan keyword -> (KELOMPOK, JENIS kanonik, STN default).
#    Dicocokkan berurutan; aturan PERTAMA yang semua keyword-nya muncul = menang.
#    'keys' = tuple grup keyword; tiap elemen string ATAU tuple(=OR).
#    KELOMPOK/STN bisa None -> ikuti konteks bagian / satuan terbaca.
ATURAN_JENIS = [
    # ---- INSPEKSI ----
    ("INSPEKSI", "Inspeksi JTM Tier 1", "kms", (("tier 1", "tier1"),)),
    ("INSPEKSI", "Inspeksi JTM Tier 2", "kms", (("tier 2", "tier2"),)),
    ("INSPEKSI", "Inspeksi Gardu", "gardu", ("inspeksi", "gardu")),
    ("INSPEKSI", "Inspeksi Gardu", "gardu",
        (("pengukuran beban", "ukur beban"), "gardu")),

    # ---- ROW / JTM vegetasi ----
    ("JTM", "Pangkas (ROW)", "kms", (("pangkas", "pemangkasan"),)),
    ("JTM", "Tebang (ROW)", "btg", (("tebang", "penebangan"),)),
    ("JTM", "Pembersihan akar rambat", "titik", (("akar rambat", "akar"),)),
    ("JTM", "Pembersihan layang-layang", "titik", (("layang",),)),

    # ---- JTM konstruksi/komponen ----
    ("JTM", "Perbaikan Tiang Miring", "btg",
        (("tiang miring", "tiang jtm miring"),)),
    ("JTM", "Resagging JTM 3 Phasa", "gwg",
        (("resagging", "seging", "sagging", "kawat kendor"),)),
    ("JTM", "Pemasangan Pin Cover", "titik",
        (("pin cover", "penghalang panjat", "pincover"),)),
    ("JTM", "Perbaikan kawat rantas (ngepral) JTM dengan press > 5 urat", "titik",
        (("kawat rantas", "rantas", "ngepral"),)),
    ("JTM", "Pembenahan Bending Wire", "titik",
        (("bending wire", "tie wired", "tie wire", "binding"),)),
    ("JTM", "Penggantian Komponen Hotspot", "titik", (("hotspot",),)),
    ("JTM", "Penggantian Arrester", "bh",
        (("penggantian la", "ganti la", "penggantian arrester", "ganti arrester",
          "penggantian arester", "ganti arester"),)),
    ("JTM", "Pemasangan Arrester", "bh",
        (("pemasangan la", "pasang la", "pemasangan arrester", "pasang arrester"),)),
    ("JTM", "Penggantian Heng Isolator", "titik",
        (("hang flash", "heng isolator", "hang isolator", "heng flash",
          "penggantian heng", "ganti heng"),)),
    ("JTM", "Penggantian Pin Isolator", "bh", (("pin isolator",),)),
    ("JTM", "Penggantian FCO", "bh", (("fco", "cut out"),)),
    ("JTM", "Reconecting JTM", "titik",
        (("reconnect jtm", "reconecting jtm", "penjamperan tm", "jamperan tm",
          "putus jamperan"),)),
    ("JTM", "Perbaikan Jumper", "titik",
        (("jamper", "jumper", "jamperan"),)),
    ("JTM", "Pemasangan Grounding", "titik",
        (("pemasangan ground", "pasang ground", "pemasangan grounding",
          "pasang grounding", "pemasangan pentanahan"),)),
    ("JTM", "Perbaikan Pentanahan / Grounding JTM", "titik",
        (("pembenahan ground", "perbaikan ground", "pembenahan grounding",
          "ground la"),)),
    ("JTM", "Perbaikan Konstruksi", "titik",
        (("penyesuaian konstruksi", "pembenahan konstruksi", "perbaikan konstruksi"),)),
    ("JTM", "Pemasangan Trekschoor/ Kontramas", "titik",
        (("trekschoor", "kontramas", "treksoor"),)),

    # ---- HAR GARDU / TRAFO ----
    ("GARDU", "HAR GARDU", "gardu", (("har gardu",),)),
    ("GARDU", "Ketidakseimbangan beban TR/Penyeimbangan Beban TR", "gardu",
        (("penyeimbangan beban", "ketidakseimbangan beban", "seimbang beban"),)),
    ("GARDU", "Pemeliharaan Grounding Gardu", "titik",
        (("grounding la", "grounding body", "grounding netral", "grounding gardu",
          "pentanahan gardu"),)),
    ("GARDU", "Pentanahan Trafo/Pasang Tambahan Pentanahan Trafo", "titik",
        (("pentanahan trafo", "grounding trafo"),)),

    # ---- JTR & SR ----
    ("JTR", "Perbaikan Tiang TR miring", "btg",
        (("tiang tumbang", "tiang tr miring", "tiang tr"),)),
    ("JTR", "Penggantian SKUTR Retas", "gwg",
        (("skutr", "skutr retas"),)),
    ("JTR", "Resagging JTR", "gwg", (("resagging jtr", "sagging jtr"),)),
    ("SR", "Reconnecting SR", "titik", (("reconnect sr", "reconnecting sr"),)),
    ("SR", "Konfigurasi SR", "titik", (("konfigurasi sr", "config sr"),)),
]

# Bagian (section) header -> (KELOMPOK default, PELAKSANA default).
# Dipakai untuk konteks; JENIS tetap ditentukan ATURAN_JENIS.
SECTION_DEFAULT = [
    (("inspeksi",), ("INSPEKSI", "")),
    (("realisasi row", "realiasi row"), ("JTM", "VENDOR")),
    (("har jtm",), ("JTM", "PLN ES")),
    (("har pdkb", "pdkb"), ("JTM", "PDKB")),
    (("har gardu", "trafo & phb", "trafo & phbtr"), ("GARDU", "PLN ES")),
    (("har jtr", "jtr & sr"), ("JTR", "PLN ES")),
    (("p0 yandal", "po yandal", "p0yandal"), ("JTM", "P0 YANDAL")),
    (("gangguan", "trip"), ("__SKIP__", "")),
]


def cocok_grup(teks_norm, grup):
    """grup = tuple keyword; tiap elemen string atau tuple(OR). Semua harus match."""
    for elem in grup:
        kandidat = elem if isinstance(elem, tuple) else (elem,)
        if not any(k in teks_norm for k in kandidat):
            return False
    return True


def deteksi_section(baris_norm):
    # Header bagian biasanya diapit '*...*' atau diawali kata kunci.
    t = baris_norm.strip("*: ").strip()
    for keys, default in SECTION_DEFAULT:
        for k in keys:
            if t.startswith(k) or t == k:
                return default
    # cek juga bila keyword muncul di awal baris tebal
    for keys, default in SECTION_DEFAULT:
        if any(baris_norm.startswith("*" + k) or ("*" + k) in baris_norm for k in keys):
            return default
    return None


# ---------------------- Ekstraksi angka & satuan ----------------------
RE_ANGKA = re.compile(r"(\d+(?:[.,]\d+)?)")
# kode gardu / titik (mis. "KT 297", "RB077", "Sa 54") -> jangan dianggap volume.
RE_KODE = re.compile(r"\b[A-Za-z]{2,3}\s?\d{2,4}\b")


def ekstrak_volume_satuan(teks, stn_default):
    """
    Kembalikan (volume_float, satuan) dari potongan nilai sebuah baris.
    - Mendukung 'X kms', 'X btg ( Y kms )', '0,4', '1.10'.
    - Bila ada beberapa pasangan, pilih yang satuannya == stn_default; jika tak
      ada, pilih pasangan pertama yang punya satuan; jika tak ada satuan sama
      sekali, pakai angka pertama + stn_default.
    Return (None, None) bila tidak ada angka -> baris di-skip.
    """
    t = bersih(teks)
    # buang kode gardu/titik supaya tidak terbaca sbg volume ("KT 297" -> "297").
    t = RE_KODE.sub(" ", t)
    # kumpulkan semua (angka, satuan_setelahnya)
    pasangan = []
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*([A-Za-z]+)?", t):
        angka_raw = m.group(1)
        unit_raw = (m.group(2) or "").lower()
        satuan = SATUAN_ALIAS.get(unit_raw, "")
        try:
            vol = float(angka_raw.replace(".", "").replace(",", ".")) \
                if angka_raw.count(",") == 1 and angka_raw.count(".") == 0 \
                else float(angka_raw.replace(",", ""))
        except ValueError:
            continue
        # heuristik desimal: "1.10"->1.1 ; "1,50"->1.5 ; "328"->328
        vol = _parse_desimal(angka_raw)
        pasangan.append((vol, satuan))

    if not pasangan:
        return None, None

    # prioritas: satuan == stn_default
    if stn_default:
        for vol, sat in pasangan:
            if sat == stn_default:
                return vol, sat
    # lalu: pasangan pertama yang punya satuan dikenal
    for vol, sat in pasangan:
        if sat:
            return vol, sat
    # terakhir: angka pertama + stn_default
    return pasangan[0][0], stn_default or ""


def _parse_desimal(s):
    s = s.strip()
    if "," in s and "." in s:
        # asumsikan '.' ribuan, ',' desimal -> buang '.', ',' jadi '.'
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


# ---------------------- Penyulang ----------------------
def normalisasi_penyulang(teks):
    """'f.salacia' / 'P kijang' / 'Bacan' -> 'P. SALACIA' style (best-effort)."""
    t = bersih(teks).strip()
    if not t:
        return ""
    # buang prefiks penyulang
    t = re.sub(r"^(p\.?\s*|f\.?\s*|penyulang\s*:?\s*)", "", t, flags=re.IGNORECASE)
    # ambil token nama utama (sebelum kata 'rc'/'rec'/'(' jika ada)
    t = re.split(r"\b(rc|rec|jur|jurusan)\b|\(", t, flags=re.IGNORECASE)[0]
    nama = t.strip().strip(".").strip()
    if not nama:
        return ""
    return "P. " + nama.upper()


# ====================== PARSER LAPORAN ======================
def parse_laporan(teks):
    """
    Return dict:
      ok: bool, alasan: str (bila tidak ok),
      ulp, tanggal(date), rows: list[list A..N tanpa NO/format], skip: list[str]
    Setiap row = dict field siap dirakit jadi baris sheet.
    """
    raw = bersih(teks)
    baris_list = [b.rstrip() for b in raw.split("\n")]

    # --- ULP ---
    ulp = ""
    for b in baris_list:
        bn = norm(b)
        if bn.startswith("unit") and ":" in b:
            isi = norm(b.split(":", 1)[1])
            for keys, val in ULP_ALIAS:
                if any(k in isi for k in keys):
                    ulp = val
                    break
            break
    if not ulp:
        return {"ok": False, "alasan": "Baris 'Unit : ULP ...' tidak ditemukan / ULP tidak dikenali."}

    # --- TANGGAL ---
    tgl = None
    for b in baris_list:
        bn = norm(b)
        if "tanggal" in bn or "hari/tanggal" in bn or re.search(r"\bhari\b", bn):
            tgl = parse_tanggal(b)
            if tgl:
                break
    if not tgl:
        # fallback: cari tanggal di mana saja
        for b in baris_list:
            tgl = parse_tanggal(b)
            if tgl:
                break
    if not tgl:
        return {"ok": False, "alasan": "Tanggal laporan tidak ditemukan / tidak bisa diparse."}

    # --- ISI per bagian ---
    rows = []
    skip = []
    kel_default, pel_default = "", ""
    penyulang_konteks = ""
    pelaksana_konteks = ""

    for b in baris_list:
        bn = norm(b)
        if not bn:
            continue

        # lewati baris pembuka/penutup/identitas laporan
        if any(k in bn for k in ("assalamu", "demikian laporan", "berikut disampaikan",
                                 "terimakasih", "terima kasih")):
            continue

        # deteksi header bagian
        sec = deteksi_section(bn)
        if sec is not None:
            kel_default, pel_default = sec
            penyulang_konteks = ""
            pelaksana_konteks = ""
            # baris header bisa juga memuat penyulang (mis "*Har JTM* f.meekurius")
            sisa = re.sub(r"\*[^*]+\*", "", b).strip(" :-")
            if sisa and re.search(r"[a-zA-Z]", sisa):
                pny = normalisasi_penyulang(sisa)
                if pny and len(pny) > 3:
                    penyulang_konteks = pny
            continue

        if kel_default == "__SKIP__":
            continue  # bagian Gangguan/Trip tidak ditulis

        isi_label, isi_nilai = pisah_label_nilai(b)

        # update konteks penyulang / pelaksana bila baris adalah meta
        lab_n = norm(isi_label)
        if "penyulang" in lab_n or "penyulang" in bn[:12]:
            penyulang_konteks = normalisasi_penyulang(isi_nilai)
            continue
        if "pelaksana" in lab_n:
            pelaksana_konteks = tebak_pelaksana(isi_nilai, pel_default)
            continue
        if lab_n in ("lokasi", "temuan", "keterangan", "ket", "tindak lanjut",
                     "no.gardu", "no gardu", "penyebab", "jenis gangguan",
                     "rincian pekerjaan", "rincian pekerjaan:",
                     "hari/tanggal", "hari / tanggal", "tanggal", "hari", "unit"):
            continue

        # lewati baris header posko (mis. "1.posko siak", "2.posko sei apit")
        if re.match(r"^\d*\s*\.?\s*posko\b", bn) or lab_n.startswith("posko"):
            continue

        # baris pekerjaan: cocokkan aturan
        hasil = cocok_aturan(bn, kel_default)
        if hasil is None:
            # laporkan bila baris punya angka volume (kandidat pekerjaan tak dikenali)
            if len(bn) > 2:
                vol_cek, _ = ekstrak_volume_satuan(isi_nilai if isi_nilai else b, None)
                if vol_cek not in (None, 0.0):
                    skip.append(b.strip())
            continue

        kelompok, jenis, stn_default = hasil
        kode_gardu = RE_KODE.findall(b)
        vol, satuan = ekstrak_volume_satuan(isi_nilai if isi_nilai else b, stn_default)
        # HAR GARDU tanpa angka eksplisit: volume = jumlah kode gardu yg disebut.
        if (vol is None or vol == 0.0) and jenis == "HAR GARDU" and kode_gardu:
            vol, satuan = float(len(kode_gardu)), "gardu"
        if vol is None or vol == 0.0:
            continue  # baris template kosong / tanpa volume -> skip diam2

        pelaksana = pelaksana_konteks or pel_default
        ket = ", ".join(k.strip() for k in kode_gardu) if kode_gardu else ekstrak_ket(b)
        rows.append({
            "ulp": ulp,
            "penyulang": penyulang_konteks,
            "zona": "",
            "kelompok": kelompok,
            "jenis": jenis,
            "volume": vol,
            "stn": satuan or stn_default or "",
            "pelaksana": pelaksana,
            "ket": ket,
        })

    return {"ok": True, "ulp": ulp, "tanggal": tgl, "rows": rows, "skip": skip}


def cocok_aturan(baris_norm, kel_konteks):
    for kelompok, jenis, stn, grup in ATURAN_JENIS:
        if cocok_grup(baris_norm, grup):
            return (kelompok or kel_konteks), jenis, stn
    # fallback konteks INSPEKSI: "Gardu : N gardu" -> Inspeksi Gardu
    if kel_konteks == "INSPEKSI" and "gardu" in baris_norm and "har" not in baris_norm:
        return "INSPEKSI", "Inspeksi Gardu", "gardu"
    return None


def pisah_label_nilai(baris):
    b = bersih(baris).strip()
    b = re.sub(r"^[\-\*•⁃‐‑\s\.]+", "", b)  # buang bullet
    b = re.sub(r"^\d+\.\s*", "", b)  # buang penomoran "1."
    if ":" in b:
        lab, nilai = b.split(":", 1)
        return lab.strip(), nilai.strip()
    return b.strip(), ""


def ekstrak_ket(baris):
    """Ambil kode gardu / catatan singkat untuk kolom K (best-effort)."""
    b = bersih(baris)
    m = re.search(r"\b([A-Z]{2}\s?\d{2,4})\b", b)  # mis 'KT 297', 'RB077'
    if m:
        return m.group(1)
    return ""


def parse_tanggal(baris):
    t = bersih(baris)
    # format "dd <bulan_id> yyyy"
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", t)
    if m:
        d = int(m.group(1)); bln = BULAN_ID.get(m.group(2).lower()); y = int(m.group(3))
        if bln:
            try:
                return date(y, bln, d)
            except ValueError:
                return None
    # format dd/mm/yyyy atau dd-mm-yyyy
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", t)
    if m:
        d = int(m.group(1)); bln = int(m.group(2)); y = int(m.group(3))
        try:
            return date(y, bln, d)
        except ValueError:
            return None
    return None


# ====================== PENULISAN KE SHEET ======================
def buka_worksheet():
    if gspread is None or ServiceAccountCredentials is None:
        raise RuntimeError("Dependency gspread/oauth2client belum terpasang.")
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(FILE_KREDENSIAL, scope)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    return sh.get_worksheet_by_id(GID_SHEET)


def tulis_ke_sheet(hasil, dry_run=False):
    """Append baris hasil parse ke sheet INPUT secara AMAN (anchor kolom A/NO).
    dry_run=True: hitung & cetak rencana tulis tanpa mengubah spreadsheet."""
    ws = buka_worksheet()
    kol_a = ws.col_values(1)  # NO

    # baris terakhir yang punya NO numerik = batas data riil.
    last_row = 2
    last_no = 0
    for i, v in enumerate(kol_a, start=1):
        if str(v).strip().isdigit():
            last_row = i
            last_no = int(v)

    start_row = last_row + 1
    tgl = hasil["tanggal"]
    serial = serial_tanggal(tgl)

    matriks = []
    no = last_no
    for r in hasil["rows"]:
        no += 1
        matriks.append([
            no,                       # A NO
            serial,                   # B TANGGAL (serial -> diformat tanggal)
            r["ulp"],                 # C
            r["penyulang"],           # D
            r["zona"],                # E
            r["kelompok"],            # F
            r["jenis"],               # G
            r["volume"],              # H (number)
            r["stn"],                 # I
            r["pelaksana"],           # J
            r["ket"],                 # K
            tgl.day,                  # L HARI
            tgl.month,                # M BULAN
            tgl.year,                 # N TAHUN
        ])

    if not matriks:
        return 0, start_row

    end_row = start_row + len(matriks) - 1
    rng = f"A{start_row}:N{end_row}"

    if dry_run:
        print(f"[DRY-RUN] last NO={last_no} di baris {last_row}; "
              f"akan menulis {len(matriks)} baris ke {rng} (TANPA mengubah sheet):")
        for row in matriks:
            print("   ", row)
        return len(matriks), start_row

    ws.update(range_name=rng, values=matriks, value_input_option="USER_ENTERED")
    # samakan format tanggal kolom B agar tampil "Hari, d Bulan yyyy"
    try:
        ws.format(f"B{start_row}:B{end_row}",
                  {"numberFormat": {"type": "DATE", "pattern": FORMAT_TANGGAL}})
    except Exception as e:
        catat_log(f"Peringatan: gagal set format tanggal: {e}")

    return len(matriks), start_row


# ====================== BALAS WHATSAPP ======================
def kirim_balasan(chat_id, teks):
    if requests is None:
        catat_log("requests tidak tersedia, balasan dilewati.")
        return
    url = f"{WAHA_URL.rstrip('/')}/api/sendText"
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "X-Api-Key": WAHA_API_KEY, "Connection": "close"}
    payload = {"session": WAHA_SESSION, "chatId": chat_id, "text": teks}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30,
                             verify=WAHA_VERIFY_SSL)
        if resp.status_code not in (200, 201):
            catat_log(f"Gagal kirim balasan {chat_id}: {resp.status_code} {resp.text[:200]}")
        else:
            catat_log(f"↩️ Balasan terkirim ke {chat_id}")
    except Exception as e:
        catat_log(f"Error kirim balasan: {e}")


def ringkasan_teks(hasil, jumlah, start_row):
    ulp = hasil["ulp"]; tgl = teks_tanggal(hasil["tanggal"])
    baris = [
        "✅ *Laporan ULP diterima*",
        f"Unit   : {ulp}",
        f"Tanggal: {tgl}",
        f"Tertulis: *{jumlah}* baris (mulai baris {start_row}).",
    ]
    if hasil.get("skip"):
        baris.append("")
        baris.append(f"⚠️ *{len(hasil['skip'])} baris belum dikenali* (tidak ditulis, cek manual):")
        for s in hasil["skip"][:15]:
            baris.append(f"- {s}")
        if len(hasil["skip"]) > 15:
            baris.append(f"...(+{len(hasil['skip']) - 15} lagi)")
    return "\n".join(baris)


def proses_laporan_masuk(teks, chat_id=None, tulis=True):
    hasil = parse_laporan(teks)
    if not hasil.get("ok"):
        catat_log(f"Parse gagal: {hasil.get('alasan')}")
        if chat_id:
            kirim_balasan(chat_id, f"❌ Gagal memproses laporan: {hasil.get('alasan')}")
        return hasil

    jumlah, start_row = (0, 0)
    if tulis:
        try:
            with _LOCK_TULIS:
                jumlah, start_row = tulis_ke_sheet(hasil)
        except Exception as e:
            catat_log(f"Gagal menulis ke sheet: {e}")
            if chat_id:
                kirim_balasan(chat_id, f"❌ Gagal menulis ke spreadsheet: {e}")
            return {"ok": False, "alasan": str(e)}

    catat_log(f"ULP {hasil['ulp']} | {hasil['tanggal']} | {jumlah} baris ditulis "
              f"| {len(hasil['skip'])} skip")
    if chat_id:
        kirim_balasan(chat_id, ringkasan_teks(hasil, jumlah, start_row))
    hasil["jumlah"] = jumlah
    hasil["start_row"] = start_row
    return hasil


# ====================== WEBHOOK (WAHA) ======================
try:
    from fastapi import FastAPI, Request
    app = FastAPI()

    @app.get("/")
    async def root():
        return {"status": "ok", "service": "kirim_ulp"}

    @app.get("/webhook")
    async def webhook_get():
        # beberapa sistem melakukan GET utk verifikasi endpoint.
        return {"status": "ok", "hint": "kirim POST event message ke sini"}

    @app.post("/webhook")
    async def webhook(request: Request):
        try:
            data = await request.json()
        except Exception:
            body = (await request.body())[:200]
            catat_log(f"⚠️ Webhook: body bukan JSON: {body!r}")
            return {"status": "ignored", "reason": "body bukan JSON"}

        event = data.get("event") or data.get("type") or ""
        payload = data.get("payload") or data.get("data") or {}
        if not isinstance(payload, dict):
            payload = {}

        chat_id = (payload.get("from") or payload.get("chatId")
                   or payload.get("chat_id") or "")
        from_me = bool(payload.get("fromMe") or payload.get("from_me"))
        teks = (payload.get("body") or payload.get("text")
                or payload.get("caption") or "")

        # CATAT semua yg masuk supaya bisa didiagnosis.
        catat_log(f"📥 Webhook event={event!r} from={chat_id!r} fromMe={from_me} "
                  f"len={len(teks)} keys={list(payload.keys())}")

        # terima berbagai nama event yg mengandung 'message'
        if event and "message" not in str(event).lower():
            return {"status": "ignored", "reason": f"event {event}"}
        if from_me:
            return {"status": "ignored", "reason": "pesan dari diri sendiri"}
        if not teks.strip():
            return {"status": "ignored", "reason": "pesan tanpa teks"}

        # chat pribadi diutamakan; kalau bukan @c.us tetap diproses bila format laporan cocok.
        is_private = str(chat_id).endswith("@c.us")
        cocok_format = "laporan kehandalan harian" in norm(teks)
        if not cocok_format:
            catat_log(f"   ↳ diabaikan: bukan format laporan. cuplikan={norm(teks)[:60]!r}")
            return {"status": "ignored", "reason": "bukan format laporan ULP"}
        if not is_private:
            catat_log(f"   ↳ catatan: chat bukan @c.us ({chat_id}), tetap diproses.")

        catat_log(f"📩 Laporan ULP masuk dari {chat_id} ({len(teks)} char)")
        try:
            proses_laporan_masuk(teks, chat_id=chat_id or None, tulis=True)
        except Exception as e:
            catat_log(f"❌ Error proses laporan: {e}")
            return {"status": "error", "reason": str(e)}
        return {"status": "ok"}
except ModuleNotFoundError:
    app = None


# ====================== CONTOH & UJI OFFLINE ======================
CONTOH_LAPORAN = r"""Assalamualaikum Wr Wb, Berikut disampaikan Laporan kehandalan Harian Inspeksi, Pemeliharaan, dan gangguan
Hari/Tanggal : Selasa / 31 Maret 2026
Unit : ULP Rumbai

*Inspeksi*
  - Tier 1 : 5 kms
  - Tier 2 : kms
  - Gardu : 4 gardu

*Realisasi ROW*
- Pelaksana : PT ITA 02
- Penyulang : P kijang rec barito
- Pangkas : 1.10 kms
- Tebang : 2 Btg

*Har PDKB*
  - Penggantian Hang flash :  1 titik
  - Lokasi : Jl. Siak 2

*P0 Yandal 6*
- Pangkas : titik
- penyeimbangan beban : gardu
- Lokasi :
"""


def _uji_offline():
    hasil = parse_laporan(CONTOH_LAPORAN)
    if not hasil["ok"]:
        print("PARSE GAGAL:", hasil["alasan"]); return
    print(f"ULP     : {hasil['ulp']}")
    print(f"TANGGAL : {hasil['tanggal']}  -> serial {serial_tanggal(hasil['tanggal'])} "
          f"| L={hasil['tanggal'].day} M={hasil['tanggal'].month} N={hasil['tanggal'].year}")
    print(f"BARIS   : {len(hasil['rows'])}")
    print("-" * 90)
    print(f"{'C ULP':10} {'D PENY':14} {'F KEL':10} {'G JENIS':38} {'H':>6} {'I':6} {'J PEL':9}")
    for r in hasil["rows"]:
        print(f"{r['ulp']:10} {r['penyulang']:14} {r['kelompok']:10} "
              f"{r['jenis'][:38]:38} {r['volume']:>6} {r['stn']:6} {r['pelaksana']:9}")
    if hasil["skip"]:
        print("-" * 90)
        print("TIDAK DIKENALI (tidak ditulis):")
        for s in hasil["skip"]:
            print("  -", s)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _uji_offline()
    elif "--kirim" in sys.argv:
        idx = sys.argv.index("--kirim")
        path = sys.argv[idx + 1]
        with open(path, encoding="utf-8") as f:
            teks = f.read()
        proses_laporan_masuk(teks, chat_id=None, tulis=True)
    elif "--dry" in sys.argv:
        idx = sys.argv.index("--dry")
        path = sys.argv[idx + 1]
        with open(path, encoding="utf-8") as f:
            teks = f.read()
        hasil = parse_laporan(teks)
        if not hasil["ok"]:
            print("PARSE GAGAL:", hasil["alasan"]); sys.exit(1)
        tulis_ke_sheet(hasil, dry_run=True)
    else:
        if app is None:
            print("FastAPI tidak terpasang. Pakai: python kirim_ulp.py --test")
            sys.exit(1)
        import uvicorn
        print("=" * 55)
        print("  kirim_ulp -> webhook WAHA (chat pribadi -> sheet INPUT)")
        print(f"  Spreadsheet: {SPREADSHEET_ID} (gid={GID_SHEET})")
        print("  Endpoint   : POST /webhook")
        print("=" * 55)
        uvicorn.run(app, host="0.0.0.0", port=8010)
