import {
  getElement,
  formatNumber,
  formatCount,
  formatDate,
  createElement,
  formatRangeDays,
  currentJakartaTime,
  postJSON,
} from "./helpers.js";
import {
  renderHistoryChart,
  setupScatterZoom,
} from "./charts.js";
import { setupSearchSelect } from "./search-select.js";
import { defaultTestAnalysis, renderAnalysisPanels } from "./analysis-sources.js";

// Urutan alur: initializePage -> isian formulir -> calculateEstimate -> renderPredictionResult.

// Satu tempat untuk menyimpan pilihan, hasil, dan status halaman.
// Simpan hasil terakhir dan pilihan sumber di tab ini. Saat pindah tampilan, hasilnya bisa
// langsung dipakai lagi. Hanya data sumber yang sedang ditampilkan yang disimpan.
const appState = {
  options: null,
  view: "citizen",
  busy: false,
  predictionResult: null,
  context: null,
  isianLaporan: null,
  analysisSource: "test",
  analysisData: null,
  analysisRequest: 0,
};

// Simpan fungsi dropdown rincian dan unit agar dapat disinkronkan/reset.
// Map ini menyimpan fungsi sync/close milik dropdown rincian dan unit. Saat Reset atau
// pilihan berubah, kotak pencariannya bisa disamakan dengan select asli.
const searchControls = new Map();

const kolomFormulir = [
  "kategori_laporan",
  "rincian_masalah",
  "kecamatan",
  "kelurahan",
  "kanal_aduan",
  "waktu_masuk",
  "unit_penanganan",
];

// Baca semua kolom formulir sebagai satu objek untuk dikirim ke Flask.
// Nama properti harus cocok dengan input_frame() di engine.py. Di sini masih teks formulir;
// encoding dan prediksi dikerjakan backend.
function bacaIsianFormulir() {
  const isianFormulir = {};

  for (const namaKolom of kolomFormulir) {
    // Nama kolom ini juga menjadi id elemen HTML dan nama isian untuk Python.
    isianFormulir[namaKolom] = getElement(namaKolom).value;
  }

  // Model warga tetap sama. Kolom kosong menentukan versi masukan secara otomatis.
  isianFormulir.mode = "model_utama";
  isianFormulir.sumber_model = "model_utama";
  isianFormulir.algorithm = "CatBoost";

  return isianFormulir;
}

// Isi pilihan select dan sinkronkan kotak pencariannya.
function fillSelect(id, values, blank) {
  const select = getElement(id);
  select.replaceChildren(new Option(blank, ""));

  for (const value of values) {
    select.add(new Option(value, value));
  }
  searchControls.get(id)?.sync();
}

// Tampilkan teks rincian terpilih agar kalimat panjang tetap dapat dibaca.
function perbaruiKeteranganRincian() {
  getElement("keteranganRincianTerpilih").textContent = getElement("rincian_masalah").value;
  getElement("keteranganRincianTerpilih").hidden = !getElement("rincian_masalah").value;
}

// Sesuaikan daftar rincian dengan kategori laporan yang dipilih.
function perbaruiPilihanRincian() {
  fillSelect(
    "rincian_masalah",
    appState.options.rincian_per_kategori[getElement("kategori_laporan").value] || [],
    "Belum diketahui",
  );

  // Rincian mengikuti kategori, sedangkan unit memakai daftar unit yang tersedia. Pertahankan
  // unit sebelumnya kalau pilihannya masih ada.
  const unitPenanganan = getElement("unit_penanganan").value;
  fillSelect("unit_penanganan", appState.options.unit_penanganan, "Belum diketahui");

  if (appState.options.unit_penanganan.includes(unitPenanganan)) {
    getElement("unit_penanganan").value = unitPenanganan;
  }
  searchControls.get("unit_penanganan")?.sync();
}

// Sesuaikan kelurahan dengan kecamatan yang dipilih.
function perbaruiPilihanKelurahan() {
  fillSelect(
    "kelurahan",
    appState.options.kelurahan_per_kecamatan[getElement("kecamatan").value] || [],
    "Pilih kelurahan",
  );
}


// Kosongkan pembanding lama saat isian belum dihitung ulang.
function clearContextDisplay() {
  appState.analysisData = null;
  // Naikkan nomor request supaya jawaban analisis yang datang terlambat tidak muncul lagi
  // setelah isian diganti atau di-reset.
  appState.analysisRequest++;
  getElement("analysisLoadStatus").textContent = "";
  getElement("historyResult").hidden = true;
  getElement("historyEmpty").hidden = false;
  getElement("historyEmpty").textContent =
    "Setelah estimasi dihitung, lihat rentang waktu yang biasa tercatat pada laporan sejenis.";
  getElement("historyCount").textContent = "Laporan terdahulu";

  getElement("skResult").hidden = true;
  getElement("skEmpty").hidden = false;
  getElement("skEmpty").textContent =
    "Pilih rincian masalah untuk melihat acuan waktu pada SK Sekda.";

  getElement("researchDashboard").hidden = true;
}

// Tandai hasil lama tidak berlaku setelah pengguna mengubah isian.
function markResultsOutdated() {
  // Isian berubah berarti hasil lama sudah tidak cocok. Kosongkan hasil tersimpan dan
  // sembunyikan panel sampai dihitung lagi.
  appState.predictionResult = null;
  appState.context = null;
  appState.isianLaporan = null;

  getElement("result").hidden = true;
  getElement("empty").hidden = false;
  getElement("resultState").textContent = "Belum dihitung";
  getElement("error").hidden = true;

  clearContextDisplay();
  getElement("status").textContent =
    "Isian berubah. Hitung kembali untuk memperbarui hasil.";
}

// Pindahkan formulir yang sama ke halaman warga atau analisis.
function switchPage() {
  // #analisis dan #estimasi memilih tampilan di halaman yang sama. Pindah halaman tidak
  // membuat form atau memuat model baru.
  const research = location.hash === "#analisis";

  if (appState.busy) {
    appState.pendingView = true;
    return;
  }

  appState.view = research ? "research" : "citizen";
  document.body.dataset.view = appState.view;
  getElement("citizenView").hidden = research;
  getElement("researchView").hidden = !research;

  // Formulir tetap sama; isi panel hasil menyesuaikan warga atau peneliti.
  // append memindahkan form dan panel hasil yang sudah ada. Karena formnya tetap satu, isi
  // kolom tidak hilang saat pindah tampilan.
  const formHost = research ? "researchFormHost" : "citizenFormHost";
  const resultHost = research ? "researchResultHost" : "citizenResultHost";
  getElement(formHost).append(getElement("form"));
  getElement(resultHost).append(getElement("resultPanel"));

  for (const [id, active] of [
    ["navCitizen", !research],
    ["navResearch", research],
  ]) {
    if (active) {
      getElement(id).setAttribute("aria-current", "page");
    } else {
      getElement(id).removeAttribute("aria-current");
    }
  }

  getElement("pageEyebrow").textContent = research
    ? "HALAMAN PENDUKUNG PENELITIAN"
    : "INFORMASI WAKTU PENANGANAN";

  if (research) {
    getElement("pageTitle").replaceChildren(
      document.createTextNode("Analisis dan Perbandingan"),
      createElement("br"),
      document.createTextNode("Kinerja Model."),
    );
  } else {
    getElement("pageTitle").replaceChildren(
      document.createTextNode("Setiap laporan punya"),
      createElement("br"),
      document.createTextNode("waktu penanganan."),
    );
  }

  getElement("pageDescription").textContent = research
    ? "Bandingkan estimasi CatBoost, Random Forest, dan XGBoost untuk isian Anda, lalu lihat hasil pengujiannya."
    : "Dapatkan perkiraan penyelesaian berdasarkan karakteristik laporan Anda dan pola laporan sebelumnya.";

  getElement("formTitle").textContent = research
    ? "Karakteristik laporan yang dianalisis"
    : "Ceritakan jenis laporannya";
  getElement("submitLabel").textContent = research
    ? "Hitung analisis"
    : "Lihat perkiraan waktu";
  document.title =
    "KiraCRM | " + (research ? "Analisis model" : "Estimasi laporan");

  if (research && appState.context) {
    renderResearchDashboard(appState.context);
    loadAnalysisSource();
  }
}

// Isi contoh laporan listrik. Fungsi ini belum menjalankan prediksi.
function fillExample() {
  if (!appState.options) {
    return;
  }
  getElement("kategori_laporan").value = "Jaringan Listrik";
  perbaruiPilihanRincian();
  getElement("rincian_masalah").value =
    ("Kabel/jaringan utilitas semerawut antar tiang PJU dan/atau kabel utilitas " +
      "putus yang mengganggu pengguna jalan");

  getElement("kecamatan").value = "JAGAKARSA";
  perbaruiPilihanKelurahan();
  getElement("kelurahan").value = "SRENGSENG SAWAH";
  getElement("kanal_aduan").value = "JAKI";

  getElement("waktu_masuk").value = "2026-10-06T17:07";
  getElement("unit_penanganan").value = "DINAS BINA MARGA";

  for (const control of searchControls.values()) {
    control.sync();
  }
  markResultsOutdated();
  getElement("status").textContent =
    "Contoh listrik terisi. Anda dapat mengubahnya sebelum menghitung.";
}

// Kembalikan formulir ke keadaan awal.
function resetForm() {
  if (!appState.options) {
    return;
  }
  // Reset form belum cukup untuk kotak pencarian tambahan. Isi ulang pilihan, samakan
  // tampilan dropdown, lalu kosongkan hasil lama.
  getElement("form").reset();
  appState.analysisSource = "test";
  getElement("analysisSourceTest").checked = true;
  fillSelect("kategori_laporan", appState.options.kategori_laporan, "Pilih kategori");
  fillSelect("kanal_aduan", appState.options.kanal_aduan, "Pilih kanal");

  fillSelect("kecamatan", Object.keys(appState.options.kelurahan_per_kecamatan), "Pilih kecamatan");
  perbaruiPilihanRincian();
  perbaruiPilihanKelurahan();
  getElement("waktu_masuk").value = currentJakartaTime();

  markResultsOutdated();
  getElement("status").textContent = "Isian direset. Silakan isi laporan baru.";
}

// Nonaktifkan tombol sementara selama permintaan ke server berjalan.
function setBusy(value) {
  // Status ini hanya berlaku pada tab pengguna ini; backend melayani permintaan bersamaan.
  appState.busy = value;
  getElement("fields").disabled = value;

  if (value) {
    getElement("submitLabel").textContent = "Menghitung...";
  } else {
    getElement("submitLabel").textContent = appState.view === "research"
      ? "Hitung analisis"
      : "Lihat perkiraan waktu";
  }
}

// Isi panel estimasi, rentang, metrik, dan keterangan dari jawaban Flask.
function renderPredictionResult(predictionResult) {
  // 1. Simpan jawaban server dan siapkan panel hasil.
  // predictionResult adalah jawaban /api/predict. Jam dan rentangnya sudah dihitung backend, jadi
  // frontend tinggal menampilkan tanpa membuat rentang baru dari MAE.
  const evaluation = predictionResult.evaluation.primary;
  appState.predictionResult = predictionResult;
  getElement("empty").hidden = true;
  getElement("result").hidden = false;

  getElement("resultTitle").textContent = "Perkiraan untuk laporan ini";
  getElement("resultState").textContent = "Selesai dihitung";
  // 2. Isi rentang, estimasi jam, dan perkiraan tanggal selesai.
  getElement("range").textContent = predictionResult.interval
    ? formatCount(predictionResult.interval.lower) +
      " - " +
      formatCount(predictionResult.interval.upper) +
      " jam"
    : "Belum cukup data";
  getElement("rangeDays").textContent = formatRangeDays(predictionResult.interval);

  getElement("rangeDays").hidden = !predictionResult.interval;
  getElement("rangeDates").textContent = predictionResult.interval
    ? formatDate(predictionResult.interval.lower_date) +
      " sampai " +
      formatDate(predictionResult.interval.upper_date)
    : "Estimasi titik tersedia, tetapi prediksi OOF latihan belum cukup untuk menampilkan rentang.";
  getElement("estimate").textContent = formatNumber(predictionResult.estimate) + " jam";
  getElement("estimateDays").textContent = predictionResult.estimate < 24
    ? "Kurang dari 1 hari"
    : "Sekitar " + formatCount(predictionResult.estimate / 24) + " hari";

  getElement("finish").textContent =
    "Perkiraan selesai: " + formatDate(predictionResult.finish);
  getElement("used").textContent = predictionResult.used + " / " + predictionResult.algorithm;

  // Angka, keterangan hari, dan susunan hasil sama pada halaman warga dan analisis.
  getElement("citizenEstimate").textContent = getElement("estimate").textContent;
  getElement("citizenEstimateDays").textContent = predictionResult.estimate < 24
    ? "Kurang dari 1 hari"
    : getElement("estimateDays").textContent;
  getElement("citizenFinish").textContent =
    "Perkiraan selesai: " + formatDate(predictionResult.finish);
  getElement("citizenRange").textContent = getElement("range").textContent;
  getElement("citizenRangeDays").textContent = getElement("rangeDays").textContent;
  getElement("citizenRangeDays").hidden = !predictionResult.interval;
  getElement("citizenRangeDates").textContent = predictionResult.interval
    ? getElement("rangeDates").textContent
    : "Belum cukup data untuk menghitung rentang waktunya.";

  // 3. Tampilkan sumber latihan dan sumber error untuk rentang.
  getElement("trainCount").textContent = formatCount(predictionResult.training_count);
  getElement("oofCount").textContent = formatCount(predictionResult.evidence.n);
  getElement("intervalSourceLabel").textContent = "Prediksi OOF latihan";

  // 4. Tampilkan catatan yang sesuai dengan model dan nilai masukan.
  const unseen = predictionResult.warnings.find((warning) =>
    warning.startsWith("Nilai belum pernah"),
  );

  const limitation = "Gunakan hasil ini sebagai gambaran waktu. Penyelesaian sebenarnya dapat " +
    "lebih cepat atau lebih lama, sesuai kondisi penanganan laporan.";
  getElement("citizenWarning").textContent =
    limitation +
    (unseen
      ? " Beberapa isian belum tercatat pada data sebelumnya, sehingga perkiraannya perlu dibaca lebih hati-hati."
      : "");
  getElement("citizenWarning").classList.toggle("caution", Boolean(unseen));
  // 5. Isi daftar metrik. Angka ini dikirim server dari hasil pengujian tersimpan.
  getElement("metrics").replaceChildren();

  for (const [name, value] of [
    ["MAE uji lolos IQR", formatNumber(evaluation.mae) + " jam"],
    ["RMSE uji lolos IQR", formatNumber(evaluation.rmse) + " jam"],
    ["R² uji lolos IQR", formatNumber(evaluation.r2, 4)],
    [
      "SD error log OOF",
      formatNumber(predictionResult.evidence.sigma, 4),
    ],
    [
      "Aktual dalam rentang (OOF latihan)",
      predictionResult.interval
        ? formatNumber(predictionResult.evidence.coverage, 1) + "%"
        : "Belum tersedia",
    ],
  ]) {
    getElement("metrics").append(createElement("dt", name), createElement("dd", value));
  }
  // 6. Perlihatkan kembali masukan yang diterima backend.
  getElement("features").replaceChildren();

  for (const [name, value] of Object.entries(predictionResult.features)) {
    const row = createElement(
      "div",
      null,
      ("feature grid grid-cols-[115px_1fr] gap-3 border-b border-line py-2 " +
        "text-[11px] [&>span:first-child]:text-muted " +
        "[&>span:last-child]:wrap-anywhere"),
    );
    row.append(
      createElement("span", name),
      createElement("span", value === "" ? "Tidak digunakan" : String(value)),
    );
    getElement("features").append(row);
  }
  getElement("source").textContent = "Sumber model: " + predictionResult.source;

  getElement("iqrEvaluation").replaceChildren();

  if (predictionResult.iqr) {
    getElement("iqrEvaluation").append(createElement("h3", "Hasil uji snapshot ini"));

    const table = createElement("table");
    const head = createElement("thead");
    const tr = createElement("tr");
    ["Cakupan uji", "Jumlah", "MAE jam", "RMSE jam", "R²"].forEach((t) =>
      tr.append(createElement("th", t)),
    );
    head.append(tr);
    table.append(head);

    const body = createElement("tbody");

    for (const row of predictionResult.iqr.test_summary) {
      const tr = createElement("tr");
      [
        row.label || row.laporan_dinilai,
        formatCount(+row.jumlah_dinilai),
        formatNumber(+row.MAE_jam),
        formatNumber(+row.RMSE_jam),
        formatNumber(+row.R2, 4),
      ].forEach((t) => tr.append(createElement("td", t)));
      body.append(tr);
    }
    table.append(body);

    const scroll = createElement(
      "div",
      null,
      "table-scroll mt-4 overflow-x-auto overscroll-x-contain",
    );
    scroll.append(table);
    getElement("iqrEvaluation").append(scroll);
  }
}


// Tampilkan pembanding historis hanya jika jumlah datanya cukup.
function renderHistory(context, predictionResult) {
  const history = context.history;
  getElement("historyEmpty").hidden = history.available;
  getElement("historyResult").hidden = !history.available;
  getElement("historyCount").textContent = formatCount(history.n) + " laporan";

  if (!history.available) {
    getElement("historyEmpty").textContent = history.note;

    return;
  }
  renderHistoryChart(history, predictionResult);
  // Pecahan jam hanya disembunyikan pada tulisan warga; data dan grafik tetap memakai angka asli.
  getElement("historySentence").textContent =
    "Sebagai gambaran, separuh dari " +
    formatCount(history.n) +
    " laporan terdahulu selesai dalam " +
    formatCount(Math.floor(history.q1)) +
    " sampai " +
    formatCount(Math.floor(history.q3)) +
    " jam.";
  getElement("historyNote").textContent =
    history.note +
    (history.limited
      ? " Laporan pembanding masih terbatas."
      : "");
}

function bandText(b) {
  if (b.upper == null) {
    return "≥ " + formatCount(b.lower) + " jam";
  }

  if (b.lower == null) {
    return "≤ " + formatCount(b.upper) + " jam";
  }

  return formatCount(b.lower) + " - " + formatCount(b.upper) + " jam";
}

// Tampilkan acuan SK dan posisi estimasi setelah pembulatan jam.
function renderSkReference(sk, predictionResult) {
  getElement("skResult").hidden = !sk.available;
  getElement("skEmpty").hidden = sk.available;

  if (!sk.available) {
    getElement("skEmpty").textContent = sk.reason;

    return;
  }
  getElement("skVersion").textContent = "SK Sekda " + sk.version;
  getElement("skLink").href = sk.source_url;
  getElement("skLinkLabel").textContent = sk.page
    ? "Buka PDF sumber (halaman PDF " + sk.page + ")"
    : "Buka PDF sumber";

  getElement("skDescription").textContent =
    "Rincian pada SK: " + sk.description;

  // Aturan SK datang dari /api/context. Cek apakah empat kelompoknya berurutan sebelum
  // menandai posisi estimasi pada 100/80/60/40.
  const bands = sk.bands;

  const valid =
    bands.length === 4 &&
    bands.every(
      (band, index) =>
        index === 0 ||
        (bands[index - 1].upper != null && band.lower === bands[index - 1].upper + 1),
    );

  const classify = (value) =>
    valid
      ? bands.find(
          (b) =>
            (b.lower == null || Math.floor(value + 0.5) >= b.lower) &&
            (b.upper == null || Math.floor(value + 0.5) <= b.upper),
        )
      : null;

  // Bulatkan estimasi ke jam untuk dicocokkan dengan batas SK. Ini hanya menentukan kelompok
  // pada tampilan, tidak mengubah angka prediksi model.
  const point = classify(predictionResult.estimate);
  getElement("skBands").replaceChildren();

  for (const band of bands) {
    const box = createElement(
      "div",
      null,
      ("sk-band rounded-lg border border-amber-200/50 bg-amber-50/40 px-2 py-3 " +
        "text-center [&>span]:mb-1 [&>span]:block [&>span]:text-[10px] " +
        "[&>span]:text-amber-700 [&>strong]:text-xs [&>strong]:whitespace-nowrap " +
        "[&>strong]:text-amber-900 [&.active]:border-emerald-300 " +
        "[&.active]:bg-emerald-50 [&.special]:col-span-full [&.special]:text-left") +
        (point?.score === band.score ? " active" : ""),
    );
    box.append(
      createElement("span", "Nilai " + band.score + "%"),
      createElement("strong", bandText(band)),
    );
    getElement("skBands").append(box);
  }

  if (!bands.length) {
    getElement("skBands").append(
      createElement(
        "div",
        sk.special,
        ("sk-band special col-span-full rounded-lg border border-amber-200 bg-amber-50" +
          " p-3 text-xs text-amber-900"),
      ),
    );
  }

  const lowerDays = predictionResult.interval && classify(predictionResult.interval.lower);

  const upperDays = predictionResult.interval && classify(predictionResult.interval.upper);
  getElement("skPosition").textContent =
    lowerDays && upperDays && lowerDays.score === upperDays.score
      ? "Seluruh rentang perkiraan berada pada kelompok waktu " +
        lowerDays.score +
        "%. Ini bukan penilaian kinerja unit."
      : point
        ? "Perkiraan penyelesaian berada pada kelompok waktu " +
          point.score +
          "%; rentang perkiraan dapat melintasi kelompok lain. Ini bukan penilaian kinerja unit."
        : "Aturan waktu pada dokumen belum cukup jelas untuk dibandingkan dengan perkiraan ini.";
  getElement("skNote").textContent =
    "Mengacu pada SK Sekda 99/2022 dan 175/2025 yang tersedia di aplikasi." +
    (sk.source_note
      ? " " + (sk.source_note === "40%: bertumpang tindih dengan rentang sebelumnya"
        ? "Batas waktu kelompok 40% pada dokumen bertumpang tindih dengan kelompok sebelumnya. Periksa PDF sumber untuk melihat aturannya."
        : sk.source_note)
      : "");
}

// Tiga model menghitung prediksi baru; setiap kartu memakai baris isian yang sama.
function renderLivePredictions(predictions) {
  const cards = getElement("livePredictionCards");
  cards.replaceChildren();

  getElement("livePredictionsScope").textContent =
    predictions.variant + ". Ketiganya dilatih pada " +
    formatCount(predictions.training_count) + " laporan yang sama.";

  for (const model of predictions.rows) {
    const card = createElement(
      "article",
      null,
      model.selected
        ? "rounded-xl border border-teal bg-emerald-50 p-5"
        : "rounded-xl border border-line bg-slate-50 p-5",
    );

    card.append(createElement("h3", model.name, "m-0 text-sm font-semibold text-primary"));
    card.append(createElement(
      "p",
      formatNumber(model.estimate) + " jam",
      "mt-3 mb-0 text-2xl font-bold text-primary",
    ));

    const days = model.estimate < 24
      ? "Kurang dari 1 hari"
      : "Sekitar " + formatCount(model.estimate / 24) + " hari";

    card.append(createElement("p", days, "mt-1 mb-0 text-xs text-muted"));

    if (model.selected) {
      card.append(createElement(
        "p",
        "Dipakai pada halaman warga",
        "mt-3 mb-0 text-xs font-semibold text-teal",
      ));
    }

    cards.append(card);
  }
}

// Ambil sumber pembanding. Jawaban untuk isian/pilihan yang sudah berubah diabaikan.
async function loadAnalysisSource() {
  if (!appState.context || !appState.isianLaporan) return;

  const source = appState.analysisSource;
  // Catat nomor request terbaru. Kalau pengguna cepat mengganti Latihan ke Uji, jawaban
  // Latihan yang datang belakangan tidak boleh menimpa tampilan Uji.
  const requestNumber = ++appState.analysisRequest;

  getElement("analysisLoadStatus").textContent = "Menyiapkan pembanding " +
    (source === "test" ? "data uji" : source === "train" ? "data latihan" : "kedua sumber") +
    "... Data yang masih terlihat adalah pilihan sebelumnya.";

  try {
    // Kirim isian yang sudah dihitung tadi, ditambah pilihan sumber. Backend menyiapkan
    // kelompok pembanding tanpa mengganti model warga.
    const analysis = await postJSON("/api/analysis", {
      ...appState.isianLaporan,
      analysis_source: source,
    });

    if (requestNumber !== appState.analysisRequest) return;
    if (analysis.model !== appState.predictionResult.model) throw new Error("Laporan pembanding belum dapat ditampilkan.");

    appState.analysisData = analysis;
    getElement("analysisLoadStatus").textContent = "";
    if (appState.view === "research") renderResearchDashboard(appState.context);
  } catch (error) {
    if (requestNumber !== appState.analysisRequest) return;
    getElement("analysisLoadStatus").textContent = "Sumber belum berhasil dimuat. " + error.message;
    appState.analysisSource = appState.analysisData.source;
    for (const input of document.querySelectorAll('input[name="analysisSource"]')) {
      input.checked = input.value === appState.analysisSource;
    }
  }
}

// Angka data dan prediksi warga tetap; hanya kelompok pembanding yang berubah.
// Ringkasan data dan metrik semua uji tetap dari context. Pilihan sumber hanya mengganti
// histogram, MAE kelompok, dan grafik lewat renderAnalysisPanels().
function renderResearchDashboard(context) {
  const snapshot = context.snapshot;
  getElement("researchDashboard").hidden = false;
  renderLivePredictions(context.live_predictions);
  getElement("dataTotal").textContent = formatCount(snapshot.training_initial + snapshot.test);
  getElement("dataInitial").textContent = formatCount(snapshot.training_initial);
  getElement("dataTrain").textContent = formatCount(snapshot.training_used);
  getElement("dataTest").textContent = formatCount(snapshot.test_filtered);
  getElement("testAvailability").textContent = formatCount(snapshot.test) + " sebelum IQR";
  getElement("snapshotNote").textContent =
    "Pembagian acak 80/20. Batas IQR per kategori dihitung dari data latih, " +
    "lalu diterapkan pada data uji. Ketiga model memakai laporan yang sama.";

  if (appState.analysisData) {
    renderAnalysisPanels(appState.analysisData, context.evaluation.comparison);
  }
}

// Gabungkan tampilan pembanding historis, SK, dan analisis model.
function renderContext(context) {
  appState.context = context;
  appState.analysisRequest++;
  // Siapkan tampilan awal dari 30 uji pada jawaban backend. Pergantian sumber meminta data lagi.
  appState.analysisData = defaultTestAnalysis(context);
  renderHistory(context, appState.predictionResult);
  renderSkReference(context.sk, appState.predictionResult);

  if (appState.view === "research") {
    renderResearchDashboard(context);
  }
}


// Baca formulir, minta prediksi, lalu muat data pembanding dari Flask.
async function calculateEstimate() {
  // 1. Periksa formulir dan baca isian sebelum tombol dinonaktifkan.
  if (appState.busy || !appState.options || !getElement("form").reportValidity()) {
    return;
  }

  const input = bacaIsianFormulir();
  setBusy(true);
  getElement("error").hidden = true;
  getElement("status").textContent = "Menghitung perkiraan penyelesaian...";

  try {
    // 2. Estimasi baru tetap memakai CatBoost akhir yang digunakan warga.
    // Tampilkan prediksi utama dulu supaya warga tidak menunggu semua pembanding selesai.
    // Setelah itu baru ambil SK, riwayat, grafik, dan kartu tiga model.
    const predictionResult = await postJSON("/api/predict", input);

    appState.isianLaporan = input;
    renderPredictionResult(predictionResult);
    getElement("status").textContent = "Estimasi selesai. Menyiapkan data pembanding...";

    try {
      // 3. Hitung estimasi RF/XGBoost dan ambil hasil uji tersimpan untuk tabel metrik.
      // Kirim isian yang sama dengan request prediksi tadi. Kelompok 30 uji dipilih backend
      // di sini lalu dipakai bersama untuk histogram, MAE, dan grafik.
      const context = await postJSON("/api/context", input);

      if (context.model !== predictionResult.model) {
        throw new Error("Laporan pembanding belum dapat ditampilkan.");
      }

      renderContext(context);

      if (appState.view === "research") {
        await loadAnalysisSource();
      }

      getElement("status").textContent = "Selesai. Hasil mengikuti isian laporan di atas.";
    } catch (error) {
      // Kalau pembanding gagal dimuat, estimasi utama yang sudah berhasil tetap tampil.
      // Bagian riwayat, SK, dan analisis dikosongkan dulu.
      appState.context = null;
      clearContextDisplay();
      getElement("status").textContent = "Estimasi tersedia, tetapi data pembanding belum dapat dimuat.";
      getElement("historyEmpty").textContent = error.message;
    }
  } catch (error) {
    // Prediksi gagal: jangan biarkan hasil isian sebelumnya tetap terlihat.
    appState.predictionResult = null;
    appState.context = null;
    appState.isianLaporan = null;
    clearContextDisplay();
    getElement("error").textContent = error.message;
    getElement("error").hidden = false;
    getElement("status").textContent = "Perkiraan belum berhasil ditampilkan. Silakan coba kembali.";
    getElement("result").hidden = true;
    getElement("empty").hidden = false;
  } finally {
    // 4. Aktifkan formulir kembali, baik perhitungan berhasil maupun gagal.
    setBusy(false);

    if (appState.pendingView) {
      appState.pendingView = false;
      switchPage();
    }
  }
}


// Cegah submit bawaan supaya browser tidak pindah halaman. Kirim isian lewat fetch, lalu
// masukkan jawabannya ke HTML yang sudah ada.
getElement("form").addEventListener("submit", (event) => {
  event.preventDefault();
  calculateEstimate();
});


getElement("sample").addEventListener("click", fillExample);

// Hindari id "reset" agar fungsi bawaan form.reset() tetap dapat dipanggil.
getElement("resetButton").addEventListener("click", resetForm);

// Mengganti sumber hanya memperbarui pembanding peneliti, bukan prediksi isian.
for (const input of document.querySelectorAll('input[name="analysisSource"]')) {
  input.addEventListener("change", () => {
    appState.analysisSource = input.value;
    loadAnalysisSource();
  });
}

getElement("kategori_laporan").addEventListener("change", () => {
  if (appState.options) {
    perbaruiPilihanRincian();
  }
});

getElement("kecamatan").addEventListener("change", () => {
  if (appState.options) {
    perbaruiPilihanKelurahan();
  }
});

for (const id of kolomFormulir) {
  getElement(id).addEventListener("input", markResultsOutdated);
}


getElement("rincian_masalah").addEventListener("change", perbaruiKeteranganRincian);


window.addEventListener("hashchange", switchPage);

window.addEventListener("resize", () => {
  if (appState.view === "research" && appState.context) {
    renderResearchDashboard(appState.context);
  }
});

for (const link of document.querySelectorAll(
  'a[href="#estimasi"],a[href="#analisis"]',
)) {
  link.addEventListener("click", (event) => {
    if (appState.busy) {
      event.preventDefault();
    }
  });
}

setupScatterZoom();

// Pasang dropdown pencarian untuk rincian dan unit saat halaman dibuka. Ini hanya menambah
// cara mencari pilihan, belum menjalankan prediksi.
setupSearchSelect(
  "rincian_masalah",
  "Pilih atau cari rincian masalah",
  searchControls,
  perbaruiKeteranganRincian,
  markResultsOutdated,
);

setupSearchSelect(
  "unit_penanganan",
  "Pilih atau cari unit penanganan",
  searchControls,
  perbaruiKeteranganRincian,
  markResultsOutdated,
);

// Baca daftar pilihan dari paket model ketika halaman dibuka.
async function initializePage() {
  try {
    const response = await fetch("/options.json");

    if (!response.ok) {
      throw new Error("Halaman belum berhasil dimuat. Silakan muat ulang.");
    }
    appState.options = await response.json();

    // 2. Isi dropdown utama dan pilihan yang bergantung pada kategori/kecamatan.
    fillSelect("kategori_laporan", appState.options.kategori_laporan, "Pilih kategori");
    fillSelect("kecamatan", Object.keys(appState.options.kelurahan_per_kecamatan), "Pilih kecamatan");

    fillSelect("kanal_aduan", appState.options.kanal_aduan, "Pilih kanal");
    perbaruiPilihanRincian();
    perbaruiPilihanKelurahan();
    getElement("waktu_masuk").value = currentJakartaTime();

    // 3. Pilih halaman dan tampilkan status siap.

    switchPage();
    getElement("status").textContent = "Siap. Isi laporan atau gunakan contoh.";
  } catch (error) {
    console.error("Gagal memuat pilihan formulir:", error);
    getElement("error").textContent = "Halaman belum berhasil dimuat. Silakan muat ulang.";
    getElement("error").hidden = false;
    getElement("status").textContent = "Belum dapat terhubung ke layanan.";
  }
}

initializePage();
