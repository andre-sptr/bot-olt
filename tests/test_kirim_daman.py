import unittest

import kirim_daman as kd


def _blank_row():
    return [""] * 80


def _set(row, column, value):
    row[kd.IDX[column]] = value


class KirimDamanCaptionTest(unittest.TestCase):
    def test_inventory_screenshot_ranges_include_full_ytd_table(self):
        self.assertEqual(kd.PESAN[2]["range"], "B22:I29")
        self.assertEqual(kd.PESAN[3]["range"], "B32:I37")

    def test_petakan_ytd_tabel_reads_displayed_ytd_columns(self):
        rows = [
            ["BATAM", "67.21%", "75.68%", "88.81%", "67.21%", "95.60%", "70.30%", "2"],
            ["AREA 1", "58.60%", "75.68%", "77.44%", "58.60%", "95.60%", "61.30%", ""],
        ]

        mapped = kd._petakan_ytd_tabel(rows)

        self.assertEqual(
            mapped["BATAM"],
            {"real": "67.21%", "target": "95.60%", "ach": "70.30%", "rank": "2"},
        )
        self.assertEqual(
            mapped["AREA 1"],
            {"real": "58.60%", "target": "95.60%", "ach": "61.30%", "rank": ""},
        )

    def test_inventory_district_caption_includes_ytd_values(self):
        latest_total = _blank_row()
        latest_batam = _blank_row()
        previous_total = _blank_row()
        previous_batam = _blank_row()
        _set(latest_total, "AJ", "58.75%")
        _set(previous_total, "AJ", "57.00%")
        _set(latest_batam, "AJ", "67.21%")
        _set(previous_batam, "AJ", "66.00%")

        data = {
            "vals": [latest_total, latest_batam, previous_total, previous_batam],
            "rows_terbaru": {"TOTAL": 1, "BATAM": 2},
            "rows_sebelum": {"TOTAL": 3, "BATAM": 4},
            "tanggal": "24 Juni 2026",
            "target_ytd": {
                "district": {
                    "SUMBAGTENG": {"real": "58.75%", "target": "95.60%", "ach": "61.45%", "rank": ""},
                    "BATAM": {"real": "67.21%", "target": "95.60%", "ach": "70.30%", "rank": "2"},
                }
            },
        }

        caption = kd.buat_caption(kd.PESAN[2], data)

        self.assertIn("*YTD* : 58.75% | Target 95.60% | Ach 61.45%", caption)
        self.assertIn("YTD : 67.21% | Target 95.60% | Ach 70.30%", caption)

    def test_inventory_region_caption_includes_ytd_values(self):
        latest_area = _blank_row()
        latest_sumbagteng = _blank_row()
        previous_area = _blank_row()
        previous_sumbagteng = _blank_row()
        _set(latest_area, "BV", "58.60%")
        _set(previous_area, "BV", "57.50%")
        _set(latest_sumbagteng, "BV", "58.75%")
        _set(previous_sumbagteng, "BV", "57.80%")

        data = {
            "vals": [latest_area, latest_sumbagteng, previous_area, previous_sumbagteng],
            "rows_terbaru": {},
            "rows_sebelum": {},
            "regions_terbaru": {"AREA1": 1, "SUMBAGTENG": 2},
            "regions_sebelum": {"AREA1": 3, "SUMBAGTENG": 4},
            "tanggal": "24 Juni 2026",
            "target_ytd": {
                "region": {
                    "AREA 1": {"real": "58.60%", "target": "95.60%", "ach": "61.30%", "rank": ""},
                    "SUMBAGTENG": {"real": "58.75%", "target": "95.60%", "ach": "61.45%", "rank": "2"},
                }
            },
        }

        caption = kd.buat_caption(kd.PESAN[3], data)

        self.assertIn("*YTD* : 58.60% | Target 95.60% | Ach 61.30%", caption)
        self.assertIn("YTD : 58.75% | Target 95.60% | Ach 61.45%", caption)


if __name__ == "__main__":
    unittest.main()
