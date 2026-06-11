# OLT Down Escalation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send a short, separate WhatsApp escalation message on every GPON update while at least one active Mini OLT has been down for more than one hour.

**Architecture:** Keep the existing full OLT report unchanged. Add pure helpers to normalize phone numbers and districts, parse down durations, select active incidents over 60 minutes, and build one compact escalation message plus its WAHA `mentions` array. Extend the existing WA sender with an optional `mentions` argument, then send the escalation immediately after the normal report whenever eligible incidents exist.

**Tech Stack:** Python, Telethon, requests, WAHA `/api/sendText`, unittest/pytest.

---

### Task 1: Duration and Recipient Selection

**Files:**
- Modify: `tests/test_mirror_isp.py`
- Modify: `mirror_isp.py`

- [x] **Step 1: Write failing tests for the one-hour boundary**

Add tests proving:

```python
self.assertEqual(mi.durasi_ke_menit("01:00"), 60)
self.assertEqual(mi.durasi_ke_menit("01:01"), 61)
self.assertEqual(mi.durasi_ke_menit("8 Jam 30 Menit"), 510)
self.assertIsNone(mi.durasi_ke_menit("-"))
```

Also populate `data_gpon_down` with durations `01:00` and `01:01`, then assert only the `01:01` record is returned by `ambil_olt_down_lebih_satu_jam()`.

- [x] **Step 2: Run tests and verify RED**

Run:

```powershell
rtk .\.venv\Scripts\python.exe -m pytest tests/test_mirror_isp.py -q
```

Expected: failure because the duration and incident-selection helpers do not exist.

- [x] **Step 3: Implement minimal duration and district helpers**

In `mirror_isp.py`, add `normalisasi_distrik(distrik)`,
`durasi_ke_menit(durasi)`, and
`ambil_olt_down_lebih_satu_jam(data_down=None)`. The parser uses a full-match
regular expression for `HH:MM[:SS]`, separate case-insensitive expressions for
Indonesian `Jam` and `Menit`, and returns `None` for invalid input. The selector
splits each stored row on `|`, pads missing fields, and returns dictionaries
containing `district`, `hostname`, `duration`, and `minutes` only when the
parsed duration is strictly greater than 60.

- [x] **Step 4: Run tests and verify GREEN**

Run the focused test file and confirm all duration-selection tests pass.

### Task 2: Compact Escalation Message and WAHA Mentions

**Files:**
- Modify: `tests/test_mirror_isp.py`
- Modify: `mirror_isp.py`

- [x] **Step 1: Write failing tests for message and recipient behavior**

Configure test recipients:

```python
manager = ["628111111111", "628222222222"]
officer = {
    "DUMAI": ["628333333333"],
    "PADANG": ["628444444444"],
}
```

Assert the generated escalation:

```text
🚨 *ESKALASI OLT DOWN > 1 JAM*
🔴 DUMAI | GPON00-D1-BGU-3SPK | 08:30

@628111111111 @628222222222
PIC DUMAI: @628333333333

*SEGERA CONCALL & UPDATE PROGRES PENANGANAN.*
```

For multiple districts, assert each eligible incident appears once, each affected district gets one `PIC <DISTRICT>:` line, unaffected district officers are absent, and duplicate numbers appear only once in the WAHA `mentions` array.

- [x] **Step 2: Run tests and verify RED**

Expected: failure because recipient configuration, normalization, and escalation builder do not exist.

- [x] **Step 3: Add editable recipient configuration**

Add four manager placeholders and per-district officer arrays:

```python
RAW_MANAGER_WA = ["", "", "", ""]

RAW_OFFICER_DISTRIK = {
    "BATAM": [],
    "PEKANBARU": [],
    "DUMAI": [],
    "BUKITTINGGI": [],
    "PADANG": [],
}
```

Normalize configured values to the Indonesian `62` prefix, ignore blanks, and
deduplicate while preserving order.

- [x] **Step 4: Implement compact escalation builder**

Add the pure function
`buat_pesan_eskalasi(daftar_down=None, manager_numbers=None,
officer_by_district=None)`. It builds one red incident line per eligible OLT,
adds one manager line, adds one `PIC <DISTRICT>:` line per affected district,
and deduplicates the final WAHA mention IDs while preserving manager-first
order. Return `(None, [])` when no incident is over 60 minutes; otherwise
return the compact message and mention IDs formatted as `<number>@c.us`.

- [x] **Step 5: Run tests and verify GREEN**

Run the focused test file and confirm message text, district filtering, blank handling, and deduplication pass.

### Task 3: Send Alarm Separately on Every Eligible Update

**Files:**
- Modify: `tests/test_mirror_isp.py`
- Modify: `mirror_isp.py`

- [x] **Step 1: Write failing WAHA payload test**

Patch `requests.post`, call:

```python
mi.kirim_pesan_wa("alarm", ["628111111111@c.us"])
```

Assert every target group receives:

```python
{
    "session": mi.WAHA_SESSION,
    "chatId": target_group,
    "text": "alarm",
    "mentions": ["628111111111@c.us"],
}
```

Also assert the existing call without mentions omits the `mentions` key.

- [x] **Step 2: Run payload tests and verify RED**

Expected: failure because `kirim_pesan_wa` does not accept a mention list.

- [x] **Step 3: Extend the WAHA sender**

Change the signature to:

```python
def kirim_pesan_wa(teks, mentions=None):
```

Only add `payload["mentions"]` when the normalized list is non-empty.

- [x] **Step 4: Add escalation to the update flow**

After the existing normal report send:

```python
teks_eskalasi, mentions = buat_pesan_eskalasi()
if teks_eskalasi:
    kirim_pesan_wa(teks_eskalasi, mentions)
```

This intentionally has no anti-spam state: every Telegram message that changes GPON data sends another escalation while any active incident remains above one hour.

- [x] **Step 5: Run focused and full verification**

Run:

```powershell
rtk .\.venv\Scripts\python.exe -m pytest tests/test_mirror_isp.py -q
rtk .\.venv\Scripts\python.exe -m pytest -q
rtk .\.venv\Scripts\python.exe -m py_compile mirror_isp.py
```

Expected: all tests pass and compilation exits with code 0.

- [x] **Step 6: Review final diff**

Confirm the existing full report format is unchanged, only eligible down records appear in the short alarm, manager/officer placeholders are easy to edit, and unrelated files are untouched.
