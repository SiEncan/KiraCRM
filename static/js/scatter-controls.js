import { getElement } from "./helpers.js";
import { zoomScatter, resetScatterPlot, setScatterGroupVisible } from "./scatter-plot.js";

// Roda mouse, drag, dan tooltip ditangani Plotly. Tiga tombol ini hanya
// mengubah area pandang pada grafik yang sama.
// Pasang event tombol sekali saat halaman dibuka. Hitungan batas sumbu dan pengaturan titik
// ada di scatter-plot.js.
function setupScatterControls() {
  getElement("scatterZoomIn").addEventListener("click", () => zoomScatter(2));
  getElement("scatterZoomOut").addEventListener("click", () => zoomScatter(0.5));
  getElement("scatterZoomReset").addEventListener("click", resetScatterPlot);

  // Checkbox hanya menampilkan atau menyembunyikan kelompok. Saat dicentang lagi, tidak perlu
  // mengambil titik dari server.
  getElement("scatterShowSimilar").addEventListener("change", (event) => {
    setScatterGroupVisible(true, event.target.checked);
  });

  getElement("scatterShowOthers").addEventListener("change", (event) => {
    setScatterGroupVisible(false, event.target.checked);
  });
}

export { setupScatterControls };
