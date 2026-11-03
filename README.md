# KiraCRM

Website estimasi durasi pengaduan CRM Jakarta Selatan: https://kiracrm.online.
Backend: Flask dengan server production Waitress. Frontend: HTML, Tailwind CSS,
JavaScript, dan Plotly. Gunakan Python 3.12 seperti environment penelitian.

## Menjalankan aplikasi

Dari folder `demo_crm`:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python server.py
```

Buka http://127.0.0.1:8765/. Terminal tetap menyala sampai Ctrl+C ditekan.
Pada laptop penelitian, dari folder `.skripsi` gunakan:

```powershell
.venv_crm\Scripts\python.exe demo_crm\server.py
```

Server memakai Waitress, bukan server pengembangan Flask. Model dimuat sekali
saat startup. Tidak ada training ketika pengguna menghitung estimasi.
Port lain: `python server.py --port 8766`. Jumlah thread: `--threads 4`.

Waitress menggunakan satu proses dengan 4 thread secara default, agar model
tersimpan tidak diduplikasi dalam beberapa proses. Batas koneksi 100, body
permintaan 32.000 byte, dan header 16.384 byte. Traceback internal tidak ditampilkan
kepada pengunjung. Batas koneksi bukan pembatasan jumlah permintaan per pengguna.

## Cloudflare Tunnel

Route `kiracrm.online` tetap menuju `http://localhost:8765`.
Server mendengarkan pada `127.0.0.1`; HTTPS publik ditangani Cloudflare.
Jalankan aplikasi dan connector tunnel pada komputer yang sama.
Token tunnel disimpan di luar repository. Pembatasan permintaan publik dan
pemblokiran pemindaian bot dapat diatur melalui Cloudflare.

## Susunan folder

```text
demo_crm/
  server.py           # Flask, endpoint, dan startup Waitress
  engine.py           # Model, pengolahan input, estimasi, dan rentang
  presentation.py     # Laporan pembanding, SK, serta analisis
  requirements.txt    # Versi paket Python
  templates/          # HTML
  static/             # JavaScript, CSS, gambar, dan pustaka frontend
  models/             # Model, encoding, serta data pendukung aplikasi
  data/               # Pencocokan rincian dengan SK Sekda
  documents/          # Dua PDF SK Sekda
  tests/              # Tes aplikasi aktif
  package.json        # Perintah membangun CSS
  pnpm-lock.yaml      # Versi dependensi frontend
```

Folder aplikasi memakai path relatif dan dapat dipindahkan.
Model hanya dibuka dari file tepercaya yang sudah dipasang.
`model_info.json` mencatat model dan encoding pasangannya.
Model sebenarnya tersimpan sebagai `.cbm`, `.joblib`, atau `.ubj`.

## Model aplikasi

Warga memakai CatBoost dengan target log(1 + jam) dan IQR per kategori.
Halaman analisis juga menghitung prediksi Random Forest serta XGBoost.
Setiap algoritma memiliki 4 versi sesuai kelengkapan rincian dan unit.

- Pembagian acak 80/20 dari urutan Excel, seed 21; seed internal model/encoding/fold 42.
- Latihan awal 16.372 dan uji awal 4.094. Setelah IQR: latihan 14.746 dan uji 3.700.
- CatBoost lengkap pada uji lolos IQR: MAE 61,74 jam; RMSE 183,43 jam;
  R² 0,3677; median error 22,84 jam.
- Rentang berasal dari SD error log OOF latihan, bukan MAE atau 30 laporan terdekat.

Skor tersebut berlaku pada uji lolos IQR. Status lolos IQR memerlukan durasi
aktual, yang belum diketahui ketika warga mengisi laporan baru. Laporan baru
tetap dapat membutuhkan waktu lebih lama dari perkiraan.

## Pengujian

```powershell
python -m unittest discover -s tests -v
```

Tes memerlukan paket Python dan file model aplikasi yang disertakan.

## Mengubah tampilan

Class Tailwind ada di `templates/index.html`; aturan dasar ada di
`static/css/tailwind.css`. Node.js hanya diperlukan saat membangun CSS:

```powershell
pnpm install --frozen-lockfile
pnpm run build:css
```

CSS hasil build tetap disertakan di Git. `.gitignore` mengecualikan dependensi
lokal, cache Python, log, backup, environment lokal, dan file rahasia.
File model yang diperlukan aplikasi tetap disertakan.

## Alat penelitian di luar aplikasi

Notebook dan hasil eksperimen berada di luar `demo_crm`.
Alat pemasangan model terbaru: `../tools_crm/prepare_final_80_model.py` pada
workspace penelitian. Backup, launcher alternatif, installer lama, dan verifikasi
lama diarsipkan di `../arsip_demo_crm_20261103/`. Kedua folder tersebut tidak
diperlukan untuk menjalankan aplikasi yang modelnya sudah terpasang.

## Notebook penelitian

Dua notebook tersedia di [notebooks](notebooks/README.md): model utama dan pencarian hyperparameter. Kebutuhan data serta arsip eksperimennya dijelaskan di folder tersebut.
