const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const WS_PROTOCOL = BASE.startsWith("https") ? "wss" : "ws";
const HTTP_BASE = BASE.replace(/^https?/, "");

export const API_URL = `${BASE}/api`;
export const WS_URL = `${WS_PROTOCOL}${HTTP_BASE}/ws`;

export const GOOGLE_CLIENT_ID =
  import.meta.env.VITE_GOOGLE_CLIENT_ID ??
  "879038766799-lihogd5k6ed49n9gbv29min1mftfp78h.apps.googleusercontent.com";
