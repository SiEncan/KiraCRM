import { getElement, formatCount, formatNumber } from "./helpers.js";

// Plotly menyimpan seluruh titik. Zoom dan geser hanya mengubah area pandang.
// Simpan titik dan status grafik agar bisa dipakai lagi. Zoom atau geser hanya mengubah
// tampilan, tidak meminta prediksi baru ke backend.
const plot = {
  evaluation: null,
  points: [],
  maximumActual: 1,
  maximumPrediction: 1,
  initialized: false,
  queue: Promise.resolve(),
  renderer: null,
};

let plotlyReady;

// Halaman warga tidak membutuhkan Plotly. Ambil pustakanya saat grafik pertama dibuat.
function loadPlotly() {
  if (!plotlyReady) {
    plotlyReady = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "/static/vendor/plotly-strict.min.js";
      script.onload = resolve;
      script.onerror = () => {
        script.remove();
        plotlyReady = null;
        reject(new Error("Pustaka grafik belum berhasil dimuat."));
      };
      document.head.append(script);
    });
  }

  return plotlyReady;
}

// Pakai scattergl kalau browser mendukung WebGL agar banyak titik tetap ringan. Kalau tidak
// ada, pakai scatter biasa.
function rendererType() {
  if (!plot.renderer) {
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("webgl2") || canvas.getContext("webgl");
    plot.renderer = context ? "scattergl" : "scatter";
  }

  return plot.renderer;
}

// Satu trace berisi satu kelompok titik. Pisahkan uji/latihan dan terdekat/lainnya supaya
// warna dan checkbox bisa diatur per kelompok.
function reportTrace(points, similar, source) {
  const dariDataLatih = source === "train";
  const sourceName = dariDataLatih ? "latihan" : "uji";
  return {
    type: rendererType(),
    mode: "markers",
    visible: getElement(similar ? "scatterShowSimilar" : "scatterShowOthers").checked,
    name: similar ? "30 laporan " + sourceName + " terdekat" : "Laporan " + sourceName + " lainnya",
    x: points.map((point) => point[1]),
    y: points.map((point) => point[2]),
    customdata: points.map((point) => point[0]),
    marker: {
      color: dariDataLatih ? (similar ? "#c38122" : "#9ca3af") : (similar ? "#7c3aed" : "#437ba1"),
      size: similar ? 11 : 5,
      symbol: "circle",
      opacity: similar ? 1 : dariDataLatih ? 0.35 : 0.7,
      line: { color: "white", width: similar ? 1.5 : 0 },
    },
    hovertemplate: "Baris %{customdata}<br>Aktual: %{x:.2f} jam" +
      "<br>Prediksi: %{y:.2f} jam<extra>%{fullData.name}</extra>",
  };
}

// X adalah aktual, Y adalah prediksi. Batas tiap sumbu mengikuti nilai terbesar dari titik
// yang ditampilkan, bukan angka jam yang ditulis tetap.
function chartLayout() {
  const axis = {
    fixedrange: false,
    minallowed: 0,
    zeroline: false,
    gridcolor: "#e7eff0",
    tickformat: ",.0f",
    automargin: true,
  };
  const idealMaximum = Math.max(plot.maximumActual, plot.maximumPrediction);

  return {
    height: 340,
    margin: { l: 65, r: 20, t: 20, b: 55 },
    font: { family: "Segoe UI, Arial, sans-serif", size: 11, color: "#687d87" },
    paper_bgcolor: "white",
    plot_bgcolor: "white",
    separators: ",.",
    showlegend: false,
    dragmode: "pan",
    hovermode: "closest",
    xaxis: {
      ...axis,
      title: { text: "Durasi aktual (jam)", standoff: 12 },
      range: [0, plot.maximumActual],
      maxallowed: plot.maximumActual,
    },
    yaxis: {
      ...axis,
      title: { text: "Prediksi (jam)", standoff: 12 },
      range: [0, plot.maximumPrediction],
      maxallowed: plot.maximumPrediction,
    },
    shapes: [{
      type: "line", xref: "x", yref: "y", layer: "below",
      x0: 0, y0: 0, x1: idealMaximum, y1: idealMaximum,
      line: { color: "#c99d5e", width: 1.5, dash: "dash" },
    }],
  };
}

function updateScatterNote() {
  const host = getElement("scatter");
  const x = host.layout.xaxis.range;
  const y = host.layout.yaxis.range;
  // Saat zoom, ada titik yang keluar dari layar. Hitung terpisah dari titik yang
  // disembunyikan checkbox supaya keterangan jumlahnya jelas.
  const withinView = plot.points.filter((point) =>
    point[1] >= x[0] && point[1] <= x[1] && point[2] >= y[0] && point[2] <= y[1],
  );
  const showSimilar = getElement("scatterShowSimilar").checked;
  const showOthers = getElement("scatterShowOthers").checked;
  const selected = (point) => point[3] ? showSimilar : showOthers;
  const visible = withinView.filter(selected);
  const selectedCount = plot.points.filter(selected).length;
  const hiddenBySelection = plot.points.length - selectedCount;
  const outsideView = selectedCount - visible.length;
  const similar = visible.filter((point) => point[3]).length;
  const zoom = Math.max(1, plot.maximumActual / (x[1] - x[0]));
  const fullView = visible.length === plot.points.length;

  getElement("scatterSimilarCount").textContent =
    "(" + formatCount(withinView.filter((point) => point[3]).length) + ")";
  getElement("scatterZoomLevel").textContent = formatNumber(zoom, zoom < 1.01 ? 0 : 1) + "x";
  getElement("scatterZoomOut").disabled =
    x[1] - x[0] >= plot.maximumActual && y[1] - y[0] >= plot.maximumPrediction;

  let note;

  if (!showSimilar && !showOthers) {
    note = "Kedua kelompok titik disembunyikan. Centang kelompok yang ingin ditampilkan.";
  } else if (selectedCount === 0) {
    note = "Tidak ada laporan pada kelompok yang diaktifkan untuk pilihan sumber ini.";
  } else if (hiddenBySelection > 0) {
    note = "Terlihat " + formatCount(visible.length) + " titik. " +
      formatCount(hiddenBySelection) + " titik disembunyikan melalui pilihan kelompok." +
      (outsideView ? " " + formatCount(outsideView) + " titik berada di luar area zoom." : "");
  } else if (fullView) {
    note = formatCount(plot.points.length) + " laporan dari sumber terpilih, lolos IQR kategori. " +
      "Maksimum aktual " + formatNumber(plot.maximumActual) + " jam; " +
      "maksimum prediksi " + formatNumber(plot.maximumPrediction) + " jam.";
  } else {
    note = "Terlihat " + formatCount(visible.length) + " dari " + formatCount(plot.points.length) +
      " titik. " + formatCount(plot.points.length - visible.length) +
      " titik berada di luar area zoom. Reset untuk melihat seluruh data.";
  }

  getElement("scatterNote").textContent = note;

  host.dataset.actualMin = x[0];
  host.dataset.actualMax = x[1];
  host.dataset.predictionMin = y[0];
  host.dataset.predictionMax = y[1];
  host.dataset.visiblePoints = visible.length;
  host.dataset.totalPoints = plot.points.length;
  host.dataset.similarPoints = similar;
  host.dataset.hiddenBySelection = hiddenBySelection;
  host.dataset.renderer = plot.renderer;
  host.setAttribute("aria-label", "Grafik prediksi dan durasi aktual, " +
    formatCount(visible.length) + " titik terlihat.");
}

function renderScatterplot(evaluation) {
  const host = getElement("scatter");

  // Resize memakai grafik yang sudah ada, tanpa memasukkan ulang titik.
  // Kalau data masih sama, cukup resize grafik. Tidak perlu memasukkan semua titik lagi
  // setiap ukuran layar berubah.
  if (plot.evaluation === evaluation) {
    if (plot.initialized) {
      Plotly.Plots.resize(host);
    }
    return;
  }

  plot.evaluation = evaluation;

  // Antrekan hasil baru agar proses menggambar yang bersamaan tidak bertabrakan.
  plot.queue = plot.queue.then(async () => {
    await loadPlotly();

    if (plot.evaluation !== evaluation) {
      return;
    }

    // Isi titik: [baris Excel, aktual, prediksi, anggota 30, sumber]. Penanda 30 sudah
    // ditentukan backend lewat daun CatBoost, bukan dipilih ulang di browser.
    plot.points = evaluation.scatter;
    plot.maximumActual = Math.max(1, ...plot.points.map((point) => point[1]));
    plot.maximumPrediction = Math.max(1, ...plot.points.map((point) => point[2]));
    const fromSource = (point, source) => (point[4] || "test") === source;
    const data = [
      reportTrace(plot.points.filter((point) => !point[3] && fromSource(point, "test")), false, "test"),
      reportTrace(plot.points.filter((point) => !point[3] && fromSource(point, "train")), false, "train"),
      // Dua kelompok terdekat digambar terakhir supaya tidak tertutup titik lainnya.
      reportTrace(plot.points.filter((point) => point[3] && fromSource(point, "test")), true, "test"),
      reportTrace(plot.points.filter((point) => point[3] && fromSource(point, "train")), true, "train"),
    ];
    const config = {
      scrollZoom: true, responsive: true, displayModeBar: false,
      displaylogo: false, doubleClick: "reset", showSendToCloud: false,
    };

    // Pakai newPlot saat pertama membuat grafik. Kalau data isian/sumber berubah, pakai
    // react. Untuk zoom atau geser cukup ubah batas sumbunya.
    if (plot.initialized) {
      // Hanya hasil isian baru yang memperbarui data grafik.
      await Plotly.react(host, data, chartLayout(), config);
    } else {
      await Plotly.newPlot(host, data, chartLayout(), config);
      host.on("plotly_relayout", updateScatterNote);
      plot.initialized = true;
      host.dataset.initializations = "1";
    }

    host.dataset.dataUpdates = Number(host.dataset.dataUpdates || 0) + 1;
    updateScatterNote();
  }).catch((error) => {
    console.error("Grafik belum berhasil dimuat:", error);
    getElement("scatterNote").textContent = "Grafik belum berhasil dimuat. Coba muat ulang halaman.";
  });
}

function zoomScatter(multiplier) {
  if (!plot.initialized) {
    return;
  }

  const host = getElement("scatter");
  // Tombol zoom menghitung batas layar baru. Batasi agar tidak negatif atau melewati tampilan
  // penuh. Reset mengembalikan batas awal kedua sumbu.
  function changedRange(current, maximum) {
    const span = Math.min(maximum, (current[1] - current[0]) / multiplier);
    const lower = Math.max(0, Math.min(maximum - span, current[0]));
    return [lower, lower + span];
  }

  // relayout mengubah batas sumbu, bukan data atau susunan titik.
  Plotly.relayout(host, {
    "xaxis.range": changedRange(host.layout.xaxis.range, plot.maximumActual),
    "yaxis.range": changedRange(host.layout.yaxis.range, plot.maximumPrediction),
  });
}

function resetScatterPlot() {
  if (plot.initialized) {
    Plotly.relayout(getElement("scatter"), {
      "xaxis.range": [0, plot.maximumActual],
      "yaxis.range": [0, plot.maximumPrediction],
    });
  }
}

function setScatterGroupVisible(similar, visible) {
  // Mengubah visibilitas trace yang sudah tersimpan, tanpa membuat grafik baru.
  plot.queue = plot.queue.then(async () => {
    if (!plot.initialized) {
      return;
    }

    // Trace 2/3 berisi terdekat uji/latihan, 0/1 berisi laporan lainnya. Checkbox hanya
    // mengganti visible, jadi titiknya tetap tersimpan.
    await Plotly.restyle(getElement("scatter"), { visible }, similar ? [2, 3] : [0, 1]);
    updateScatterNote();
  }).catch((error) => console.error("Kelompok grafik belum berhasil diubah:", error));
}

export { renderScatterplot, zoomScatter, resetScatterPlot, setScatterGroupVisible };
