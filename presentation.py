"""Siapkan pembanding, grafik, dan acuan SK bagi aplikasi CRM."""

from pathlib import Path
import re
import unicodedata
import numpy as np
import pandas as pd
from engine import ROOT, ANALYSIS_SOURCE, MODEL_PER_RANGKAIAN, ALGORITHMS, matrix, format_count

RULES = ROOT / "data/aturan_SK.csv"
ANALYSIS_PREDICTIONS = ANALYSIS_SOURCE / "prediksi_semua_kombinasi.csv"
ANALYSIS_ROUTES = {
    "lengkap": ("lengkap__tfidf", "lengkap"),
    "tanpa_unit": ("tanpa_unit__tfidf", "tanpa_unit"),
    "tanpa_rincian": ("tanpa_rincian__kategori", "tanpa_rincian"),
    "dasar": ("dasar__kategori", "dasar"),
}



# Samakan huruf besar/kecil, spasi, dan tanda baca sebelum mencocokkan teks. Ini untuk
# pencarian nama, bukan encoding input model.
def normalize(value):
    """Samakan huruf dan tanda baca untuk mencari pasangan pada tabel aturan SK."""

    value = unicodedata.normalize("NFKC", str(value)).casefold()

    return " ".join(re.sub("[^\\w\\s]", " ", value).split())


def metrics(actual, prediction):
    """Hitung MAE, RMSE, R2, dan median error dalam satuan jam."""

    actual_hours, predicted_hours = (
        np.asarray(actual, float),
        np.asarray(prediction, float),
    )
    error = actual_hours - predicted_hours
    # R2 membandingkan error kuadrat dengan variasi aktual kelompok yang dinilai. Kalau
    # kelompoknya diganti, pembanding R2 ikut berubah; nilainya bukan ukuran meleset dalam
    # jam.
    denominator = np.sum((actual_hours - actual_hours.mean()) ** 2)

    return dict(
        n=len(actual_hours),
        mae=float(np.abs(error).mean()),
        rmse=float(np.sqrt(np.mean(error**2))),
        r2=(
            float(1 - np.sum(error**2) / denominator)
            if len(actual_hours) > 1 and denominator
            else None
        ),
        median_error=float(np.median(np.abs(error))),
    )


def distribution(isian):
    """Ringkas sebaran durasi menjadi kuartil dan batang histogram."""

    isian = np.asarray(isian, dtype=float)
    # Kelompokkan durasi menjadi batang histogram dan hitung jumlah anggotanya. Median dan
    # kuartil juga memakai daftar durasi yang sama.
    counts, edges = np.histogram(
        isian, bins=min(12, max(3, int(np.sqrt(len(isian)))))
    )

    return dict(
        n=len(isian),
        median=float(np.median(isian)),
        q1=float(np.quantile(isian, 0.25, method="inverted_cdf")),
        q3=float(np.quantile(isian, 0.75, method="inverted_cdf")),
        p90=float(np.quantile(isian, 0.9)),
        minimum=float(isian.min()),
        maximum=float(isian.max()),
        histogram=[
            dict(lower=float(lower_edge), upper=float(upper_edge), count=int(bin_count))
            for lower_edge, upper_edge, bin_count in zip(edges[:-1], edges[1:], counts)
        ],
    )


class Presentation:

    def __init__(self, engine):
        """Baca tabel pencocokan SK; tidak mengubah atau melatih model."""

        # engine dikirim dari create_app() saat objek Presentation dibuat. Simpan sebagai
        # self.engine supaya fungsi lain bisa memakai model dan data yang sama.
        self.engine = engine
        # aturan_SK.csv berisi tabel acuan dari dua PDF SK. Dipakai untuk membandingkan hasil
        # model, tidak untuk menghitung atau melatih prediksinya.
        self.rules = pd.read_csv(RULES, float_precision="round_trip").fillna("")
        self.rules["_category"] = self.rules["Kategori CRM"].map(normalize)
        self.rules["_detail"] = self.rules["Rincian dataset"].map(normalize)

        # Tabel ini berisi hasil pengujian tersimpan, bukan hasil latihan baru.
        # Metrik seluruh uji memakai hasil prediksi yang sudah disimpan saat eksperimen. Kartu
        # estimasi isian baru tetap menghitung lewat predict_analysis().
        self.prediksi_data_uji = pd.read_csv(
            ANALYSIS_PREDICTIONS,
            float_precision="round_trip",
        )
        # CSV percobaan lama masih memakai cb/rf/xgb. Samakan nama kolom sekali
        # saat dibaca; kode analisis selanjutnya memakai nama lengkap algoritma.
        kolom_arsip = {}
        for spec_id, _ in ANALYSIS_ROUTES.values():
            for kode_lama, algorithm in [("cb", "CatBoost"), ("rf", "Random Forest"), ("xgb", "XGBoost")]:
                lama = "prediksi_" + spec_id + "__" + kode_lama
                baru = "prediksi_" + spec_id + "_" + algorithm.lower().replace(" ", "_")
                if baru not in self.prediksi_data_uji.columns:
                    kolom_arsip[lama] = baru
        self.prediksi_data_uji = self.prediksi_data_uji.rename(columns=kolom_arsip)
        # Hasil latihan baru diperlukan jika peneliti memilih Latihan/Keduanya.
        # Model tidak dilatih ulang; yang dihitung hanya prediksi dan indeks daun.
        # Prediksi dan daun latihan baru dihitung saat Latihan/Keduanya dipilih. Simpan
        # hasilnya di sini supaya tidak mengulang semua hitungan saat sumber diganti lagi.
        self.analisis_data_latih = {}

    def history(self, data_latih, isian):
        """Cari pembanding rincian yang sama; jika jumlahnya kurang, pakai kategori."""

        # Pembanding warga memakai latihan dengan kategori dan rincian yang sama.
        kategori_laporan = data_latih[data_latih["Kategori Laporan"].eq(isian["kategori_laporan"])]
        group, level = (kategori_laporan, "kategori")
        note = (
            "Perbandingan menggunakan laporan terdahulu dalam kategori yang sama."
        )

        if isian["rincian_masalah"]:
            specific = kategori_laporan[kategori_laporan.rincian_asli.eq(isian["rincian_masalah"])]

            # Kalau rincian punya kurang dari 10 contoh, pakai kelompok kategorinya. Kalau
            # kategori juga kurang dari 10, pembanding tidak ditampilkan.
            if len(specific) >= 10:
                group, level = (specific, "rincian")
                note = "Perbandingan menggunakan laporan dengan kategori dan rincian masalah yang sama."
            else:
                note = "Sebagai gambaran, perbandingan menggunakan laporan terdahulu dalam kategori yang sama."

        if len(group) < 10:
            return dict(
                available=False,
                n=len(group),
                note="Belum tersedia cukup laporan sejenis untuk ditampilkan sebagai perbandingan.",
            )

        return dict(
            available=True,
            level=level,
            note=note,
            limited=len(group) < 30,
            **distribution(group.durasi_jam),
        )

    def sk(self, isian):
        """Utamakan kecocokan teks rincian pada kedua SK, tanpa memakai tanggal."""

        # base menampung jawaban awal saat aturan SK belum ketemu. dict(base, ...) menyalin
        # isinya lalu menambah atau mengganti bagian yang diperlukan.
        base = dict(
            available=False,
            version=None,
            bands=[],
            selection_reason=(
                "Acuan pembanding dipilih berdasarkan kecocokan rincian pada dua SK."
            ),
            note=(
                "Acuan berasal dari dua SK yang digunakan dalam penelitian; bukan "
                "verifikasi pembaruan peraturan setelah 2025."
            ),
        )

        if not isian["rincian_masalah"]:
            return dict(
                base, reason="Pilih rincian masalah untuk melihat acuan waktu pada SK Sekda."
            )

        # Cari teks rincian pada kedua SK. Tanggal laporan tidak memilih versi SK di aplikasi
        # ini. Kategori membantu membedakan nama rincian yang berulang, misalnya Lain-lain.
        rincian_masalah = normalize(isian["rincian_masalah"])
        candidates = self.rules[self.rules["_detail"] == rincian_masalah]

        # Rincian seperti Lain-lain dapat dipakai oleh banyak kategori.
        # Kategori membantu membedakan konteks, bukan menentukan versi SK.
        same_category = candidates[
            candidates["_category"] == normalize(isian["kategori_laporan"])
        ]

        if not same_category.empty:
            candidates = same_category
        elif candidates["_category"].nunique() > 1:
            candidates = candidates.iloc[:0]

        candidates = candidates[
            candidates["Versi SK"].isin(["99/2022", "175/2025"])
            & candidates["Status pencocokan"].ne("Aturan tidak ditemukan")
        ]

        if candidates.empty:
            return dict(
                base,
                reason="Acuan waktu untuk rincian ini belum tersedia di aplikasi.",
            )

        # Teks yang persis sama didahulukan dari pasangan berdasarkan kesamaan isi.
        exact = candidates[
            candidates["Rincian pasangan SK"].map(normalize) == rincian_masalah
        ]

        if not exact.empty:
            candidates = exact

        # Jika tingkat kecocokannya sama, gunakan versi yang lebih baru.
        version = (
            "175/2025"
            if candidates["Versi SK"].eq("175/2025").any()
            else "99/2022"
        )
        base["version"] = version
        candidates = candidates[candidates["Versi SK"] == version]

        columns = [
            "Rincian pasangan SK",
            "100% min",
            "100% max",
            "80% min",
            "80% max",
            "60% min",
            "60% max",
            "40% min",
            "40% max",
            "Acuan khusus",
        ]
        # Beberapa baris bisa punya aturan waktu yang sama. Gabungkan yang sama dulu agar
        # tidak dianggap sebagai beberapa pilihan berbeda.
        candidates = candidates.drop_duplicates(subset=columns)

        # Kalau masih tersisa beberapa aturan waktu berbeda, jangan pilih asal salah satunya.
        if len(candidates) != 1:
            return dict(
                base,
                reason="Acuan waktu belum dapat ditampilkan karena ditemukan beberapa aturan yang berbeda.",
            )

        row = candidates.iloc[0]

        if row["Status pencocokan"] == "Aturan tidak ditemukan":
            return dict(
                base,
                reason="Acuan waktu untuk rincian ini belum tersedia di aplikasi.",
            )

        bands = []

        # Ambil batas jam tiap kelompok untuk kotak SK di frontend. Nilai 100/80/60/40 adalah
        # kelompok waktu SK, bukan akurasi model.
        for score in [100, 80, 60, 40]:
            lower_bound, upper_bound = (
                row[str(score) + "% min"],
                row[str(score) + "% max"],
            )

            if lower_bound != "" or upper_bound != "":
                bands.append(
                    dict(
                        score=score,
                        lower=float(lower_bound) if lower_bound != "" else None,
                        upper=float(upper_bound) if upper_bound != "" else None,
                    )
                )

        special = str(row["Acuan khusus"])

        if not bands and (not special):
            return dict(
                base,
                reason="Rentang waktu untuk rincian ini belum tersedia di aplikasi.",
            )

        # Sertakan halaman PDF supaya tombol sumber langsung membuka bagian aturan yang
        # dipakai.
        if row["Halaman PDF"] != "":
            page = int(float(row["Halaman PDF"]))
        else:
            page = None

        return dict(
            base,
            available=True,
            bands=bands,
            special=special,
            page=page,
            description=str(row["Rincian pasangan SK"]),
            match=str(row["Status pencocokan"]),
            source_url="/documents/sk-"
            + ("99-2022" if version == "99/2022" else "175-2025")
            + ".pdf"
            + (f"#page={page}" if page else ""),
            source_note=str(row["Catatan rentang SK"]),
        )

    # Buat tebakan median dari latihan, lalu cocokkan ke laporan yang dinilai. Durasi aktual
    # laporan tersebut tidak ikut membuat tebakannya.
    @staticmethod
    def baseline(data_latih, target_reports, versi_isian):
        """Buat prediksi median dari kelompok latihan yang sesuai kelengkapan isian."""

        layers = []

        if versi_isian == "lengkap":
            layers.append(["Kategori Laporan", "rincian_asli", "Unit Penanganan"])

        if versi_isian in ["lengkap", "tanpa_unit"]:
            layers.append(["Kategori Laporan", "rincian_asli"])

        if versi_isian == "tanpa_rincian":
            layers.append(["Kategori Laporan", "Unit Penanganan"])

        # layers berisi urutan kelompok dari yang lebih spesifik ke yang lebih umum. Kalau
        # kelompok belum cukup datanya, lanjut cari median di kelompok berikutnya.
        layers.append(["Kategori Laporan"])
        prediction = pd.Series(np.nan, index=target_reports.index)

        # Kelompok median perlu minimal 10 contoh latihan. Ini aturan baseline, bukan syarat
        # melatih CatBoost global atau menghitung IQR.
        for columns in layers:
            summary = data_latih.groupby(columns, dropna=False).durasi_jam.agg(
                ["size", "median"]
            )
            summary = summary[summary["size"] >= 10]["median"]
            lookup = {
                kunci_model if isinstance(kunci_model, tuple) else (kunci_model,): value
                for kunci_model, value in summary.items()
            }
            candidate = pd.Series(
                [
                    lookup.get(tuple(row), np.nan)
                    for row in target_reports[columns].itertuples(
                        index=False, name=None
                    )
                ],
                index=target_reports.index,
            )

            prediction = prediction.fillna(candidate)

        return prediction.fillna(float(data_latih.durasi_jam.median())).to_numpy()

    def compare_main_models(self, versi_isian, neighbors):
        """Bandingkan tiga algoritma dan median pada laporan uji yang persis sama."""

        source = self.prediksi_data_uji
        data_uji_tersimpan = self.engine.data_uji_per_rangkaian[versi_isian]
        spec_id, median_id = ANALYSIS_ROUTES[versi_isian]

        # Pastikan tabel pembanding memakai baris, durasi, dan penyaringan yang sama.
        for column in ["baris_excel_sumber", "durasi_jam", "lolos_IQR_kategori"]:
            np.testing.assert_array_equal(source[column], data_uji_tersimpan[column])

        np.testing.assert_array_equal(
            source["prediksi_" + spec_id + "_catboost"], data_uji_tersimpan.prediksi_jam
        )

        # Metrik keseluruhan memakai semua uji lolos IQR. MAE sejenis hanya memakai 30 anggota
        # yang dipilih CatBoost, dan anggotanya sama untuk semua model.
        data_uji = source.loc[source.lolos_IQR_kategori]
        # Satu kelompok uji yang sama untuk keempat baris tabel, bukan dicari ulang
        # oleh tiap algoritma. Durasi aktual tidak dipakai untuk memilih anggotanya.
        report_ids = [row["id"] for row in neighbors["rows"]]
        same_report_type = data_uji.baris_excel_sumber.isin(report_ids)
        similar_count = int(same_report_type.sum())
        rows = []

        for label, prediction_column in [
            ("Baseline median", "prediksi_median_" + median_id),
            ("CatBoost", "prediksi_" + spec_id + "_catboost"),
            ("Random Forest", "prediksi_" + spec_id + "_random_forest"),
            ("XGBoost", "prediksi_" + spec_id + "_xgboost"),
        ]:
            overall = metrics(data_uji.durasi_jam, data_uji[prediction_column])
            similar_mae = None

            if similar_count:
                similar = data_uji.loc[same_report_type]
                errors = similar.durasi_jam - similar[prediction_column]
                similar_mae = float(errors.abs().mean())

            rows.append(
                dict(
                    name=label,
                    metrics=overall,
                    similar_mae=similar_mae,
                    similar_n=similar_count,
                    selected=label == "CatBoost",
                )
            )

        return dict(
            rows=rows,
            n=len(data_uji),
            similar_n=similar_count,
            similar_ids=report_ids,
            similar_scope="kemiripan daun CatBoost tertinggi dengan isian",
            source=str(ANALYSIS_PREDICTIONS.relative_to(ROOT)),
        )

    def describe_main(self, versi_isian, kunci_model, model_info, isian, waktu_masuk, tabel_masukan):
        """Metrik/grafik berasal dari uji; SD rentang tetap dari OOF latihan."""

        data_uji_seluruh = self.engine.data_uji_per_rangkaian[versi_isian]
        data_uji = data_uji_seluruh.loc[data_uji_seluruh.lolos_IQR_kategori].copy()
        data_latih = self.engine.data_latih_iqr
        # Saat /api/context diminta, pilih 30 uji lalu pakai ID yang sama untuk histogram, MAE
        # sejenis, dan penanda grafik.
        neighbors = self.nearest_test_reports(tabel_masukan, versi_isian)
        similar_ids = {row["id"] for row in neighbors["rows"]}
        # Isi tiap titik: nomor baris, aktual, prediksi, dan penanda apakah masuk 30 terdekat.
        # Semua uji lolos IQR tetap ada di grafik; 30 anggota hanya diberi warna berbeda.
        scatter = [
            [
                int(row_id),
                float(actual),
                float(prediction),
                int(row_id) in similar_ids,
            ]
            for row_id, actual, prediction, kategori_laporan, rincian_masalah in zip(
                data_uji.baris_excel_sumber,
                data_uji.durasi_jam,
                data_uji.prediksi_jam,
                data_uji["Kategori Laporan"],
                data_uji.rincian_asli,
            )
        ]

        return dict(
            model=kunci_model,
            neighbors=neighbors,
            history=self.history(data_latih, isian),
            sk=self.sk(isian),
            snapshot=dict(
                training_used=len(data_latih),
                training_initial=len(self.engine.data_latih_awal),
                calibration_n=model_info["evidence"]["n"],
                test=len(data_uji_seluruh),
                test_filtered=len(data_uji),
                split=self.engine.model_manifest["split"] + "; IQR per kategori dari latihan saja",
                calibration="Error OOF 5-fold dalam 80% latihan, pembagi n - 1",
                note=(
                    f"Model akhir CatBoost memakai {format_count(len(data_latih))} dari {format_count(len(self.engine.data_latih_awal))} latihan. "
                    f"Tidak ada validasi terpisah. Metrik utama/grafik menilai {format_count(len(data_uji))} uji lolos IQR; "
                    f"ringkasan seluruh {format_count(len(data_uji_seluruh))} uji tetap ditampilkan."
                ),
            ),
            evaluation=dict(
                scope="Uji lolos IQR kategori",
                model=model_info["evaluation"]["primary"],
                baseline=metrics(data_uji.durasi_jam, data_uji.median_bertingkat_jam),
                baseline_label="Median bertingkat Bab II (dari latihan)",
                scatter=scatter,
                scatter_scope="Uji lolos IQR kategori",
                test_summary=model_info["test_summary"],
                calibration=model_info["evidence"],
                is_final=True,
                comparison=self.compare_main_models(versi_isian, neighbors),
            ),
        )

    def nearest_test_reports(self, tabel_masukan, versi_isian):
        """Pilih 30 laporan uji dari fitur saja; jawaban aktual tidak menentukan peringkat."""

        # Ini jalan pintas untuk sumber uji. Pengurutan daun tetap lewat nearest_reports(),
        # sama seperti saat memilih sumber latihan.
        return self.nearest_reports(tabel_masukan, versi_isian, "test")

    def analysis_reference(self, versi_isian, source):
        """Ambil tabel prediksi dan daun dari sumber yang diminta peneliti."""

        kunci_model = MODEL_PER_RANGKAIAN[versi_isian]
        spec_id, median_id = ANALYSIS_ROUTES[versi_isian]

        # Prediksi dan daun uji sudah tersedia. Cek urutannya supaya daun laporan A tidak
        # sampai terpasang ke laporan B.
        if source == "test":
            data_pembanding = self.prediksi_data_uji.loc[self.prediksi_data_uji.lolos_IQR_kategori]
            data_uji_tersimpan = self.engine.data_uji_per_rangkaian[versi_isian]
            data_uji_tersimpan = data_uji_tersimpan.loc[data_uji_tersimpan.lolos_IQR_kategori]
            np.testing.assert_array_equal(data_pembanding.baris_excel_sumber, data_uji_tersimpan.baris_excel_sumber)

            return data_pembanding, self.engine.daun_data_uji[kunci_model]

        # Kalau latihan belum pernah diminta untuk versi ini, hitung prediksi dan daunnya
        # dulu. Model akhir sudah mempelajari latihan ini, jadi error-nya bukan OOF atau hasil
        # uji baru.
        if versi_isian not in self.analisis_data_latih:
            data_pembanding = self.engine.data_latih_iqr.copy()
            leaves = None

            for algorithm in ALGORITHMS:
                paket_model = self.engine.analysis_models[versi_isian][algorithm]
                model_input = matrix(data_pembanding, paket_model["encoding"], paket_model["algorithm"])

                if algorithm == "CatBoost":
                    logs = paket_model["model"].predict(model_input, thread_count=2)
                    leaves = paket_model["model"].calc_leaf_indexes(model_input, thread_count=2)
                else:
                    logs = paket_model["model"].predict(model_input)

                data_pembanding["prediksi_" + spec_id + "_" + algorithm.lower().replace(" ", "_")] = np.maximum(
                    np.expm1(np.asarray(logs, dtype=float)), 0
                )

            data_pembanding["prediksi_median_" + median_id] = self.baseline(data_pembanding, data_pembanding, versi_isian)
            leaves = leaves.astype(np.uint8 if leaves.max() < 256 else np.uint16)
            leaves.setflags(write=False)
            self.analisis_data_latih[versi_isian] = (data_pembanding, leaves)

        return self.analisis_data_latih[versi_isian]

    def nearest_reports(self, tabel_masukan, versi_isian, source):
        """Pilih tetangga menurut daun; sumber latih dan uji tidak dicampurkan."""

        kunci_model = MODEL_PER_RANGKAIAN[versi_isian]
        paket_model = self.engine.bundle(kunci_model)
        data_pembanding, leaves = self.analysis_reference(versi_isian, source)
        target_input = matrix(tabel_masukan, paket_model["encoding"], paket_model["algorithm"])
        target = paket_model["model"].calc_leaf_indexes(target_input, thread_count=2)[0]
        # Satu baris leaves berisi nomor daun sebuah laporan pada semua pohon. Bandingkan
        # dengan isian baru, lalu hitung berapa pohon yang daunnya sama.
        shared_trees = np.count_nonzero(leaves == target, axis=1)

        # Jika skornya sama, pertahankan urutan uji tersimpan. Tidak melihat durasi.
        # Minus di depan skor membuat yang terbesar diurutkan lebih dulu. Ambil 30 pertama.
        # Anggotanya boleh beda kategori karena modelnya global.
        order = np.argsort(-shared_trees, kind="stable")[:30]
        selected = data_pembanding.iloc[order]
        source_label = "uji" if source == "test" else "latihan"
        durations = selected.durasi_jam.to_numpy()
        # Pilih anggota berdasarkan daun dulu, baru ambil durasinya untuk median dan kuartil.
        # Durasi aktual tidak menentukan siapa yang terpilih.
        median = float(np.median(durations))
        # Pemeriksaan saja: keluarkan masing-masing anggota dari salinan angka.
        # Untuk 30 anggota, besar perubahan absolutnya sama bagi setiap anggota.
        # Coba keluarkan tiap anggota bergantian dari salinan daftar durasi. Hitung perubahan
        # median dari 30 menjadi 29 anggota, lalu ambil rata-rata selisihnya dalam jam.
        changes = [abs(float(np.median(np.delete(durations, i))) - median) for i in range(len(durations))]
        rows = [
            dict(
                id=int(row.baris_excel_sumber),
                duration=float(row.durasi_jam),
                similarity=float(shared_trees[pos] / len(target) * 100),
                kategori_laporan=row["Kategori Laporan"],
                rincian_masalah=row.rincian_asli,
                unit_penanganan=row["Unit Penanganan"],
                shared_trees=int(shared_trees[pos]),
            )
            for pos, (_, row) in zip(order, selected.iterrows())
        ]

        # Kelompok ini hanya untuk analisis; estimasi warga dan SD OOF tidak berubah.
        return dict(
            available=True,
            model=kunci_model,
            algorithm=paket_model["algorithm"],
            trees=len(target),
            candidates=len(data_pembanding),
            source=source_label + " lolos IQR kategori",
            source_key=source,
            mean_similarity=float(np.mean(shared_trees[order]) / len(target) * 100),
            median_change_hours=float(np.mean(changes)),
            rows=rows,
            **distribution(selected.durasi_jam),
            note=(
                "Peringkat berdasarkan persentase pohon yang menempatkan laporan pada "
                f"daun yang sama. Semua anggota berasal dari data {source_label} lolos IQR kategori. "
                f"Nilai seri mengikuti urutan {source_label} tersimpan, bukan durasi aktual. "
                "Kelompok yang sama dipakai untuk histogram, kuartil, MAE sejenis, dan penanda grafik."
            ),
        )

    def analysis_group(self, tabel_masukan, versi_isian, source):
        """Susun satu kelompok, metrik lokal, dan grafik dari sumber yang sama."""

        neighbors = self.nearest_reports(tabel_masukan, versi_isian, source)
        data_pembanding, _ = self.analysis_reference(versi_isian, source)
        # Tabel daftar 30 memang sudah dihapus, tetapi ID dan durasinya masih dipakai.
        # Histogram, MAE kelompok, dan penanda grafik harus mengambil anggota yang sama.
        ids = {row["id"] for row in neighbors["rows"]}
        selected = data_pembanding.loc[data_pembanding.baris_excel_sumber.isin(ids)]
        spec_id, median_id = ANALYSIS_ROUTES[versi_isian]
        local_rows = []

        for name, column in [
            ("Baseline median", "prediksi_median_" + median_id),
            ("CatBoost", "prediksi_" + spec_id + "_catboost"),
            ("Random Forest", "prediksi_" + spec_id + "_random_forest"),
            ("XGBoost", "prediksi_" + spec_id + "_xgboost"),
        ]:
            local_rows.append(dict(name=name, mae=float(np.abs(selected.durasi_jam-selected[column]).mean())))

        scatter = [
            [int(row_id), float(actual), float(prediction), int(row_id) in ids, source]
            for row_id, actual, prediction in zip(
                data_pembanding.baris_excel_sumber, data_pembanding.durasi_jam, data_pembanding["prediksi_" + spec_id + "_catboost"]
            )
        ]

        return dict(source=source, label="Data uji" if source == "test" else "Data latihan", neighbors=neighbors, rows=local_rows, scatter=scatter)

    def analysis(self, isian_laporan):
        """Layanan khusus peneliti untuk pilihan Uji, Latihan, atau Keduanya."""

        source = isian_laporan.get("analysis_source", "test")

        if source not in ["test", "train", "both"]:
            raise ValueError("Pilih sumber pembanding: uji, latihan, atau keduanya.")

        tabel_masukan, versi_isian, _, isian = self.engine.input_frame(isian_laporan)
        kunci_model, _ = self.engine.resolve(isian_laporan, versi_isian, isian)

        if kunci_model != MODEL_PER_RANGKAIAN[versi_isian]:
            raise ValueError("Pemilih sumber tersedia untuk model akhir CatBoost.")

        # Keduanya mengambil 30 uji dan 30 latihan secara terpisah. Bukan 30 dari gabungan dua
        # sumber.
        sources = ["test", "train"] if source == "both" else [source]

        return dict(
            source=source,
            model=kunci_model,
            groups=[self.analysis_group(tabel_masukan, versi_isian, item) for item in sources],
        )

    def describe(self, isian_laporan):
        """Siapkan data model utama, SK, grafik, dan tiga pembanding penelitian."""
        tabel_masukan, versi_isian, waktu_masuk, isian = self.engine.input_frame(isian_laporan)
        kunci_model, _ = self.engine.resolve(isian_laporan, versi_isian, isian)
        context = self.describe_main(versi_isian, kunci_model, self.engine.informasi_model_utama[kunci_model],
                                      isian, waktu_masuk, tabel_masukan)
        # Kartu tiga model menghitung prediksi baru untuk isian sekarang. Angka ini berbeda
        # dari metrik seluruh uji yang sudah disimpan saat eksperimen.
        context["live_predictions"] = self.engine.predict_analysis(tabel_masukan, versi_isian)
        return context

