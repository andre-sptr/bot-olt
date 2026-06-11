import asyncio
from types import SimpleNamespace
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

    def test_buat_mapping_metadata_uses_e_l_m_n_o_columns(self):
        values = [
            [
                " gpon00-d1-amk-2ukui ",
                "",
                "",
                "",
                "",
                "",
                "",
                "critical",
                "TSEL",
                "2",
                "3",
            ],
            [
                "GPON00-D1-ARK-3SGA",
                "",
                "",
                "",
                "",
                "",
                "",
                "Minor",
                "",
                "1",
                "",
            ],
            ["", "", "", "", "", "", "", "Major", "ISAT", "4", "5"],
        ]

        mapping = mi.buat_mapping_metadata(values)

        self.assertEqual(
            mapping,
            {
                "GPON00-D1-AMK-2UKUI": {
                    "severity": "Critical",
                    "olo": "TSEL",
                    "k2": "2",
                    "k3": "3",
                },
                "GPON00-D1-ARK-3SGA": {
                    "severity": "Minor",
                    "olo": "",
                    "k2": "1",
                    "k3": "",
                },
            },
        )

    def test_ambil_mapping_metadata_uses_new_sheet_and_range(self):
        worksheet = mock.Mock()
        worksheet.get.return_value = []
        spreadsheet = mock.Mock()
        spreadsheet.get_worksheet_by_id.return_value = worksheet
        client_gs = mock.Mock()
        client_gs.open_by_key.return_value = spreadsheet

        with (
            mock.patch.object(
                mi.ServiceAccountCredentials,
                "from_json_keyfile_name",
                return_value=object(),
            ),
            mock.patch.object(mi.gspread, "authorize", return_value=client_gs),
        ):
            hasil = mi.ambil_mapping_metadata()

        self.assertEqual(hasil, {})
        client_gs.open_by_key.assert_called_once_with(
            "1crQdVmqXoROtuiaB4-ce7sIwJh26oxKMPq3Mj6-GyLU"
        )
        spreadsheet.get_worksheet_by_id.assert_called_once_with(1706912635)
        worksheet.get.assert_called_once_with("E3:O")

    def test_format_baris_down_inserts_sheet_metadata_in_requested_order(self):
        info = (
            "DUMAI | GPON00-D1-AMK-2UKUI | 01:30 | "
            "NodeB-123 | PLN-456"
        )

        baris = mi.format_baris_down(
            1,
            info,
            {
                "GPON00-D1-AMK-2UKUI": {
                    "severity": "Critical",
                    "olo": "TSEL",
                    "k2": "2",
                    "k3": "3",
                }
            },
        )

        self.assertEqual(
            baris,
            "1 | DUMAI | GPON00-D1-AMK-2UKUI | 01:30 | "
            "🟥 Critical | NodeB-123 | TSEL | 2 | 3 | PLN-456",
        )

    def test_format_baris_down_uses_dash_for_missing_fields_and_metadata(self):
        baris = mi.format_baris_down(
            2,
            "PADANG | GPON00-D1-UNKNOWN | 10 Menit",
            {},
        )

        self.assertEqual(
            baris,
            "2 | PADANG | GPON00-D1-UNKNOWN | 10 Menit | "
            "- | - | - | - | - | -",
        )

    def test_buat_laporan_list_uses_exact_down_header(self):
        mi.data_gpon_down["GPON00-D1-ARK-3SGA"] = (
            "BATAM | GPON00-D1-ARK-3SGA | 00:15 | NB-1 | ID-1"
        )

        laporan = mi.buat_laporan_list(
            {
                "GPON00-D1-ARK-3SGA": {
                    "severity": "Minor",
                    "olo": "ISAT",
                    "k2": "1",
                    "k3": "4",
                }
            }
        )

        self.assertIn(
            "NO | DISTRICT | HOSTNAME | DURASI DOWN | SEVERITY | "
            "NodeB | OLO | K2 | K3 | IdPLN",
            laporan,
        )
        self.assertIn(
            "1 | BATAM | GPON00-D1-ARK-3SGA | 00:15 | "
            "🟠 Minor | NB-1 | ISAT | 1 | 4 | ID-1",
            laporan,
        )

    def test_buat_laporan_list_uses_dash_when_sheet_read_fails(self):
        mi.data_gpon_down["GPON00-D1-UNKNOWN"] = (
            "PADANG | GPON00-D1-UNKNOWN | 10 Menit | NB-2 | ID-2"
        )

        with (
            mock.patch.object(
                mi,
                "ambil_mapping_metadata",
                side_effect=RuntimeError("sheet unavailable"),
            ),
            mock.patch.object(mi, "simpan_log") as simpan_log,
        ):
            laporan = mi.buat_laporan_list()

        self.assertIn(
            "1 | PADANG | GPON00-D1-UNKNOWN | 10 Menit | "
            "- | NB-2 | - | - | - | ID-2",
            laporan,
        )
        self.assertIn("menggunakan '-'", simpan_log.call_args.args[0])

    def test_durasi_ke_menit_supports_clock_and_text_formats(self):
        self.assertEqual(mi.durasi_ke_menit("01:00"), 60)
        self.assertEqual(mi.durasi_ke_menit("01:01"), 61)
        self.assertEqual(mi.durasi_ke_menit("08:30:45"), 510)
        self.assertEqual(mi.durasi_ke_menit("8 Jam 30 Menit"), 510)
        self.assertEqual(mi.durasi_ke_menit("45 Menit"), 45)
        self.assertIsNone(mi.durasi_ke_menit("-"))
        self.assertIsNone(mi.durasi_ke_menit("tidak diketahui"))

    def test_ambil_olt_down_lebih_satu_jam_uses_strict_boundary(self):
        mi.data_gpon_down.update(
            {
                "GPON-ONE-HOUR": (
                    "DUMAI | GPON-ONE-HOUR | 01:00 | NB-1 | ID-1"
                ),
                "GPON-OVER-HOUR": (
                    "PADANG | GPON-OVER-HOUR | 01:01 | NB-2 | ID-2"
                ),
                "GPON-INVALID": (
                    "BATAM | GPON-INVALID | - | NB-3 | ID-3"
                ),
            }
        )

        hasil = mi.ambil_olt_down_lebih_satu_jam()

        self.assertEqual(
            hasil,
            [
                {
                    "district": "PADANG",
                    "hostname": "GPON-OVER-HOUR",
                    "duration": "01:01",
                    "minutes": 61,
                }
            ],
        )

    def test_buat_pesan_eskalasi_is_compact_and_mentions_district_officer(self):
        daftar_down = [
            {
                "district": "DUMAI",
                "hostname": "GPON00-D1-BGU-3SPK",
                "duration": "08:30",
                "minutes": 510,
            }
        ]

        teks, mentions = mi.buat_pesan_eskalasi(
            daftar_down=daftar_down,
            manager_numbers=["08111111111", "+62 822-222-2222"],
            officer_by_district={
                "DUMAI": ["08133333333"],
                "PADANG": ["08144444444"],
            },
        )

        self.assertEqual(
            teks,
            "🚨 *ESKALASI OLT DOWN > 1 JAM*\n"
            "🔴 DUMAI | GPON00-D1-BGU-3SPK | 08:30\n"
            "\n"
            "@628111111111 @628222222222\n"
            "PIC DUMAI: @628133333333\n"
            "\n"
            "*SEGERA CONCALL & UPDATE PROGRES PENANGANAN.*",
        )
        self.assertEqual(
            mentions,
            [
                "628111111111@c.us",
                "628222222222@c.us",
                "628133333333@c.us",
            ],
        )
        self.assertNotIn("628144444444", teks)

    def test_buat_pesan_eskalasi_handles_multiple_districts_and_deduplicates(self):
        daftar_down = [
            {
                "district": "DUMAI",
                "hostname": "GPON-DUM",
                "duration": "01:30",
                "minutes": 90,
            },
            {
                "district": "PADANG",
                "hostname": "GPON-PDG",
                "duration": "02:15",
                "minutes": 135,
            },
        ]

        teks, mentions = mi.buat_pesan_eskalasi(
            daftar_down=daftar_down,
            manager_numbers=[
                "08111111111",
                "08111111111",
                "",
            ],
            officer_by_district={
                "DUMAI": ["08111111111", "08133333333"],
                "PADANG": ["08144444444"],
                "BATAM": ["08155555555"],
            },
        )

        self.assertIn("🔴 DUMAI | GPON-DUM | 01:30", teks)
        self.assertIn("🔴 PADANG | GPON-PDG | 02:15", teks)
        self.assertIn("PIC DUMAI: @628111111111 @628133333333", teks)
        self.assertIn("PIC PADANG: @628144444444", teks)
        self.assertNotIn("PIC BATAM", teks)
        self.assertEqual(
            mentions,
            [
                "628111111111@c.us",
                "628133333333@c.us",
                "628144444444@c.us",
            ],
        )

    def test_buat_pesan_eskalasi_returns_empty_when_no_incident_is_eligible(self):
        teks, mentions = mi.buat_pesan_eskalasi(daftar_down=[])

        self.assertIsNone(teks)
        self.assertEqual(mentions, [])

    def test_kirim_pesan_wa_adds_mentions_only_for_escalation(self):
        response = SimpleNamespace(status_code=200, text="OK")

        with (
            mock.patch.object(mi.requests, "post", return_value=response) as post,
            mock.patch.object(mi, "simpan_log"),
        ):
            self.assertTrue(
                mi.kirim_pesan_wa(
                    "alarm",
                    ["628111111111@c.us"],
                )
            )

        self.assertEqual(post.call_count, len(mi.GROUP_ID_TUJUAN))
        for panggilan, chat_id in zip(post.call_args_list, mi.GROUP_ID_TUJUAN):
            payload = panggilan.kwargs["json"]
            self.assertEqual(payload["chatId"], chat_id)
            self.assertEqual(payload["text"], "alarm")
            self.assertEqual(payload["mentions"], ["628111111111@c.us"])

        with (
            mock.patch.object(mi.requests, "post", return_value=response) as post,
            mock.patch.object(mi, "simpan_log"),
        ):
            self.assertTrue(mi.kirim_pesan_wa("laporan"))

        for panggilan in post.call_args_list:
            self.assertNotIn("mentions", panggilan.kwargs["json"])

    def test_proses_update_sends_report_then_separate_escalation(self):
        event = SimpleNamespace(
            text=(
                "!PROGRAM ZERO GAMAS OLT!\n"
                "- DISTRICT DUMAI\n"
                "GPON00-D1-BGU-3SPK | 01:30 | 0 | OLT SITE"
            )
        )

        with (
            mock.patch.object(mi, "buat_laporan_list", return_value="laporan"),
            mock.patch.object(mi, "simpan_ke_file_laporan"),
            mock.patch.object(mi, "simpan_log"),
            mock.patch.object(mi, "kirim_pesan_wa") as kirim,
            mock.patch.object(mi, "RAW_MANAGER_WA", ["08111111111"]),
            mock.patch.object(
                mi,
                "RAW_OFFICER_DISTRIK",
                {"DUMAI": ["08133333333"]},
            ),
        ):
            asyncio.run(mi.proses_pesan_baru(event))

        self.assertEqual(kirim.call_count, 2)
        self.assertEqual(kirim.call_args_list[0], mock.call("laporan"))

        teks_eskalasi, mentions = kirim.call_args_list[1].args
        self.assertIn("ESKALASI OLT DOWN > 1 JAM", teks_eskalasi)
        self.assertIn("DUMAI | GPON00-D1-BGU-3SPK | 01:30", teks_eskalasi)
        self.assertEqual(
            mentions,
            [
                "628111111111@c.us",
                "628133333333@c.us",
            ],
        )
