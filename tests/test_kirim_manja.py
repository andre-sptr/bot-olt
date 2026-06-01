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
