import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import type { Portfolio, Position, Signal, TickerProfile, WsMessage } from "@/types";
import { API_URL, WS_URL } from "@/config";
import { authFetch, getAuthWsUrl, useAuth } from "@/hooks/useAuth";

interface DashboardState {
  portfolio: Portfolio | null;
  positions: Position[];
  signals: Signal[];
  watchlist: TickerProfile[];
  connected: boolean;
  lastUpdate: string | null;
}

/**
 * Hook that connects to the backend WebSocket for real-time portfolio updates
 * and provides REST API helpers.
 */
export function useTradingBot() {
  const { token } = useAuth();
  const [state, setState] = useState<DashboardState>({
    portfolio: null,
    positions: [],
    signals: [],
    watchlist: [],
    connected: false,
    lastUpdate: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ───────────────────────── WebSocket ─────────────────────────
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    if (!token) return;

    const ws = new WebSocket(getAuthWsUrl(WS_URL));

    ws.onopen = () => {
      setState((s) => ({ ...s, connected: true }));
      console.log("[WS] Connected");
    };

    ws.onmessage = (event) => {
      try {
        const data: WsMessage = JSON.parse(event.data);

        if (data.type === "portfolio_update") {
          setState((s) => ({
            ...s,
            portfolio: data.portfolio ?? s.portfolio,
            positions: data.positions ?? s.positions,
            lastUpdate: data.timestamp ?? new Date().toISOString(),
          }));
        }

        if (data.type === "analysis_complete" && data.signals) {
          setState((s) => ({
            ...s,
            signals: data.signals ?? s.signals,
            lastUpdate: data.timestamp ?? new Date().toISOString(),
          }));
          const count = (data.signals as Signal[])?.length ?? 0;
          if (count > 0) {
            toast.info(`Análisis completo — ${count} señal${count > 1 ? "es" : ""}`);
          }
        }

        if (data.type === "trade_executed") {
          const action = (data as Record<string, unknown>).action as string;
          const ticker = (data as Record<string, unknown>).ticker as string;
          const pnl = (data as Record<string, unknown>).pnl_pct as number | undefined;
          const labels: Record<string, string> = {
            BUY: "Compra",
            SELL: "Venta",
            TAKE_PROFIT: "Take Profit",
            EXIT_RED_ZONE: "Salida Rojo",
            CLOSE_EOD: "Cierre EOD",
            EXTRAORDINARY_GAP_SELL: "Gap Extraordinario",
          };
          const label = labels[action] ?? action;
          const pnlStr = pnl !== undefined ? ` (${pnl >= 0 ? "+" : ""}${pnl.toFixed(1)}%)` : "";
          if (action === "BUY") {
            toast.success(`${label}: ${ticker}`);
          } else {
            toast(pnl !== undefined && pnl >= 0 ? `✅ ${label}: ${ticker}${pnlStr}` : `🔻 ${label}: ${ticker}${pnlStr}`);
          }
        }
      } catch (err) {
        console.error("[WS] Parse error:", err);
      }
    };

    ws.onclose = () => {
      setState((s) => ({ ...s, connected: false }));
      console.log("[WS] Disconnected — reconnecting in 3s...");
      reconnectTimeout.current = setTimeout(connect, 3000);
    };

    ws.onerror = (err) => {
      console.error("[WS] Error:", err);
      ws.close();
    };

    wsRef.current = ws;
  }, [token]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
      wsRef.current?.close();
    };
  }, [connect]);

  // ───────────────────────── REST helpers ─────────────────────────
  const fetchPortfolio = useCallback(async () => {
    try {
      const res = await authFetch(`${API_URL}/portfolio`);
      const data = await res.json();
      setState((s) => ({
        ...s,
        portfolio: data.portfolio,
        positions: data.positions,
      }));
    } catch (err) {
      console.error("Failed to fetch portfolio:", err);
    }
  }, []);

  const fetchSignals = useCallback(async () => {
    try {
      const res = await authFetch(`${API_URL}/signals`);
      const data = await res.json();
      setState((s) => ({ ...s, signals: data.signals }));
    } catch (err) {
      console.error("Failed to fetch signals:", err);
    }
  }, []);

  const fetchWatchlist = useCallback(async () => {
    try {
      const res = await authFetch(`${API_URL}/watchlist`);
      const data = await res.json();
      setState((s) => ({ ...s, watchlist: data.watchlist }));
    } catch (err) {
      console.error("Failed to fetch watchlist:", err);
    }
  }, []);

  const addTicker = useCallback(async (ticker: string) => {
    try {
      const res = await authFetch(`${API_URL}/watchlist/${ticker}`, {
        method: "POST",
      });
      const data = await res.json();
      await fetchWatchlist();
      return data;
    } catch (err) {
      console.error("Failed to add ticker:", err);
      return null;
    }
  }, [fetchWatchlist]);

  const removeTicker = useCallback(async (ticker: string) => {
    try {
      await authFetch(`${API_URL}/watchlist/${ticker}`, { method: "DELETE" });
      await fetchWatchlist();
    } catch (err) {
      console.error("Failed to remove ticker:", err);
    }
  }, [fetchWatchlist]);

  const triggerAnalysis = useCallback(async (ticker: string) => {
    try {
      const res = await authFetch(`${API_URL}/analyze/${ticker}`, {
        method: "POST",
      });
      return await res.json();
    } catch (err) {
      console.error("Failed to trigger analysis:", err);
      return null;
    }
  }, []);

  // On mount, fetch initial data
  useEffect(() => {
    fetchPortfolio();
    fetchSignals();
    fetchWatchlist();
  }, [fetchPortfolio, fetchSignals, fetchWatchlist]);

  return {
    ...state,
    fetchPortfolio,
    fetchSignals,
    fetchWatchlist,
    addTicker,
    removeTicker,
    triggerAnalysis,
  };
}
