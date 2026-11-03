import {
  getElement,
  formatNumber,
  formatCount,
  createElement,
  createSvgElement,
  createChart,
  addChartText,
} from "./helpers.js";
import { setupScatterControls } from "./scatter-controls.js";
import { renderScatterplot } from "./scatter-plot.js";

// Grafik hanya menggambar angka yang diberikan server.

function setupScatterZoom() {
  setupScatterControls();
}

// Gambar rentang kuartil historis dan rentang prediksi pada sumbu yang sama.
function renderHistoryChart(history, predictionResult) {
  const root = createChart(
    getElement("historyTimeline"),
    "Rentang historis dan rentang perkiraan, dalam jam",
    560,
    103,
  );

  // Ujung skala pembanding warga memakai persentil 90 supaya bagian yang umum tetap terbaca.
  // Kalau rentang lewat ujung skala, tambahkan tanda panah.
  const max = Math.max(history.p90, 1);

  // Ubah jam menjadi posisi mendatar dalam gambar SVG (bukan angka untuk model).
  const xCoordinate = (hours) => 18 + Math.min(Math.max(hours / max, 0), 1) * 515;
  createSvgElement(
    "rect",
    {
      x: 18,
      y: 38,
      width: 515,
      height: 12,
      rx: 6,
      fill: "#edf2f3",
    },
    root,
  );

  // Batang hijau muda menunjukkan Q1-Q3 riwayat. 
  createSvgElement(
    "rect",
    {
      x: xCoordinate(history.q1),
      y: 38,
      width: Math.max(3, xCoordinate(history.q3) - xCoordinate(history.q1)),
      height: 12,
      rx: 6,
      fill: "#bad9cc",
    },
    root,
  );

  // Garis rentang model
  // dari OOF; keduanya memang punya sumber berbeda.
  if (predictionResult.interval) {
    const lower = xCoordinate(predictionResult.interval.lower);

    const upper = xCoordinate(predictionResult.interval.upper);
    createSvgElement(
      "rect",
      {
        x: lower,
        y: 42,
        width: Math.max(3, upper - lower),
        height: 5,
        rx: 2.5,
        fill: "#276d75",
      },
      root,
    );

    if (predictionResult.interval.upper > max) {
      createSvgElement(
        "path",
        {
          d: "M535 38l8 6-8 6",
          fill: "none",
          stroke: "#276d75",
          "stroke-width": 2,
        },
        root,
      );
    }
  }

  // Segitiga menunjukkan estimasi titik, bukan median riwayat. Letaknya tidak harus di tengah
  // rentang karena batas rentang dihitung pada skala log.
  const position = xCoordinate(predictionResult.estimate);
  createSvgElement(
    "path",
    {
      d: `M${position - 4} 22h8l-4 7z`,
      fill: "#276d75",
    },
    root,
  );
  addChartText(
    root,
    Math.min(465, Math.max(83, position)),
    15,
    "perkiraan laporan ini",
    {
      "text-anchor": "middle",
      fill: "#276d75",
      "font-size": 9,
    },
  );
  addChartText(root, 18, 73, "0");

  addChartText(root, 533, 73, formatCount(max) + " jam", {
    "text-anchor": "end",
  });
  addChartText(root, 18, 95, "Tanda > menunjukkan durasi yang melewati ujung skala.", {
    "font-size": 9,
  });
}

// Gambar jumlah laporan pada setiap kelompok durasi.
function renderHistogram(history, label, options = {}) {
  const host = getElement(options.hostId || "histogram");
  const width = Math.max(host.clientWidth, 280);
  const root = createChart(host, label, width, 250);
  const left = 44;
  const right = width - 16;
  const top = 40;
  const bottom = 205;
  // Jumlah tiap batang sudah dihitung backend. Di sini tinggal ubah menjadi tinggi batang
  // SVG, bukan membuat prediksi baru.
  const bins = history.histogram;
  const maximumCount = options.maximumCount || Math.max(...bins.map((bin) => bin.count), 1);
  const barWidth = (right - left) / bins.length;

  // Garis bantu menunjukkan banyaknya laporan, bukan durasi.
  for (let index = 0; index <= 3; index++) {
    const y = bottom - (index / 3) * (bottom - top);
    createSvgElement("line", { x1: left, y1: y, x2: right, y2: y, stroke: "#e7eff0" }, root);
    addChartText(root, left - 8, y + 4, formatCount((maximumCount * index) / 3), {
      "text-anchor": "end", "font-size": 11,
    });
  }

  for (const [index, bin] of bins.entries()) {
    const height = (bin.count / maximumCount) * (bottom - top);
    const rectangle = createSvgElement("rect", {
      x: left + index * barWidth + 2,
      y: bottom - height,
      width: Math.max(1, barWidth - 4),
      height,
      rx: 3,
      fill: options.color || "#91b9bd",
    }, root);

    createSvgElement("title", {}, rectangle,
      formatNumber(bin.lower, 1) + " - " + formatNumber(bin.upper, 1) +
      " jam: " + formatCount(bin.count) + " laporan",
    );
  }

  // Posisi median memakai batas batang histogram yang sama dengan durasinya.
  const minimum = bins[0].lower;
  const maximum = bins[bins.length - 1].upper;
  const medianX = left + ((history.median - minimum) / (maximum - minimum)) * (right - left);
  createSvgElement("line", {
    x1: medianX, x2: medianX, y1: top - 4, y2: bottom,
    stroke: "#0d7d78", "stroke-width": 2,
  }, root);
  const medianNearRight = medianX > right - 60;
  addChartText(root, medianX + (medianNearRight ? -5 : 5), top - 9, "Median", {
    fill: "#0d7d78", "font-size": 11,
    "text-anchor": medianNearRight ? "end" : "start",
  });

  addChartText(root, left, 228, formatCount(minimum) + " jam", { "font-size": 11 });
  addChartText(root, right, 228, formatCount(maximum) + " jam", {
    "text-anchor": "end", "font-size": 11,
  });
  addChartText(root, left, 12, "Jumlah laporan", { "font-size": 10 });

  // Median dan kuartil memakai anggota yang sama dengan histogram. options menentukan apakah
  // angka ditaruh pada panel latihan atau uji.
  const facts = getElement(options.factsId || "distributionFacts");
  facts.replaceChildren();

  for (const [name, value] of [
    ["Median", history.median],
    ["Kuartil 1", history.q1],
    ["Kuartil 3", history.q3],
  ]) {
    const fact = createElement("div");
    fact.append(
      createElement("span", name),
      createElement("strong", formatNumber(value, 1) + " jam"),
    );
    facts.append(fact);
  }
}

export { renderHistoryChart, renderHistogram, renderScatterplot, setupScatterZoom };
