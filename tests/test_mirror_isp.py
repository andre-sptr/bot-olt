from unittest import TestCase, mock

import mirror_isp as mi


class MirrorISPTests(TestCase):
    def setUp(self):
        self.data_down_lama = mi.data_gpon_down.copy()
        self.data_up_lama = mi.data_gpon_up.copy()
        mi.data_gpon_down.clear()
        mi.data_gpon_up.clear()

    def tearDown(self):
        mi.data_gpon_down.clear()
        mi.data_gpon_down.update(self.data_down_lama)
        mi.data_gpon_up.clear()
        mi.data_gpon_up.update(self.data_up_lama)

    def test_buat_mapping_severity_normalizes_hostname_and_values(self):
        values = [
            ["HOSTNAME", "SEVERITY"],
            [" gpon00-d1-amk-2ukui ", "critical"],
            ["GPON00-D1-ARK-3SGA", "Minor"],
            ["", "Major"],
            ["GPON-TIDAK-VALID", "Unknown"],
        ]

        mapping = mi.buat_mapping_severity(values)

        self.assertEqual(
            mapping,
            {
                "GPON00-D1-AMK-2UKUI": "Critical",
                "GPON00-D1-ARK-3SGA": "Minor",
            },
        )

    def test_format_baris_down_inserts_colored_severity_before_idpln(self):
        info = (
            "DUMAI | GPON00-D1-AMK-2UKUI | 01:30 | "
            "NodeB-123 | PLN-456"
        )

        baris = mi.format_baris_down(
            1,
            info,
            {"GPON00-D1-AMK-2UKUI": "Critical"},
        )

        self.assertEqual(
            baris,
            "1 | DUMAI | GPON00-D1-AMK-2UKUI | 01:30 | "
            "NodeB-123 | 🟥 Critical | PLN-456",
        )

    def test_format_baris_down_uses_dash_for_missing_fields_and_severity(self):
        baris = mi.format_baris_down(
            2,
            "PADANG | GPON00-D1-UNKNOWN | 10 Menit",
            {},
        )

        self.assertEqual(
            baris,
            "2 | PADANG | GPON00-D1-UNKNOWN | 10 Menit | - | - | -",
        )

    def test_buat_laporan_list_uses_exact_down_header(self):
        mi.data_gpon_down["GPON00-D1-ARK-3SGA"] = (
            "BATAM | GPON00-D1-ARK-3SGA | 00:15 | NB-1 | ID-1"
        )

        laporan = mi.buat_laporan_list(
            {"GPON00-D1-ARK-3SGA": "Minor"}
        )

        self.assertIn(
            "NO | DISTRICT | HOSTNAME | DURASI DOWN | NodeB | SEVERITY | IdPLN",
            laporan,
        )
        self.assertIn(
            "1 | BATAM | GPON00-D1-ARK-3SGA | 00:15 | "
            "NB-1 | 🟠 Minor | ID-1",
            laporan,
        )

    def test_buat_laporan_list_uses_dash_when_sheet_read_fails(self):
        mi.data_gpon_down["GPON00-D1-UNKNOWN"] = (
            "PADANG | GPON00-D1-UNKNOWN | 10 Menit | NB-2 | ID-2"
        )

        with (
            mock.patch.object(
                mi,
                "ambil_mapping_severity",
                side_effect=RuntimeError("sheet unavailable"),
            ),
            mock.patch.object(mi, "simpan_log") as simpan_log,
        ):
            laporan = mi.buat_laporan_list()

        self.assertIn(
            "1 | PADANG | GPON00-D1-UNKNOWN | 10 Menit | NB-2 | - | ID-2",
            laporan,
        )
        self.assertIn("menggunakan '-'", simpan_log.call_args.args[0])
