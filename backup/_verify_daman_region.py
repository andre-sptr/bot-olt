# Dry-run: verifikasi tabel REGION baru + RANK, TANPA menulis sheet / kirim WA.
import gspread
import kirim_daman as kd

creds = kd.buat_creds()
ss = gspread.authorize(creds).open_by_key(kd.SPREADSHEET_ID)
data = kd.baca_dashboard(ss)

print("Tanggal blok terbaru:", data["tanggal"])
print("regions_terbaru:", data["regions_terbaru"])
print("regions_sebelum:", data["regions_sebelum"])
vals = data["vals"]

print("\n" + "=" * 60)
print("PAYLOAD yang AKAN ditulis ke TABEL BOT (dry-run, tidak ditulis):")
print("=" * 60)

rows = data["rows_terbaru"]
r_total = rows.get("TOTAL")
payload = []
for tabel in kd.TABEL_TULIS:
    nilai = []
    for d in kd.DISTRICTS:
        r = rows[d]
        nilai.append([kd._cell(vals, r, kd.IDX[k]) for k in tabel["kolom"]])
    nilai.append([kd._cell(vals, r_total, kd.IDX[k]) if r_total else "" for k in tabel["kolom"]])
    payload.append({"range": tabel["range"], "values": nilai})

regs = data["regions_terbaru"]
nilai_region = []
for rg in kd.REGION_ORDER:
    r = regs.get(rg)
    nilai_region.append([kd._cell(vals, r, kd.IDX[k]) if r else "" for k in kd.TABEL_REGION["kolom"]])
payload.append({"range": kd.TABEL_REGION["range"], "values": nilai_region})

labels = ["VALINS SERVICE", "VALIDASI INFRA FTTH", "VALIDASI DATA INV (DISTRICT)", "VALIDASI DATA INV (REGION)"]
rowlabels = [kd.DISTRICTS + ["SUMBAGTENG"], kd.DISTRICTS + ["SUMBAGTENG"],
             kd.DISTRICTS + ["SUMBAGTENG"], kd.REGION_ORDER]
for lbl, p, rl in zip(labels, payload, rowlabels):
    print(f"\n--- {lbl}  range={p['range']} ---")
    for name, vrow in zip(rl, p["values"]):
        print(f"   {name:<12} {vrow}")

print("\n" + "=" * 60)
print("CAPTIONS (4 bubble):")
print("=" * 60)
for i, spec in enumerate(kd.PESAN, start=1):
    print(f"\n########## BUBBLE {i} :: judul={spec['judul']} :: range={spec['range']} ##########")
    print(kd.buat_caption(spec, data))
