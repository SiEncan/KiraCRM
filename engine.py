"""Jalankan model utama CRM dan tiga algoritma pembanding yang sudah dilatih."""

from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import json

import joblib
import numpy as np
import pandas as pd
from scipy import sparse

ROOT = Path(__file__).resolve().parent
MODEL_DIR = Path(__file__).resolve().parent / "models/catboost_global_log_iqr_kategori"
# Empat versi ini mengikuti kolom yang diisi, bukan kategori laporan. Rincian dan unit bisa
# kosong, jadi tiap versi punya model sendiri.
MODEL_PER_RANGKAIAN = {
    "lengkap":        "model_utama:lengkap",
    "tanpa_unit":     "model_utama:tanpa_unit",
    "tanpa_rincian":  "model_utama:tanpa_rincian",
    "dasar":          "model_utama:dasar"
}

ANALYSIS_SOURCE = ROOT / json.loads((MODEL_DIR / "manifest.json").read_text(encoding="utf-8"))["analysis_source"]
ALGORITHMS = ["CatBoost", "Random Forest", "XGBoost"]
VARIANT_NAMES = {
    "lengkap": "Fitur lengkap",
    "tanpa_unit": "Tanpa unit penanganan",
    "tanpa_rincian": "Tanpa rincian masalah",
    "dasar": "Tanpa rincian dan unit",
}
INTERVAL_SD_MULTIPLIER = 0.67
PREDICTION_THREADS = 2



def read_csv(path):
    """Baca CSV tanpa mengurangi ketelitian angka hasil eksperimen."""

    return pd.read_csv(path, float_precision="round_trip")


def format_count(value):
    """Tampilkan jumlah laporan seperti 14746 menjadi 14.746."""

    return format(int(value), ",d").replace(",", ".")


def build_form_options(data_latih, data_latih_iqr):
    """Susun daftar pilihan dari paket data latih aplikasi."""

    kelompok_kategori = data_latih.groupby("Kategori Laporan")
    kelompok_kecamatan = data_latih.groupby("Kecamatan")

    return dict(
        kategori_laporan=sorted(data_latih["Kategori Laporan"].unique().tolist()),
        rincian_per_kategori={
            kategori: sorted(group.rincian_asli.unique().tolist())
            for kategori, group in kelompok_kategori
        },
        kelurahan_per_kecamatan={
            kecamatan: sorted(group.Kelurahan.unique().tolist())
            for kecamatan, group in kelompok_kecamatan
        },
        kanal_aduan=sorted(data_latih.Kanal_Aduan.unique().tolist()),
        unit_penanganan=sorted(data_latih["Unit Penanganan"].unique().tolist()),
        unit_per_kategori={
            kategori: sorted(group["Unit Penanganan"].unique().tolist())
            for kategori, group in kelompok_kategori
        },
        source=(
            f"Pilihan diambil dari {format_count(len(data_latih))} laporan latihan acak 80%. "
            "Pilihan tidak dipelajari dari 20% uji."
        ),
        kategori_dalam_latihan=sorted(data_latih_iqr["Kategori Laporan"].unique().tolist()),
    )


def format_number(value, decimals=2):
    """Format angka untuk kalimat keterangan: 12.50 menjadi 12,50."""

    return f"{float(value):.{decimals}f}".replace(".", ",")


def matrix(tabel_masukan, encoding, algorithm):
    """Ubah kolom laporan ke bentuk angka/teks yang diminta model tersimpan."""

    # 1. Ambil daftar kolom dan encoding yang disimpan saat latihan.
    # Ambil daftar dan urutan kolom dari encoding hasil training. Urutannya harus tetap sama
    # saat laporan baru masuk.
    categorical_columns = encoding["categorical_columns"]
    numeric_columns = encoding["numeric_columns"]
    vectorizer = encoding["vectorizer"]

    # 2. Ubah teks rincian menjadi TF-IDF jika model memakai representasi ini.
    # transform memakai kosakata lama; fit akan mempelajari ulang dan tidak dipakai di sini.
    if vectorizer is None:
        detail_vectors = None
    else:
        # Untuk TF-IDF, ambil teks dari kolom Rincian Masalah. Kosakata dan bobotnya sudah ada
        # dari training; di sini tinggal pakai transform.
        detail_text = tabel_masukan["Rincian Masalah"].fillna("").astype(str)
        detail_vectors = vectorizer.transform(detail_text).astype(np.float32)

    # 3. CatBoost menerima kolom kategorikal berupa teks.
    if algorithm == "CatBoost":
        model_input = (
            tabel_masukan[categorical_columns].astype(str).reset_index(drop=True).copy()
        )

        # Gabungkan angka jam, hari, dan akhir pekan dengan kolom kategori. Kategori tetap
        # berupa teks karena CatBoost mengolahnya sendiri.
        for column in numeric_columns:
            model_input[column] = tabel_masukan[column].to_numpy(dtype=np.float32)

        if detail_vectors is not None:
            tfidf_columns = [f"tfidf_{i}" for i in range(detail_vectors.shape[1])]
            tfidf_frame = pd.DataFrame(
                detail_vectors.toarray(),
                columns=tfidf_columns,
            )

            model_input = pd.concat([model_input, tfidf_frame], axis=1)

        return model_input

    # 4. Random Forest dan XGBoost menerima kategori yang sudah diubah menjadi angka.
    # RF dan XGBoost perlu input angka. Kategori diubah memakai TargetEncoder yang sudah
    # disimpan saat training.
    encoded_categories = encoding["encoder"].transform(
        tabel_masukan[categorical_columns].astype(str)
    )

    # Gabungkan hasil encoding kategori, angka waktu, dan TF-IDF. Bentuk sparse dipakai supaya
    # banyak angka nol tidak menghabiskan memori.
    input_parts = [
        sparse.csr_matrix(encoded_categories, dtype=np.float32),
        sparse.csr_matrix(tabel_masukan[numeric_columns].to_numpy(dtype=np.float32)),
    ]

    if detail_vectors is not None:
        input_parts.append(detail_vectors)

    return sparse.hstack(input_parts, format="csr", dtype=np.float32)


def predict_model_log(tabel_masukan, paket_model):
    """Jalankan encoding dan model tersimpan; hasil masih berupa log(1 + jam)."""

    # Siapkan input lewat matrix(), baru panggil predict(). Hasilnya masih log(1 + jam), jadi
    # perlu dikembalikan ke jam sebelum ditampilkan.
    model_input = matrix(tabel_masukan, paket_model["encoding"], paket_model["algorithm"])

    if paket_model["algorithm"] == "CatBoost":
        prediction = paket_model["model"].predict(
            model_input,
            thread_count=PREDICTION_THREADS,
        )
    else:
        prediction = paket_model["model"].predict(model_input)

    predicted_log = float(np.asarray(prediction).reshape(-1)[0])

    if not np.isfinite(predicted_log):
        raise ValueError("Model menghasilkan angka tidak valid untuk input ini.")

    return predicted_log


def evidence(tabel_masukan, column, log_column=None, sd_ddof=0):
    """Hitung metrik dan SD error log dari prediksi OOF latihan yang tersimpan."""

    report_count = len(tabel_masukan)

    if not report_count:
        return dict(n=0, sigma=None, mae=None, rmse=None, r2=None, coverage=None)

    actual_hours = tabel_masukan.durasi_jam.to_numpy()
    predicted_hours = tabel_masukan[column].to_numpy()

    if log_column:
        predicted_log = tabel_masukan[log_column].to_numpy()
    else:
        predicted_log = np.log1p(predicted_hours)

    # Prediksi OOF dibuat saat baris itu mendapat giliran diperiksa dan tidak ikut training
    # model fold tersebut. Selisih aktual-prediksi log dipakai untuk SD rentang.
    # load_main_models mengirim sd_ddof=1, jadi pembaginya n-1.
    log_errors = np.log1p(actual_hours) - predicted_log
    log_error_sd = float(np.std(log_errors, ddof=sd_ddof))
    lower_hours = np.floor(
        np.maximum(np.expm1(predicted_log - INTERVAL_SD_MULTIPLIER * log_error_sd), 0)
        + 0.5
    )
    upper_hours = np.floor(
        np.maximum(np.expm1(predicted_log + INTERVAL_SD_MULTIPLIER * log_error_sd), 0)
        + 0.5
    )

    error = actual_hours - predicted_hours
    total_variation = np.sum((actual_hours - actual_hours.mean()) ** 2)

    return dict(
        n=report_count,
        sigma=log_error_sd,
        mae=float(np.abs(error).mean()),
        rmse=float(np.sqrt(np.mean(error**2))),
        r2=(
            float(1 - np.sum(error**2) / total_variation)
            if report_count > 1 and total_variation > 0
            else None
        ),
        coverage=float(
            np.mean((actual_hours >= lower_hours) & (actual_hours <= upper_hours)) * 100
        ),
    )


def prediction_interval(predicted_log, oof_metrics, waktu_masuk):
    """Ubah prediksi log menjadi batas bawah dan atas dalam jam."""

    # Cek apakah jumlah prediksi OOF cukup untuk menghitung SD. Angka 30 ini bukan jumlah
    # tetangga daun atau syarat 30 laporan per kategori.
    if (
        oof_metrics["n"] < 30
        or oof_metrics["sigma"] is None
    ):
        return None

    # Hitung jarak batas bawah/atas pada skala log terlebih dahulu.
    # Pakai SD OOF dari versi model yang sedang dipakai. Versi lengkap dan versi tanpa
    # rincian/unit bisa punya SD berbeda karena prediksinya juga berbeda.
    sigma = oof_metrics["sigma"]
    log_distance = INTERVAL_SD_MULTIPLIER * sigma
    lower_log = predicted_log - log_distance
    upper_log = predicted_log + log_distance

    # Kembalikan ke jam. Durasi tidak boleh negatif.
    lower_unrounded = max(np.expm1(lower_log), 0)
    upper_unrounded = max(np.expm1(upper_log), 0)

    # floor(x + 0.5) membulatkan ke jam utuh terdekat.
    lower_hours = float(np.floor(lower_unrounded + 0.5))
    upper_hours = float(np.floor(upper_unrounded + 0.5))

    # Tambahkan durasi bawah dan atas ke waktu laporan masuk supaya hasilnya bisa ditampilkan
    # sebagai tanggal selesai juga.
    lower_date = waktu_masuk + timedelta(hours=lower_hours)
    upper_date = waktu_masuk + timedelta(hours=upper_hours)

    return dict(
        lower=lower_hours,
        upper=upper_hours,
        lower_date=lower_date.isoformat(timespec="minutes"),
        upper_date=upper_date.isoformat(timespec="minutes"),
    )


def error_metrics(tabel_masukan):
    """Nilai prediksi uji tanpa menghitung SD uji untuk rentang."""

    actual = tabel_masukan.durasi_jam.to_numpy()
    errors = actual - tabel_masukan.prediksi_jam.to_numpy()
    total_variation = np.sum((actual - actual.mean()) ** 2)

    return dict(
        n=len(tabel_masukan),
        mae=float(np.abs(errors).mean()),
        rmse=float(np.sqrt(np.mean(errors**2))),
        r2=(
            float(1 - np.sum(errors**2) / total_variation)
            if total_variation > 0
            else None
        ),
        median_error=float(np.median(np.abs(errors))),
    )


class Engine:
    def __init__(self):
        """Baca model utama, data pendukung, dan tiga pembanding halaman analisis."""
        # Simpan model dan data di atribut self supaya bisa dipakai lagi saat ada request.
        # Persiapan ini dilakukan saat objek Engine dibuat.
        self.informasi_model_utama = {}
        self.main_models = {}
        self.analysis_models = {}
        self.daun_data_uji = {}
        # Baca data model, isi dropdown, load model ke RAM, lalu hitung daun data uji. Sesudah
        # startup selesai, klik pengguna tinggal memakai model yang sudah ada.
        self.load_main_models()
        self.prepare_form_options()
        self.preload_main_models()
        self.preload_analysis_models()
        self.prepare_neighbor_leaves()


    def load_main_models(self):
        """Daftarkan model akhir dan baca OOF latihan sebagai sumber SD rentang."""

        # Manifest mencatat file model, versi isian, dan pembagian datanya. Catatan ini
        # mengarahkan aplikasi ke hasil training yang dipasang.
        manifest = json.loads((MODEL_DIR / "manifest.json").read_text(encoding="utf-8"))

        if not manifest["ready"]:
            raise ValueError("Persiapan model akhir belum selesai.")

        # Hash seperti sidik jari isi file. Kalau model atau data tertukar/berubah, hentikan
        # proses supaya file dari percobaan berbeda tidak tercampur.
        for filename, expected_hash in manifest["hashes"].items():
            if (
                hashlib.sha256((MODEL_DIR / filename).read_bytes()).hexdigest()
                != expected_hash
            ):
                raise ValueError("Berkas model akhir berubah: " + filename)

        self.model_manifest = manifest
        self.data_latih_awal = read_csv(MODEL_DIR / "latih_awal.csv")
        self.data_latih_iqr = read_csv(MODEL_DIR / "latih.csv")
        self.data_uji_per_rangkaian = {}

        # Hitung batas IQR tiap kategori dari latihan awal saja. Uji memakai batas yang sama;
        # kuartilnya tidak dihitung ulang dari data uji.
        kuartil_kategori = (
            self.data_latih_awal.groupby("Kategori Laporan")
            .durasi_jam.quantile([0.25, 0.75])
            .unstack()
        )
        self.batas_iqr_per_kategori = kuartil_kategori[0.75] + 1.5 * (kuartil_kategori[0.75] - kuartil_kategori[0.25])
        first, third = self.data_latih_awal.durasi_jam.quantile([0.25, 0.75])
        self.batas_iqr_global = float(third + 1.5 * (third - first))

        data_latih_hasil_pemeriksaan = self.data_latih_awal.loc[
            self.data_latih_awal.durasi_jam.le(
                self.data_latih_awal["Kategori Laporan"].map(self.batas_iqr_per_kategori)
            )
        ]

        np.testing.assert_array_equal(
            data_latih_hasil_pemeriksaan.baris_excel_sumber, self.data_latih_iqr.baris_excel_sumber
        )
        assert len(self.data_latih_awal) == manifest["training_initial"]
        assert len(self.data_latih_iqr) == manifest["training_count"]

        # Baca OOF dan hasil uji untuk tiap versi isian. OOF dipakai untuk SD rentang,
        # sedangkan hasil uji dipakai untuk melihat error pada data yang tidak dilatih.
        for versi_isian in MODEL_PER_RANGKAIAN:
            folder = MODEL_DIR / versi_isian
            oof = read_csv(folder / "prediksi_OOF.csv")
            data_uji = read_csv(folder / "prediksi_uji.csv")
            assert len(oof) == manifest["training_initial"] and oof.baris_excel_sumber.is_unique

            # Cek nomor baris sumber supaya anggota latihan dan uji tidak tertukar. assert
            # berhenti dengan error kalau isi paketnya tidak cocok.
            assert set(oof.baris_excel_sumber) == set(self.data_latih_awal.baris_excel_sumber)
            assert len(data_uji) == manifest["test_count"] and data_uji.baris_excel_sumber.is_unique
            assert not set(oof.baris_excel_sumber) & set(data_uji.baris_excel_sumber)
            within = data_uji.durasi_jam.le(
                data_uji["Kategori Laporan"]
                .map(self.batas_iqr_per_kategori)
                .fillna(self.batas_iqr_global)
            )

            np.testing.assert_array_equal(within, data_uji.lolos_IQR_kategori)
            assert int(within.sum()) == manifest["retained_test_count"]
            self.data_uji_per_rangkaian[versi_isian] = data_uji

            # Versi sekarang memakai semua baris OOF untuk SD, termasuk yang lewat batas IQR
            # fold. Error data uji tidak dipakai untuk membuat rentang.
            calibration = evidence(oof, "prediksi_jam", "prediksi_log", sd_ddof=1)

            # Hitung dua hasil: uji lolos IQR dan seluruh uji. Hasil kedua menunjukkan
            # dampaknya kalau laporan berdurasi panjang tetap ikut dinilai.
            primary_metrics = error_metrics(data_uji.loc[within])
            all_metrics = error_metrics(data_uji)
            ringkasan_data_uji = []

            for label, code, result in [
                ("Seluruh uji", "seluruh", all_metrics),
                ("Uji lolos IQR kategori", "aktual_maks_IQR", primary_metrics),
            ]:
                ringkasan_data_uji.append(
                    dict(
                        label=label,
                        laporan_dinilai=code,
                        jumlah_dinilai=result["n"],
                        MAE_jam=result["mae"],
                        RMSE_jam=result["rmse"],
                        R2=result["r2"],
                        median_error_jam=result["median_error"],
                    )
                )

            self.informasi_model_utama[MODEL_PER_RANGKAIAN[versi_isian]] = dict(
                path=folder / "model.cbm",
                encoding=folder / "penyandi.joblib",
                algorithm="CatBoost",
                count=len(self.data_latih_iqr),
                evidence=calibration,
                evaluation=dict(
                    primary=primary_metrics,
                    all_test=all_metrics,
                    primary_scope="Uji lolos IQR kategori",
                    calibration_n=len(oof),
                ),
                evidence_iqr=primary_metrics,
                test_summary=ringkasan_data_uji,
                source=str(
                    Path(manifest["routes"][versi_isian]["model_source"])
                ),
            )

    def preload_main_models(self):
        """Muat empat versi masukan warga sekali saat Engine dibuat."""

        # Load empat CatBoost sekali ke main_models. Saat ada request, bundle() tinggal
        # mengambil objeknya dari RAM.
        for kunci_model in MODEL_PER_RANGKAIAN.values():
            self.main_models[kunci_model] = self.load_catboost_bundle(kunci_model)

    def preload_analysis_models(self):
        """Muat RF dan XGBoost untuk empat versi isian, tanpa melatih ulang."""

        from xgboost import XGBRegressor

        for versi_isian in MODEL_PER_RANGKAIAN:
            # CatBoost memakai objek yang sama dengan halaman warga.
            # CatBoost analisis memakai objek yang sama dengan halaman warga. Tambahkan empat
            # RF dan empat XGBoost, jadi total ada 12 model di RAM.
            models = {"CatBoost": self.main_models[MODEL_PER_RANGKAIAN[versi_isian]]}

            for algorithm in ["Random Forest", "XGBoost"]:
                # Nama folder mengikuti algoritma dan kelengkapan isian.
                folder_algoritma = algorithm.lower().replace(" ", "_")
                folder_isian = versi_isian
                folder = ANALYSIS_SOURCE / folder_algoritma / folder_isian
                record = json.loads(
                    (folder / "model_info.json").read_text(encoding="utf-8")
                )

                # Periksa bahwa berkas sama dengan model pada percobaan Bab 4.
                for filename, expected_hash in record["hashes"].items():
                    actual_hash = hashlib.sha256((folder / filename).read_bytes()).hexdigest()

                    if actual_hash != expected_hash:
                        raise ValueError("Berkas model analisis berubah: " + filename)

                if algorithm == "Random Forest":
                    model = joblib.load(folder / record["model_path"])
                else:
                    model = XGBRegressor()
                    model.load_model(str(folder / record["model_path"]))

                # Atur sekali saat startup; tidak mengubah model saat pengguna memprediksi.
                model.set_params(n_jobs=PREDICTION_THREADS)
                models[algorithm] = {
                    "model": model,
                    "encoding": joblib.load(folder / record["processor_path"]),
                    "algorithm": algorithm,
                }

            self.analysis_models[versi_isian] = models

    def predict_analysis(self, tabel_masukan, versi_isian):
        """Hitung tiga estimasi baru dari satu baris isian yang sudah diperiksa."""

        rows = []

        # Berikan isian yang sama ke ketiga model, masing-masing lewat alat encoding sendiri.
        # Kembalikan hasil log ke jam supaya kartunya bisa dibandingkan.
        for algorithm in ALGORITHMS:
            paket_model = self.analysis_models[versi_isian][algorithm]
            predicted_log = predict_model_log(tabel_masukan, paket_model)
            hours = float(max(np.expm1(predicted_log), 0))

            if not np.isfinite(hours):
                raise ValueError("Estimasi model analisis tidak valid.")

            rows.append({
                "name": paket_model["algorithm"],
                "estimate": hours,
                "selected": algorithm == "CatBoost",
            })

        return {
            "versi_isian": versi_isian,
            "variant": VARIANT_NAMES[versi_isian],
            "training_count": len(self.data_latih_iqr),
            "rows": rows,
        }

    def prepare_neighbor_leaves(self):
        """Simpan daun laporan uji lolos IQR untuk pembanding halaman analisis."""

        for versi_isian, kunci_model in MODEL_PER_RANGKAIAN.items():
            paket_model = self.main_models[kunci_model]
            data_uji = self.data_uji_per_rangkaian[versi_isian]
            data_uji = data_uji.loc[data_uji.lolos_IQR_kategori]
            input_data_uji = matrix(
                data_uji, paket_model["encoding"], "CatBoost"
            )
            # Catat nomor daun setiap laporan uji pada setiap pohon. Simpan hasilnya supaya
            # saat mencari 30 terdekat tidak perlu menghitung daun semua uji lagi.
            leaves = paket_model["model"].calc_leaf_indexes(
                input_data_uji, thread_count=PREDICTION_THREADS
            )

            # Kedalaman 8 menghasilkan nomor daun 0-255; satu byte sudah cukup.
            # Tetap periksa nilainya agar aman jika kelak model diganti.
            if leaves.max() < 256:
                leaves = leaves.astype(np.uint8)
            elif leaves.max() < 65536:
                leaves = leaves.astype(np.uint16)

            leaves.setflags(write=False)
            self.daun_data_uji[kunci_model] = leaves

    def input_frame(self, isian_laporan):
        """Periksa isian dan susun satu baris dengan nama kolom yang dipakai saat latihan."""

        if not isinstance(isian_laporan, dict):
            raise ValueError("Isi formulir tidak valid.")

        # Isian dari frontend masih dictionary. Cek isi dan pilihannya dulu, lalu susun
        # menjadi tabel satu baris untuk model.
        pilihan_formulir = self.options
        kolom_isian = [
            "kategori_laporan",
            "rincian_masalah",
            "kecamatan",
            "kelurahan",
            "kanal_aduan",
            "unit_penanganan",
            "waktu_masuk",
        ]

        for nama_kolom in kolom_isian:
            if (
                not isinstance(isian_laporan.get(nama_kolom, ""), str)
                or len(isian_laporan.get(nama_kolom, "")) > 2000
            ):
                raise ValueError("Isi kolom tidak valid: " + nama_kolom)

        # Buang spasi di awal/akhir teks. Kolom opsional yang tidak dikirim dibuat kosong
        # supaya bentuk isiannya tetap sama.
        isian = {
            nama_kolom: isian_laporan.get(nama_kolom, "").strip() for nama_kolom in kolom_isian
        }

        # Rincian dan unit boleh kosong. Daftar berikut berisi kolom yang tetap wajib diisi
        # pada keempat versi model.
        for nama_kolom in [
            "kategori_laporan",
            "kecamatan",
            "kelurahan",
            "kanal_aduan",
            "waktu_masuk",
        ]:
            if not isian[nama_kolom]:
                raise ValueError("Kolom wajib belum diisi: " + nama_kolom)

        if isian["kategori_laporan"] not in pilihan_formulir["kategori_laporan"]:
            raise ValueError("Pilih kategori dari daftar.")

        # Cek pasangan kecamatan-kelurahan juga, bukan hanya apakah nama kelurahannya ada di
        # daftar.
        if isian["kelurahan"] not in pilihan_formulir["kelurahan_per_kecamatan"].get(isian["kecamatan"], []):
            raise ValueError("Kelurahan tidak sesuai kecamatan.")

        if isian["kanal_aduan"] not in pilihan_formulir["kanal_aduan"]:
            raise ValueError("Pilih kanal dari daftar.")

        if isian["unit_penanganan"] and isian["unit_penanganan"] not in pilihan_formulir["unit_penanganan"]:
            raise ValueError("Pilih unit dari daftar, atau kosongkan.")

        try:
            waktu_masuk = datetime.fromisoformat(isian["waktu_masuk"])
        except ValueError:
            raise ValueError("Tanggal dan jam belum valid.")

        if waktu_masuk.tzinfo is not None or not 2000 <= waktu_masuk.year <= 2100:
            raise ValueError("Gunakan tanggal lokal Jakarta, tahun 2000-2100.")

        # Ini masih ubah nama teks, belum encoding angka. Misalnya Lain-lain pada Jalan
        # menjadi Lain-lain - Jalan, sama seperti waktu training. get mencari pasangan
        # kategori-rincian; kalau tidak ada, pakai teks aslinya.
        rincian_tersandi = self.peta_rincian.get(
            (isian["kategori_laporan"], isian["rincian_masalah"]), isian["rincian_masalah"]
        )
        # Rincian Masalah untuk model, rincian_asli untuk pilihan dan pembanding di aplikasi.
        # Jadi dua kolom ini tidak masuk sebagai dua fitur model. Dari tanggal, ambil jam,
        # hari (Senin=0), dan akhir pekan (Sabtu/Minggu=1).
        row = {
            "Kategori Laporan": isian["kategori_laporan"],
            "Rincian Masalah": rincian_tersandi,
            "rincian_asli": isian["rincian_masalah"],
            "Kecamatan": isian["kecamatan"],
            "Kelurahan": isian["kelurahan"],
            "Kanal_Aduan": isian["kanal_aduan"],
            "Unit Penanganan": isian["unit_penanganan"],
            "jam_masuk": waktu_masuk.hour,
            "hari_masuk": waktu_masuk.weekday(),
            "akhir_pekan": int(waktu_masuk.weekday() >= 5),
        }

        # Pilih versi sesuai kolom yang diisi. Model tanpa rincian/unit sudah dilatih sendiri,
        # jadi tidak perlu mengarang nilai untuk kolom yang kosong.
        if isian["rincian_masalah"] and isian["unit_penanganan"]:
            versi_isian = "lengkap"
        elif isian["rincian_masalah"]:
            versi_isian = "tanpa_unit"
        elif isian["unit_penanganan"]:
            versi_isian = "tanpa_rincian"
        else:
            versi_isian = "dasar"

        # Kembalikan empat hasil berurutan: tabel_masukan, versi_isian, waktu_masuk, dan
        # isian. Pemanggil bisa menampungnya ke empat variabel sekaligus.
        return (pd.DataFrame([row]), versi_isian, waktu_masuk, isian)

    def prepare_form_options(self):
        """Ambil pilihan formulir dari data latihan model utama saja."""
        data_latih = self.data_latih_awal
        # Buat pasangan nama asli dan nama untuk model dari latihan. Contoh: ('Jalan',
        # 'Lain-lain') menjadi 'Lain-lain - Jalan'.
        self.peta_rincian = {}
        
        for (kategori_laporan, raw), group in data_latih.groupby(["Kategori Laporan", "rincian_asli"]):
            nilai_rincian = group["Rincian Masalah"].unique()
            if len(nilai_rincian) != 1:
                raise ValueError("Encoding rincian tidak unik: " + kategori_laporan + " / " + raw)
            self.peta_rincian[kategori_laporan, raw] = str(nilai_rincian[0])

        # Dropdown tetap memakai nama rincian asli supaya pengguna cukup melihat Lain-lain.
        # Pilihannya diambil dari data latihan awal.
        self.options = build_form_options(data_latih, self.data_latih_iqr)

    def load_catboost_bundle(self, kunci_model):
        """Muat CatBoost dan encoding yang tersimpan saat latihan."""
        from catboost import CatBoostRegressor
        informasi_model = self.informasi_model_utama[kunci_model]
        model = CatBoostRegressor()
        # File .cbm berisi pohon CatBoost, .joblib berisi alat encoding. Pasang keduanya dari
        # hasil training yang sama.
        model.load_model(str(informasi_model["path"]))
        return dict(model=model, encoding=joblib.load(informasi_model["encoding"]), algorithm="CatBoost")

    def bundle(self, kunci_model):
        """Ambil model utama yang telah dimuat saat server menyala."""
        # Modelnya sudah ada di RAM sejak startup. Di sini tinggal ambil paket sesuai kunci,
        # tidak membaca atau melatih model lagi.
        return self.main_models[kunci_model]

    def resolve(self, isian_laporan, versi_isian, isian):
        """Pilih satu dari empat versi model utama menurut kolom yang diisi."""
        if (isian_laporan.get("mode", "model_utama") != "model_utama"
                or isian_laporan.get("sumber_model", "model_utama") != "model_utama"
                or isian_laporan.get("algorithm", "CatBoost") not in ("CatBoost", "auto")):
            raise ValueError("Pilihan model tidak tersedia. Gunakan model_utama / CatBoost.")
        if isian["rincian_masalah"] and isian["rincian_masalah"] not in self.options["rincian_per_kategori"].get(isian["kategori_laporan"], []):
            raise ValueError("Pilih rincian yang sesuai kategori laporan.")
        return MODEL_PER_RANGKAIAN[versi_isian], []

    def predict(self, isian_laporan):
        """Hitung estimasi warga dari model utama dan siapkan penjelasannya."""
        # Cek isian dan tentukan versinya dulu. Setelah itu ambil model, siapkan input, lalu
        # hitung prediksi.
        tabel_masukan, versi_isian, waktu_masuk, isian = self.input_frame(isian_laporan)
        kunci_model, warnings = self.resolve(isian_laporan, versi_isian, isian)
        informasi_model = self.informasi_model_utama[kunci_model]
        paket_model = self.bundle(kunci_model)
        predicted_log = predict_model_log(tabel_masukan, paket_model)
        hours = float(max(np.expm1(predicted_log), 0))
        if not np.isfinite(hours):
            raise ValueError("Model menghasilkan angka tidak valid untuk input ini.")

        # Rentang memakai SD error OOF versi ini. Bukan dari MAE uji atau 30 laporan mirip,
        # jadi pilihan sumber pembanding tidak mengubah rentang warga.
        oof_metrics = informasi_model["evidence"]
        interval = prediction_interval(predicted_log, oof_metrics, waktu_masuk)
        if interval is None:
            warnings.append("Prediksi OOF latihan belum cukup untuk menghitung rentang.")

        # Tandai nilai isian yang belum ada dalam latihan setelah IQR. Prediksi tetap jalan,
        # tetapi hasilnya diberi catatan untuk dibaca lebih hati-hati.
        data_latih = self.data_latih_iqr
        unseen = [column for column in paket_model["encoding"]["categorical_columns"]
                  if str(tabel_masukan.iloc[0][column]) not in set(data_latih[column].astype(str))]
        if (isian["rincian_masalah"] and "Rincian Masalah" not in paket_model["encoding"]["categorical_columns"]
                and not data_latih["Rincian Masalah"].eq(tabel_masukan.iloc[0]["Rincian Masalah"]).any()):
            unseen.append("Rincian Masalah (teks persis)")
        if unseen:
            warnings.append("Nilai belum pernah muncul dalam latihan model ini: " + ", ".join(unseen)
                            + ". Hasil perlu lebih hati-hati dibaca.")

        bound = float(self.batas_iqr_per_kategori.get(isian["kategori_laporan"], self.batas_iqr_global))
        return dict(
            ok=True, requested_mode="model_utama", model=kunci_model,
            used="Model utama - " + VARIANT_NAMES[versi_isian], algorithm="CatBoost",
            training_count=informasi_model["count"], estimate=hours,
            finish=(waktu_masuk + timedelta(hours=hours)).isoformat(timespec="minutes"),
            interval=interval, evidence=oof_metrics, evaluation=informasi_model["evaluation"],
            warnings=warnings, source=informasi_model["source"],
            iqr=dict(bound=bound, variant=VARIANT_NAMES[versi_isian], filter_type="kategori",
                     evidence_filtered=informasi_model["evidence_iqr"], test_summary=informasi_model["test_summary"]),
            features=tabel_masukan.drop(columns="rincian_asli").iloc[0].to_dict(),
            versi_isian=versi_isian, input=isian,
        )

