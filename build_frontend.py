"""Siapkan halaman dan pilihan formulir untuk CDN Vercel."""

import csv
import json
from shutil import copy2, copytree

from form_options import MODEL_DIR, ROOT, build_form_options


def main():
    folder_public = ROOT / "public"
    folder_public.mkdir(exist_ok=True)

    with (MODEL_DIR / "latih_awal.csv").open(encoding="utf-8-sig", newline="") as file:
        data_latih = list(csv.DictReader(file))
    with (MODEL_DIR / "latih.csv").open(encoding="utf-8-sig", newline="") as file:
        kategori_dalam_latihan = {laporan["Kategori Laporan"] for laporan in csv.DictReader(file)}
    pilihan = build_form_options(data_latih, kategori_dalam_latihan)

    isi_json = json.dumps(pilihan, ensure_ascii=False, allow_nan=False, indent=2)
    (folder_public / "options.json").write_text(isi_json + "\n", encoding="utf-8", newline="\n")

    # Sumber HTML tetap satu untuk Waitress dan Vercel.
    copy2(ROOT / "templates" / "index.html", folder_public / "index.html")
    copytree(ROOT / "static", folder_public / "static", dirs_exist_ok=True)
    print("Halaman, pilihan formulir, dan aset siap di folder public/.")


if __name__ == "__main__":
    main()
