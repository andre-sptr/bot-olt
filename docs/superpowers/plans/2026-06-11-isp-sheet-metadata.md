# ISP Sheet Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read severity, OLO, K2, and K3 by hostname from the new Google Sheet and render the requested OLT-down report columns.

**Architecture:** Replace the severity-only mapping with one metadata dictionary per normalized hostname. Read `E3:O` once, map fixed range-relative indices, and let the report formatter apply `-` fallbacks without changing Telegram state or escalation logic.

**Tech Stack:** Python, gspread, oauth2client, unittest/pytest.

---

### Task 1: Define the New Sheet Metadata Contract

**Files:**
- Modify: `tests/test_mirror_isp.py`
- Modify: `mirror_isp.py`

- [x] **Step 1: Write failing tests**

Add a row with 11 range-relative values and assert:

```python
mapping["GPON00-D1-AMK-2UKUI"] == {
    "severity": "Critical",
    "olo": "TSEL",
    "k2": "2",
    "k3": "3",
}
```

Mock the Google client chain and assert the spreadsheet ID, GID
`1706912635`, and range `E3:O` are used.

- [x] **Step 2: Run focused tests and verify RED**

Run `rtk .\.venv\Scripts\python.exe -m pytest tests/test_mirror_isp.py -q`.
Expected: failures because metadata mapping and the new source contract are not
implemented.

- [x] **Step 3: Implement the metadata reader**

Set the new spreadsheet ID and GID. Add `buat_mapping_metadata(semua_nilai)`
using indices 0, 7, 8, 9, and 10, and add `ambil_mapping_metadata()` that calls
`worksheet.get("E3:O")`.

- [x] **Step 4: Run focused tests and verify GREEN**

Run the focused test file and confirm the source and mapping tests pass.

### Task 2: Render the New Report Format

**Files:**
- Modify: `tests/test_mirror_isp.py`
- Modify: `mirror_isp.py`

- [x] **Step 1: Write failing formatter tests**

Assert the exact header:

```text
NO | DISTRICT | HOSTNAME | DURASI DOWN | SEVERITY | NodeB | OLO | K2 | K3 | IdPLN
```

Assert a complete row places severity before NodeB and metadata before IdPLN.
Assert missing metadata and sheet failures produce `-` in all four
sheet-derived fields.

- [x] **Step 2: Run focused tests and verify RED**

Run the focused test file. Expected: failures showing the old severity-only
header and row order.

- [x] **Step 3: Update formatting and fallback behavior**

Change `format_baris_down` and `buat_laporan_list` to consume metadata
dictionaries. Preserve the existing severity emoji mapping and use `-` for
missing OLO, K2, K3, or invalid severity.

- [x] **Step 4: Verify all behavior**

Run:

```powershell
rtk .\.venv\Scripts\python.exe -m pytest tests/test_mirror_isp.py -q
rtk .\.venv\Scripts\python.exe -m pytest -q
rtk .\.venv\Scripts\python.exe -m py_compile mirror_isp.py
rtk git diff --check
```

Expected: all tests pass, compilation succeeds, and the diff check is clean.
