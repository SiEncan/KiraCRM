import { getElement, createElement } from "./helpers.js";

// Tambahkan kotak pencarian pada select; nilai aslinya tetap disimpan di select.
function setupSearchSelect(
  id,
  placeholder,
  searchControls,
  perbaruiKolomTerkait,
  markResultsOutdated,
) {
  // Buat kotak pencarian dan daftar pilihan di atas select HTML yang asli.
  // Select asli tetap menyimpan pilihan untuk form. Input tambahan ini hanya kotak pencarian
  // agar pilihannya lebih gampang dicari.
  const select = getElement(id);

  const wrapper = createElement("div", null, "search-select relative min-w-0");

  const input = createElement("input");

  const toggle = createElement(
    "button",
    "⌄",
    ("search-toggle absolute top-px right-px h-[46px] w-10 rounded-lg border-0 " +
      "bg-transparent p-0 text-xl text-muted"),
  );

  const list = createElement(
    "div",
    null,
    ("search-options absolute inset-x-0 top-[calc(100%+5px)] z-30 max-h-64 " +
      "overflow-y-auto rounded-lg border border-line bg-white p-1 shadow-xl"),
  );
  input.id = id + "Search";
  input.className = "pr-11";
  input.type = "text";

  input.autocomplete = "off";
  input.placeholder = placeholder;
  // Pindahkan aturan wajib isi ke kotak yang terlihat agar browser bisa menyorotnya.
  input.required = select.required;
  select.required = false;
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");

  input.setAttribute("aria-expanded", "false");
  list.id = id + "Choices";
  list.setAttribute("role", "listbox");
  list.hidden = true;

  input.setAttribute("aria-controls", list.id);
  toggle.type = "button";
  toggle.tabIndex = -1;
  toggle.setAttribute(
    "aria-label",
    "Buka pilihan " + placeholder.replace("Pilih atau cari ", ""),
  );

  wrapper.append(input, toggle, list);
  select.insertAdjacentElement("afterend", wrapper);
  select.hidden = true;
  document.querySelector('label[for="' + id + '"]').htmlFor = input.id;

  // activeIndex menandai pilihan yang sedang disorot oleh tombol panah keyboard.
  let activeIndex = -1;
  let matchingOptions = [];

  // Tutup daftar tanpa menghapus pilihan yang sudah tersimpan.
  function closeOptions() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    activeIndex = -1;
  }

  // Samakan teks kotak pencarian dengan nilai select setelah dipilih atau di-reset.
  // Mengganti select dari kode belum tentu mengubah teks pencariannya. Samakan keduanya di
  // sini, termasuk setelah Reset atau isi contoh.
  function syncSelection() {
    input.value = select.value;
    input.setCustomValidity("");
    closeOptions();

    if (id === "rincian_masalah") {
      perbaruiKolomTerkait();
    }
  }

  // Simpan pilihan. Event input/change memberi tahu app.js bahwa isian berubah.
  function chooseOption(value) {
    select.value = value;
    syncSelection();
    // Mengubah select.value lewat kode tidak otomatis memicu event. Kirim event supaya app.js
    // tahu isian berubah dan hasil lama perlu dihitung lagi.
    select.dispatchEvent(
      new Event("input", {
        bubbles: true,
      }),
    );
    select.dispatchEvent(
      new Event("change", {
        bubbles: true,
      }),
    );

    input.focus();
    closeOptions();
  }

  // Tandai satu baris pilihan dan pastikan baris tersebut terlihat.
  function highlightOption() {
    for (const [i, row] of [...list.children].entries()) {
      row.classList.toggle("active", i === activeIndex);

      if (i === activeIndex) {
        input.setAttribute("aria-activedescendant", row.id);
        row.scrollIntoView({
          block: "nearest",
        });
      }
    }
  }

  // Pencarian hanya menyaring daftar dalam browser; tidak meminta prediksi server.
  function showOptions(query = "") {
    // Tutup dropdown lain saat daftar ini dibuka. Pencarian berlangsung di browser saja,
    // belum meminta prediksi ke server.
    for (const [other, control] of searchControls) {
      if (other !== id) {
        control.close();
      }
    }
    list.replaceChildren();
    activeIndex = -1;

    const searchText = query.trim().toLocaleLowerCase("id-ID");
    matchingOptions = [...select.options].filter(
      (option) =>
        !option.value || option.text.toLocaleLowerCase("id-ID").includes(searchText),
    );
    matchingOptions.forEach((option, index) => {
      const row = createElement(
        "button",
        option.text,
        ("search-option block w-full rounded-md border-0 bg-white p-3 text-left " +
          "text-sm leading-relaxed whitespace-normal wrap-anywhere text-ink " +
          "hover:bg-emerald-50 [&.active]:bg-emerald-50 aria-selected:font-semibold " +
          "aria-selected:text-teal"),
      );
      row.type = "button";

      row.id = id + "Choice" + index;
      row.setAttribute("role", "option");
      row.setAttribute("aria-selected", String(option.value === select.value));
      row.addEventListener("mousedown", (event) => event.preventDefault());

      row.addEventListener("click", () => chooseOption(option.value));
      list.append(row);
    });

    if (searchText && !matchingOptions.some((option) => option.value)) {
      list.append(
        createElement(
          "p",
          "Tidak ada pilihan yang cocok. Coba kata lain.",
          "search-empty m-0 p-3 text-xs text-muted",
        ),
      );
    }
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }
  input.addEventListener("click", () =>
    showOptions(input.value === select.value ? "" : input.value),
  );

  // Saat pengguna mengetik, terima hanya nilai yang ada dalam daftar pilihan.
  // Cocokkan teks ketikan dengan pilihan select. Kalau belum cocok, tahan submit dulu; kolom
  // opsional tetap boleh dikosongkan.
  input.addEventListener("input", () => {
    const match = [...select.options].find(
      (option) =>
        option.value.toLocaleLowerCase("id-ID") ===
        input.value.trim().toLocaleLowerCase("id-ID"),
    );
    select.value = match ? match.value : "";
    input.setCustomValidity(
      match ? "" : input.required
        ? "Pilih kategori laporan dari hasil pencarian."
        : "Pilih hasil pencarian, atau kosongkan kolom.",
    );
    perbaruiKolomTerkait();

    markResultsOutdated();

    if (!input.value.trim()) {
      closeOptions();

      return;
    }
    showOptions(input.value);
  });
  // Tombol panah memindahkan sorotan; Enter memilih; Escape menutup daftar.
  // Panah memindahkan sorotan. Enter menyimpan pilihan, sedangkan Escape menutup daftar.
  // Belum ada prediksi yang dijalankan di sini.
  input.addEventListener("keydown", (event) => {
    if (["ArrowDown", "ArrowUp"].includes(event.key)) {
      event.preventDefault();

      if (list.hidden) {
        showOptions(input.value === select.value ? "" : input.value);
      }
      activeIndex = Math.max(
        0,
        Math.min(
          matchingOptions.length - 1,
          activeIndex + (event.key === "ArrowDown" ? 1 : -1),
        ),
      );
      highlightOption();
    } else if (event.key === "Enter" && !list.hidden) {
      event.preventDefault();

      const selected =
        activeIndex >= 0
          ? matchingOptions[activeIndex]
          : matchingOptions.find(
              (option) =>
                option.value &&
                option.value.toLowerCase() === input.value.trim().toLowerCase(),
            );

      if (selected) {
        chooseOption(selected.value);
      } else if (matchingOptions.filter((option) => option.value).length === 1) {
        chooseOption(matchingOptions.find((option) => option.value).value);
      }
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeOptions();
    }
  });
  toggle.addEventListener("mousedown", (event) => event.preventDefault());
  toggle.addEventListener("click", () => {
    if (list.hidden) {
      input.focus();
      showOptions();
    } else {
      closeOptions();
    }
  });
  wrapper.addEventListener("focusout", (event) => {
    if (!wrapper.contains(event.relatedTarget)) {
      closeOptions();
    }
  });

  document.addEventListener("pointerdown", (event) => {
    if (!wrapper.contains(event.target)) {
      closeOptions();
    }
  });
  select.addEventListener("change", syncSelection);
  // Simpan fungsi sync dan close supaya app.js bisa mengatur dropdown dari luar tanpa
  // mengurus isi elemen-elemen di dalamnya.
  searchControls.set(id, { sync: syncSelection, close: closeOptions });

  syncSelection();
}

export { setupSearchSelect };
