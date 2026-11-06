// Fungsi kecil yang dipakai bersama oleh formulir dan grafik.

// Ambil elemen HTML berdasarkan id, misalnya getElement('kategori_laporan').
function getElement(id) {
  return document.getElementById(id);
}

// Tampilkan angka dengan pemisah Indonesia: 1234.5 menjadi 1.234,50.
function formatNumber(value, decimalPlaces = 2) {
  if (value == null) {
    return "Belum tersedia";
  }

  const formatter = new Intl.NumberFormat("id-ID", {
    maximumFractionDigits: decimalPlaces,
    minimumFractionDigits: decimalPlaces,
  });

  return formatter.format(value);
}

// Tampilkan jumlah laporan atau jam tanpa angka desimal.
function formatCount(value) {
  return formatNumber(value, 0);
}

// Format tanggal hasil model dalam zona waktu Jakarta.
function formatDate(value) {
  const formatter = new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Jakarta",
  });

  const jakartaDate = new Date(value + "+07:00");

  return formatter.format(jakartaDate) + " WIB";
}

// Buat elemen HTML dan isi teksnya dengan textContent.
function createElement(tag, text, className) {
  const node = document.createElement(tag);

  if (text != null) {
    node.textContent = text;
  }

  if (className) {
    node.className = className;
  }

  return node;
}

// Ubah batas jam menjadi jumlah hari bulat sesuai tampilan warga.
function formatRangeDays(interval) {
  if (!interval) {
    return "";
  }

  // Untuk tulisan hari, bagi jam dengan 24 lalu buang pecahannya. Angka jam asli tetap ada;
  // tampilan hari cukup misalnya 2-9 hari.
  const lowerDays = Math.floor(interval.lower / 24);

  const upperDays = Math.floor(interval.upper / 24);

  if (upperDays === 0) {
    return "Kurang dari 1 hari";
  }

  if (lowerDays === upperDays) {
    return "Sekitar " + formatCount(lowerDays) + " hari";
  }

  return "Sekitar " + formatCount(lowerDays) + " - " + formatCount(upperDays) + " hari";
}

// Ambil tanggal dan jam Jakarta untuk nilai awal formulir.
function currentJakartaTime() {
  const currentTime = new Date();
  // Pakai waktu Jakarta untuk nilai awal form walaupun zona browser berbeda. Ubah formatnya
  // agar cocok dengan datetime-local.
  const jakartaTime = currentTime.toLocaleString("sv-SE", {
    timeZone: "Asia/Jakarta",
  });

  // Format input datetime-local adalah YYYY-MM-DDTHH:mm.
  return jakartaTime.replace(" ", "T").slice(0, 16);
}

// Kirim objek JSON ke Flask dan ubah pesan gagal menjadi Error JavaScript.
async function postJSON(url, body) {
  // Ubah objek JavaScript menjadi teks JSON agar Flask bisa membaca lewat request.get_json().
  // await menunggu jawaban tanpa menghentikan tampilan loading.
  let response;

  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
  } catch (error) {
    console.error("Gagal menghubungi layanan:", error);
    throw new Error("Belum dapat terhubung ke layanan. Silakan coba kembali.");
  }

  let output;

  try {
    output = await response.json();
  } catch {
    throw new Error(
      "Layanan belum dapat memproses permintaan. Silakan coba kembali.",
    );
  }

  // Kalau status HTTP gagal, lempar Error agar masuk ke catch di pemanggil. Pesan dari
  // backend bisa langsung dipakai untuk memberi tahu pengguna.
  if (!response.ok) {
    throw new Error(output.error || "Permintaan gagal.");
  }

  return output;
}

// Buat elemen SVG untuk menggambar grafik langsung di browser.
function createSvgElement(tag, attributes, parent, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);

  for (const [key, value] of Object.entries(attributes || {})) {
    node.setAttribute(key, String(value));
  }

  if (text != null) {
    node.textContent = text;
  }

  if (parent) {
    parent.append(node);
  }

  return node;
}

// Siapkan kanvas SVG dengan judul yang dapat dibaca pembaca layar.
function createChart(host, title, width = 500, height = 250) {
  const root = createSvgElement("svg", {
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": title,
  });
  createSvgElement("title", {}, root, title);
  // Ganti SVG lama dengan gambar terbaru. Jangan ditambah terus, supaya histogram tidak
  // menumpuk setelah hitung ulang atau resize.
  host.replaceChildren(root);

  return root;
}

// Tambahkan label teks pada posisi tertentu dalam grafik.
function addChartText(parent, value, y, text, extra = {}) {
  return createSvgElement(
    "text",
    {
      x: value,
      y,
      fill: "#7c9099",
      "font-size": 10,
      "font-family": "Segoe UI, Arial, sans-serif",
      ...extra,
    },
    parent,
    text,
  );
}

export {
  getElement,
  formatNumber,
  formatCount,
  formatDate,
  createElement,
  formatRangeDays,
  currentJakartaTime,
  postJSON,
  createSvgElement,
  createChart,
  addChartText,
};
