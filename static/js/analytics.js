import { inject } from "../vendor/vercel-analytics/index.mjs";

// Kunjungan saat mencoba aplikasi di komputer sendiri tidak ikut dihitung.
const localHosts = ["localhost", "127.0.0.1", "[::1]"];

if (!localHosts.includes(window.location.hostname)) {
  inject({ mode: "production", debug: false });
}
