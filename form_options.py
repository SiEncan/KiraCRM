"""Daftar pilihan formulir dari data latih paket model."""

from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models/catboost_global_log_iqr_kategori"


def build_form_options(data_latih, kategori_dalam_latihan):
    rincian_per_kategori = defaultdict(set)
    unit_per_kategori = defaultdict(set)
    kelurahan_per_kecamatan = defaultdict(set)
    kanal_aduan = set()
    unit_penanganan = set()

    for laporan in data_latih:
        kategori = laporan["Kategori Laporan"]
        rincian_per_kategori[kategori].add(laporan["rincian_asli"])
        unit_per_kategori[kategori].add(laporan["Unit Penanganan"])
        kelurahan_per_kecamatan[laporan["Kecamatan"]].add(laporan["Kelurahan"])
        kanal_aduan.add(laporan["Kanal_Aduan"])
        unit_penanganan.add(laporan["Unit Penanganan"])

    jumlah_latih = format(len(data_latih), ",d").replace(",", ".")
    return dict(
        kategori_laporan=sorted(rincian_per_kategori),
        rincian_per_kategori={
            kategori: sorted(rincian_per_kategori[kategori])
            for kategori in sorted(rincian_per_kategori)
        },
        kelurahan_per_kecamatan={
            kecamatan: sorted(kelurahan_per_kecamatan[kecamatan])
            for kecamatan in sorted(kelurahan_per_kecamatan)
        },
        kanal_aduan=sorted(kanal_aduan),
        unit_penanganan=sorted(unit_penanganan),
        unit_per_kategori={
            kategori: sorted(unit_per_kategori[kategori])
            for kategori in sorted(unit_per_kategori)
        },
        source=(
            f"Pilihan diambil dari {jumlah_latih} laporan latihan acak 80%. "
            "Pilihan tidak dipelajari dari 20% uji."
        ),
        kategori_dalam_latihan=sorted(set(kategori_dalam_latihan)),
    )
