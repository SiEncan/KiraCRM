"""Periksa jalur aplikasi yang dipakai warga dan halaman analisis saat ini."""

import unittest

from engine import Engine, MODEL_PER_RANGKAIAN
from presentation import Presentation
from server import create_app


class CurrentAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Model dimuat sekali; tiap tes tetap mengirim permintaan sendiri.
        cls.engine = Engine()
        cls.presentation = Presentation(cls.engine)
        cls.app = create_app(cls.engine, cls.presentation)

        report = cls.engine.data_uji_per_rangkaian["lengkap"].iloc[0]
        cls.report = {
            "kategori_laporan": report["Kategori Laporan"],
            "rincian_masalah": report.rincian_asli,
            "unit_penanganan": report["Unit Penanganan"],
            "kecamatan": report.Kecamatan,
            "kelurahan": report.Kelurahan,
            "kanal_aduan": report.Kanal_Aduan,
            "waktu_masuk": "2026-10-06T17:07",
            "mode": "model_utama",
            "sumber_model": "model_utama",
            "algorithm": "CatBoost",
        }

    def post(self, path, report):
        with self.app.test_client() as client:
            return client.post(
                path,
                json=report,
                base_url="http://127.0.0.1:8765",
            )

    def test_model_utama_and_four_input_variants(self):
        for versi_isian in MODEL_PER_RANGKAIAN:
            with self.subTest(versi_isian=versi_isian):
                report = self.report.copy()
                if versi_isian in ("tanpa_rincian", "dasar"):
                    report["rincian_masalah"] = ""
                if versi_isian in ("tanpa_unit", "dasar"):
                    report["unit_penanganan"] = ""

                response = self.post("/api/predict", report)
                self.assertEqual(response.status_code, 200, response.json)
                result = response.json
                self.assertEqual(result["model"], MODEL_PER_RANGKAIAN[versi_isian])
                self.assertGreaterEqual(result["estimate"], 0)
                self.assertLessEqual(
                    result["interval"]["lower"], result["interval"]["upper"]
                )

    def test_research_comparison_uses_three_algorithms(self):
        response = self.post("/api/context", self.report)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["model"], MODEL_PER_RANGKAIAN["lengkap"])
        rows = response.json["evaluation"]["comparison"]["rows"]
        self.assertEqual(
            [row["name"] for row in rows],
            ["Baseline median", "CatBoost", "Random Forest", "XGBoost"],
        )
        self.assertAlmostEqual(rows[1]["metrics"]["mae"], 61.73609646138523)

        analysis = self.post(
            "/api/analysis", {**self.report, "analysis_source": "test"}
        )
        self.assertEqual(analysis.status_code, 200, analysis.json)
        self.assertEqual(analysis.json["model"], MODEL_PER_RANGKAIAN["lengkap"])

    def test_only_used_api_routes_remain(self):
        with self.app.test_client() as client:
            base_url = "http://127.0.0.1:8765"
            self.assertEqual(client.get("/", base_url=base_url).status_code, 200)
            options = client.get("/options.json", base_url=base_url)
            self.assertEqual(options.status_code, 200)
            self.assertEqual(options.json, self.engine.options)
            self.assertEqual(client.get("/api/options", base_url=base_url).status_code, 404)
            self.assertEqual(client.get("/api/health", base_url=base_url).status_code, 200)

        for path in ("/api/compare", "/api/neighbors"):
            self.assertEqual(self.post(path, self.report).status_code, 404)

    def test_vercel_app_uses_cdn_for_frontend(self):
        api_app = create_app(self.engine, self.presentation, serve_frontend=False)
        with api_app.test_client() as client:
            self.assertEqual(client.get("/api/health").status_code, 200)
            for path in ("/", "/options.json", "/api/options", "/static/js/app.js"):
                self.assertEqual(client.get(path).status_code, 404)


if __name__ == "__main__":
    unittest.main()
