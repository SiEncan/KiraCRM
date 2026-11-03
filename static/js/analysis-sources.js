// Tampilan pembanding peneliti. Data uji dan latihan selalu diringkas terpisah.
import { getElement, createElement, formatCount, formatNumber } from "./helpers.js";
import { renderHistogram, renderScatterplot } from "./charts.js";

// Samakan bentuk jawaban /api/context dengan /api/analysis. Fungsi tampilan yang sama bisa
// dipakai untuk Uji, Latihan, dan Keduanya.
function defaultTestAnalysis(context) {
  return {
    source: "test",
    model: context.model,
    groups: [{
      source: "test",
      label: "Data uji",
      neighbors: context.neighbors,
      rows: context.evaluation.comparison.rows.map((row) => ({ name: row.name, mae: row.similar_mae })),
      scatter: context.evaluation.scatter.map((point) => [...point, "test"]),
    }],
  };
}

function addFact(host, label, value, unit) {
  const fact = createElement("div");
  fact.append(createElement("span", label), createElement("strong", formatNumber(value) + unit));
  host.append(fact);
}

// Pada pilihan Keduanya, samakan kelompok batang dan skala histogram agar mudah dibandingkan.
function matchingHistograms(groups) {
  if (groups.length === 1) {
    return groups.map((group) => group.neighbors);
  }

  // Gabungkan durasi hanya untuk mencari batas batang yang sama. Median, kuartil, dan anggota
  // kedua sumber tetap dihitung terpisah.
  const durations = groups.flatMap((group) => group.neighbors.rows.map((row) => row.duration));
  const minimum = Math.min(...durations);
  const maximum = Math.max(minimum + 1, ...durations);
  const step = (maximum - minimum) / 5;

  return groups.map((group) => {
    const bins = Array.from({ length: 5 }, (_, i) => ({ lower: minimum + i * step, upper: minimum + (i + 1) * step, count: 0 }));
    for (const row of group.neighbors.rows) {
      bins[Math.min(4, Math.floor((row.duration - minimum) / step))].count++;
    }
    return { ...group.neighbors, histogram: bins };
  });
}

// Tampilkan panel sesuai sumber. Kalau Keduanya, samakan batas dan tinggi skala histogram
// supaya perbandingannya mudah dibaca.
function renderDistributions(groups) {
  getElement("distributionTestPanel").hidden = !groups.some((group) => group.source === "test");
  getElement("distributionTrainPanel").hidden = !groups.some((group) => group.source === "train");
  getElement("distributionPanels").classList.toggle("lg:grid-cols-2", groups.length === 2);
  const histograms = matchingHistograms(groups);
  const maximumCount = Math.max(...histograms.flatMap((item) => item.histogram.map((bin) => bin.count)));

  for (const [index, group] of groups.entries()) {
    const dariDataLatih = group.source === "train";
    const factsId = dariDataLatih ? "distributionFactsTrain" : "distributionFacts";
    renderHistogram(histograms[index], "Sebaran 30 laporan " + group.label.toLowerCase(), {
      hostId: dariDataLatih ? "histogramTrain" : "histogram",
      factsId,
      color: dariDataLatih ? "#d5b17c" : "#91b9bd",
      maximumCount,
    });
    addFact(getElement(factsId), "Kemiripan rata-rata", group.neighbors.mean_similarity, "%");
  }

  getElement("histogramScope").textContent = groups.map((group) =>
    group.label + ": 30 dari " + formatCount(group.neighbors.candidates) + " laporan lolos IQR",
  ).join(". ") + (groups.length === 2 ? ". Kedua histogram memakai skala yang sama." : ".");
}

// groups berisi MAE 30 anggota tiap sumber. overall tetap metrik semua uji, jadi memilih
// Latihan tidak mengganti metrik keseluruhan dengan hasil latihan.
function renderPerformance(groups, overall) {
  const both = groups.length === 2;
  getElement("trainMaeHeading").hidden = !both;
  getElement("localMaeHeading").textContent = "MAE 30 " + (groups[0].source === "test" ? "uji" : "latihan") + " (jam)";
  getElement("evaluationScope").textContent = "Metrik keseluruhan: " + formatCount(overall.n) + " uji";
  const body = getElement("modelComparisonRows");
  body.replaceChildren();

  for (const model of overall.rows) {
    const row = createElement("tr", null, model.selected ? "selected-model" : "");
    const name = createElement("td", model.name);
    if (model.selected) name.append(createElement("small", "Model estimasi warga"));
    row.append(name);
    for (const group of groups) {
      row.append(createElement("td", formatNumber(group.rows.find((item) => item.name === model.name).mae)));
    }
    for (const value of [model.metrics.mae, model.metrics.rmse]) {
      row.append(createElement("td", formatNumber(value)));
    }
    row.append(createElement("td", formatNumber(model.metrics.r2, 4)));
    body.append(row);
  }
}

function renderAnalysisPanels(analysis, overall) {
  // Satu sumber berisi 30 anggota. Keduanya berisi dua kelompok berisi 30 masing-masing.
  // Teruskan kelompok yang sama ke histogram, tabel MAE, dan grafik.
  const groups = analysis.groups;
  const both = groups.length === 2;
  const dariDataLatih = groups.some((group) => group.source === "train");
  getElement("analysisSourceNote").textContent = both
    ? "30 laporan uji dan 30 laporan latihan dipilih terpisah. Histogram, median, kuartil, MAE, serta penanda grafik tetap mengikuti kelompok masing-masing."
    : dariDataLatih
      ? "30 laporan latihan terdekat."
      : "30 laporan uji terdekat yang tidak dipakai melatih model.";
  renderDistributions(groups);
  renderPerformance(groups, overall);

  getElement("scatterHeading").textContent = "Prediksi terhadap durasi aktual pada " + (both ? "data uji dan latihan" : dariDataLatih ? "data latihan" : "data uji");
  getElement("scatterTestDot").hidden = !groups.some((group) => group.source === "test");
  getElement("scatterTrainDot").hidden = !dariDataLatih;
  getElement("scatterSimilarLabel").textContent = both ? "30 uji + 30 latihan terdekat" : "30 laporan " + (dariDataLatih ? "latihan" : "uji") + " terdekat";
  getElement("scatterOthersLabel").textContent = both ? "Laporan lainnya dari kedua sumber" : "Laporan " + (dariDataLatih ? "latihan" : "uji") + " lainnya";
  getElement("scatterSourceNote").textContent = both ? "Ungu: 30 uji terdekat. Oranye: 30 latihan terdekat. Biru: uji lainnya. Abu-abu: latihan lainnya." : dariDataLatih ? "Titik latihan sudah dipelajari model." : "Ungu: 30 uji terdekat. Biru: uji lainnya.";

  // Gunakan objek yang sama saat resize agar grafik hanya mengubah ukuran.
  if (!analysis.chartEvaluation) {
    // Grafik membawa semua titik dari sumber terpilih. Penanda di dalam tiap titik membedakan
    // 30 terdekat dari laporan lainnya.
    analysis.chartEvaluation = { scatter: groups.flatMap((group) => group.scatter) };
  }
  renderScatterplot(analysis.chartEvaluation);
}

export { defaultTestAnalysis, renderAnalysisPanels };
