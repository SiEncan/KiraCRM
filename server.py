"""Aplikasi Flask untuk membuka formulir dan menjalankan model CRM tersimpan.

Jalankan dari terminal: python server.py
Server tetap hidup di terminal sampai Anda menekan Ctrl+C.
"""

import argparse
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge
from threadpoolctl import threadpool_limits
from waitress import serve

from engine import Engine
from presentation import Presentation

BASE_FOLDER = Path(__file__).resolve().parent
DOCUMENT_FOLDER = BASE_FOLDER / "documents"
APP_ID = "crm-local-demo-20261013"
DEFAULT_PORT = 8765

MAX_INPUT_BYTES = 32_000

# Pesan untuk pengguna dipisahkan dari rincian error yang dicatat di terminal.
INVALID_FORM_MESSAGE = "Isian belum berhasil diproses. Silakan muat ulang halaman dan coba kembali."
FORM_FIELD_LABELS = {
    "kategori_laporan": "kategori laporan",
    "rincian_masalah": "rincian masalah",
    "kecamatan": "kecamatan",
    "kelurahan": "kelurahan",
    "kanal_aduan": "kanal aduan",
    "unit_penanganan": "unit penanganan",
    "waktu_masuk": "tanggal dan jam laporan masuk",
}


def user_error_message(error):
    """Tampilkan petunjuk isian yang dikenal; error internal tidak diteruskan ke warga."""

    message = str(error)
    prefix, _, field = message.partition(": ")

    if field in FORM_FIELD_LABELS:
        label = FORM_FIELD_LABELS[field]
        if prefix == "Kolom wajib belum diisi":
            return ("Silakan isi " if field == "waktu_masuk" else "Silakan pilih ") + label + "."
        if prefix == "Isi kolom tidak valid":
            return "Periksa kembali isian " + label + "."

    input_messages = {
        "Pilih kategori dari daftar.": "Pilih kategori dari daftar.",
        "Kelurahan tidak sesuai kecamatan.": "Pilih kelurahan sesuai kecamatan yang dipilih.",
        "Pilih kanal dari daftar.": "Pilih kanal dari daftar.",
        "Pilih unit dari daftar, atau kosongkan.": "Pilih unit dari daftar, atau kosongkan.",
        "Tanggal dan jam belum valid.": "Periksa kembali tanggal dan jam laporan masuk.",
        "Gunakan tanggal lokal Jakarta, tahun 2000-2100.": "Gunakan tanggal dan jam dalam WIB, dengan tahun antara 2000 dan 2100.",
        "Pilih rincian yang sesuai kategori laporan.": "Pilih rincian yang sesuai kategori laporan.",
        "Model menghasilkan angka tidak valid untuk input ini.": "Perkiraan belum berhasil dihitung. Silakan coba kembali.",
        "Estimasi model analisis tidak valid.": "Laporan pembanding belum dapat ditampilkan.",
    }

    return input_messages.get(message, INVALID_FORM_MESSAGE)

# Hanya dua PDF ini yang boleh dibaca melalui alamat /documents/.
DOCUMENT_FILES = {
    "sk-99-2022.pdf": "SK_Sekda_99_Tahun_2022_CRM.pdf",
    "sk-175-2025.pdf": "SK_Sekda_175_Tahun_2025_CRM.pdf",
}


# Model dan aplikasi disiapkan saat server nyala. Endpoint di bawah baru jalan setelah ada
# request dari browser.
def create_app(prediction_engine=None, display_service=None, port=DEFAULT_PORT):
    """Siapkan Flask, model, dan alamat layanan aplikasi.

    Engine memuat tiga algoritma untuk empat versi isian saat server dimulai.
    Daun laporan uji lolos IQR disiapkan agar pencarian 30 laporan mirip cepat.
    Dua parameter pertama juga memudahkan pengujian dengan model pengganti.
    """

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_INPUT_BYTES
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    # Kalau create_app() tidak diberi Engine, buat objeknya di sini. Waktu tes, objeknya bisa
    # dikirim dari luar jadi tidak perlu load model lagi.
    if prediction_engine is None:
        prediction_engine = Engine()

    # Engine yang sama dikirim ke Presentation. Di dalam __init__, objek ini disimpan sebagai
    # self.engine.
    if display_service is None:
        display_service = Presentation(prediction_engine)

    # Setiap permintaan mempunyai form_data dan hasilnya sendiri.
    # Prediksi tidak dikunci bersama; pengguna lain dapat menghitung bersamaan.

    @app.before_request
    def check_local_request():
        """Izinkan alamat lokal/hosting; permintaan browser tetap dari host yang sama."""
        if request.method == "POST":
            # Cek asal request sebelum menerima isian. Alamat lokal atau hosting boleh,
            # asalkan request browser datang dari alamat aplikasi yang sama.
            origin = request.headers.get("Origin")

            if origin is not None and (
                urlsplit(origin).scheme not in ("http", "https")
                or urlsplit(origin).netloc != request.host
            ):
                return (
                    jsonify(error="Muat ulang halaman aplikasi, lalu coba kembali."),
                    403,
                )

    @app.after_request
    def add_response_headers(response):
        """Minta browser memuat berkas terbaru dan memakai sumber lokal."""

        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; "
            "frame-ancestors 'none'; base-uri 'none'"
        )

        return response

    def read_form_data():
        """Baca objek JSON yang dikirim oleh JavaScript dari formulir."""

        # Isian dari JavaScript dikirim sebagai JSON. Cek dulu bentuk datanya supaya input
        # yang salah tidak langsung masuk ke fungsi model.
        if not request.is_json:
            return None, (jsonify(error=INVALID_FORM_MESSAGE), 415)

        if request.content_length is None or request.content_length == 0:
            return None, (jsonify(error=INVALID_FORM_MESSAGE), 400)

        try:
            form_data = request.get_json()
        except BadRequest:
            return None, (jsonify(error=INVALID_FORM_MESSAGE), 400)

        if not isinstance(form_data, dict):
            return None, (jsonify(error=INVALID_FORM_MESSAGE), 400)

        return form_data, None

    def process_form(action):
        """Jalankan satu tindakan model dan kembalikan hasilnya sebagai JSON."""

        # action berisi fungsi yang dikirim endpoint, misalnya engine.predict. Dengan cara
        # ini, bagian baca isian dan tangani error tidak perlu ditulis berulang.
        form_data, input_error = read_form_data()

        if input_error is not None:
            return input_error

        try:
            # Jalankan fungsi dari endpoint dengan isian pengguna, lalu kirim hasilnya ke
            # browser sebagai JSON.
            result = action(form_data)

            return jsonify(result)
        except (ValueError, TypeError, OverflowError) as error:
            app.logger.warning("Permintaan gagal diproses: %s", error)
            return jsonify(error=user_error_message(error)), 400
        except Exception:
            # Rincian kesalahan muncul di terminal, bukan di halaman warga.
            app.logger.exception("Model gagal memproses permintaan.")

            return (
                jsonify(
                    error="Perkiraan belum berhasil dihitung. Silakan coba kembali."
                ),
                500,
            )

    @app.get("/")
    def home():
        """Tampilkan halaman HTML dari folder templates."""

        return render_template("index.html")

    @app.get("/api/health")
    def health():
        """Dipakai pembuka demo untuk memeriksa apakah server sudah siap."""

        return jsonify(app=APP_ID, ready=True)

    # Saat halaman dibuka, JavaScript mengambil pilihan dropdown lewat sini. Daftarnya sudah
    # dibuat dari data latih saat server nyala.
    @app.get("/api/options")
    def form_options():
        """Kirim daftar kategori, rincian, lokasi, kanal, dan unit."""

        return jsonify(prediction_engine.options)

    # Klik hitung masuk ke sini dulu untuk mendapatkan estimasi CatBoost dan rentang dari
    # error OOF.
    @app.post("/api/predict")
    def predict():
        """Hitung estimasi dari satu pilihan model."""

        return process_form(prediction_engine.predict)

    # Setelah estimasi muncul, ambil riwayat, SK, metrik, dan data grafik lewat sini. Estimasi
    # untuk kartu tiga model juga dihitung di sini.
    @app.post("/api/context")
    def report_context():
        """Ambil pembanding historis, acuan SK, grafik, dan metrik."""

        return process_form(display_service.describe)

    # Uji/Latihan/Keduanya mengambil pembanding lewat endpoint ini. Estimasi dan rentang warga
    # tetap sama saat sumber diganti.
    @app.post("/api/analysis")
    def analysis_source():
        """Ubah sumber pembanding peneliti tanpa menghitung ulang estimasi warga."""

        return process_form(display_service.analysis)

    @app.get("/documents/<filename>")
    def reference_document(filename):
        """Buka salah satu dari dua PDF SK yang sudah ditentukan."""

        # Cocokkan nama di URL dengan dua PDF yang tersedia. Nama lain ditolak supaya URL ini
        # tidak bisa membuka file lain di komputer.
        source_name = DOCUMENT_FILES.get(filename)

        if source_name is None:
            return jsonify(error="Tidak ditemukan."), 404

        document_path = DOCUMENT_FOLDER / source_name

        if not document_path.is_file():
            return jsonify(error="PDF sumber tidak tersedia."), 404

        return send_file(document_path, mimetype="application/pdf")

    @app.errorhandler(404)
    def page_not_found(error):
        return jsonify(error="Tidak ditemukan."), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify(error="Metode permintaan tidak diizinkan."), 405

    @app.errorhandler(RequestEntityTooLarge)
    def input_too_large(error):
        return jsonify(error="Isian terlalu panjang. Silakan periksa kembali formulir."), 413

    return app


def main(open_browser=False):
    """Jalankan Flask melalui Waitress. Model tidak dilatih ulang saat server dimulai."""

    parser = argparse.ArgumentParser(description="Aplikasi estimasi CRM dengan Flask.")

    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--no-browser", action="store_true")
    arguments = parser.parse_args()

    if not 1 <= arguments.threads <= 16:
        parser.error("Jumlah threads harus antara 1 dan 16.")

    print("Memuat tiga algoritma untuk empat versi isian dan menyiapkan daun laporan uji...", flush=True)
    # Engine dan Presentation dibuat dari sini. Flask baru menerima request setelah semua
    # model siap.
    app = create_app(port=arguments.port)
    address = f"http://127.0.0.1:{arguments.port}"

    print(f"KiraCRM berjalan pada {address}", flush=True)

    if open_browser and not arguments.no_browser:
        threading.Timer(1, webbrowser.open, args=[address]).start()

    # Waitress memakai satu proses supaya model tidak diduplikasi di RAM.
    with threadpool_limits(limits=4):
        serve(
            app,
            host="127.0.0.1",
            port=arguments.port,
            threads=arguments.threads,
            connection_limit=100,
            channel_timeout=30,
            max_request_body_size=MAX_INPUT_BYTES,
            max_request_header_size=16_384,
            expose_tracebacks=False,
        )

if __name__ == "__main__":
    main()