const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const WS_PROTOCOL = BASE.startsWith("https") ? "wss" : "ws";
const HTTP_BASE = BASE.replace(/^https?/, "");

export const API_URL = `${BASE}/api`;
export const WS_URL = `${WS_PROTOCOL}${HTTP_BASE}/ws`;
