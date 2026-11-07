"""Siapkan halaman dan pilihan formulir untuk CDN Vercel."""

import json
from shutil import copytree

from flask import Flask, render_template

from engine import MODEL_DIR, ROOT, build_form_options, read_csv


def main():
    folder_public = ROOT / "public"

    data_latih = read_csv(MODEL_DIR / "latih_awal.csv")
    data_latih_iqr = read_csv(MODEL_DIR / "latih.csv")
    pilihan = build_form_options(data_latih, data_latih_iqr)

    isi_json = json.dumps(pilihan, ensure_ascii=False, allow_nan=False, indent=2)
    (folder_public / "options.json").write_text(isi_json + "\n", encoding="utf-8", newline="\n")

    # Pakai template yang sama dengan Waitress. Flask ini hanya untuk render HTML saat build.
    app = Flask(__name__)
    with app.test_request_context("/"):
        halaman = render_template("index.html")
    (folder_public / "index.html").write_text(halaman + "\n", encoding="utf-8", newline="\n")

    copytree(ROOT / "static", folder_public / "static", dirs_exist_ok=True)
    print("Halaman, pilihan formulir, dan aset siap di folder public/.")


if __name__ == "__main__":
    main()
