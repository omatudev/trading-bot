import { useState, useCallback, useRef, useEffect } from "react";
import NumberFlow from "@number-flow/react";
import { Toaster } from "sonner";
import { Analytics } from "@vercel/analytics/react";
import { SpeedInsights } from "@vercel/speed-insights/react";
import { useTradingBot } from "@/hooks/useTradingBot";
import { useAuth, authFetch } from "@/hooks/useAuth";
import { BackgroundChart } from "@/components/BackgroundChart";
import { API_URL } from "@/config";
import { Suspense, lazy } from "react";
const PositionsTable = lazy(() => import("@/components/PositionsTable"));
const TradeHistory = lazy(() => import("@/components/TradeHistory"));
const WatchlistPanel = lazy(() => import("@/components/WatchlistPanel"));
import { ConfigSidebar } from "@/components/ConfigSidebar";

const PERIODS = [
  { label: "1D", value: "1D" },
  { label: "1S", value: "1W" },
  { label: "1M", value: "1M" },
  { label: "3M", value: "3M" },
  { label: "6M", value: "6M" },
  { label: "1A", value: "1A" },
  { label: "All", value: "all" },
] as const;

/* ── Mobile period dropdown ──────────── */
function PeriodDropdown({
  activePeriod,
  onSelect,
}: {
  activePeriod: string;
  onSelect: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const activeLabel = PERIODS.find((p) => p.value === activePeriod)?.label ?? "1M";

  useEffect(() => {
    const handler = (e: MouseEvent | TouchEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
    };
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded text-muted-foreground hover:text-foreground transition-colors"
      >
        {activeLabel}
        <svg width="10" height="6" viewBox="0 0 10 6" fill="none" className={`transition-transform ${open ? "rotate-180" : ""}`}>
          <path d="M1 1L5 5L9 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 bg-background/80 backdrop-blur-md rounded-lg py-1 min-w-[80px] z-50">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              onClick={() => {
                onSelect(p.value);
                setOpen(false);
              }}
              className={`block w-full text-left px-3 py-1.5 text-xs transition-colors ${
                activePeriod === p.value
                  ? "text-foreground font-medium"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Login screen ─────────────────────── */
function LoginScreen() {
  const { signIn } = useAuth();
  const btnRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const renderButton = () => {
      if (btnRef.current && window.google?.accounts) {
        window.google.accounts.id.renderButton(btnRef.current, {
          theme: "filled_black",
          size: "large",
          shape: "pill",
          text: "signin_with",
        });
      }
    };

    if (window.google?.accounts) {
      renderButton();
    } else {
      const script = document.getElementById("google-gis-script");
      script?.addEventListener("load", renderButton);
      return () => script?.removeEventListener("load", renderButton);
    }
  }, [signIn]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center text-foreground gap-6">
      <p className="text-sm text-muted-foreground tracking-widest uppercase">Private access</p>
      <div ref={btnRef} />
    </div>
  );
}

function App() {
  const { user, loading, signOut } = useAuth();
  const {
    portfolio,
    positions,
    watchlist,
    connected,
    lastUpdate,
    addTicker,
    removeTicker,
    triggerAnalysis,
  } = useTradingBot();

  const [showPositions, setShowPositions] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showWatchlist, setShowWatchlist] = useState(false);

  const [activePeriod, setActivePeriod] = useState("1M");
  const [searchTicker, setSearchTicker] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [tickerPrice, setTickerPrice] = useState<number | null>(null);
  const [chartChangePct, setChartChangePct] = useState<number | null>(null);
  const [hoverPoint, setHoverPoint] = useState<{ value: number; date: string } | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  /* ── Global spacebar → focus search ── */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === " " && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  /* ── Search handler ─────────────────── */
  const handleSearch = useCallback(
    async (value: string) => {
      const ticker = value.trim().toUpperCase();
      if (!ticker) {
        setSearchTicker(null);
        setTickerPrice(null);
        return;
      }
      setSearchTicker(ticker);
      try {
        const res = await authFetch(
          `${API_URL}/bars/${ticker}?days=5`
        );
        if (res.ok) {
          const data = await res.json();
          const bars = data.bars ?? [];
          if (bars.length > 0) {
            setTickerPrice(bars[bars.length - 1].close);
          } else {
            setTickerPrice(null);
          }
        }
      } catch {
        /* ignore */
      }
    },
    []
  );

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      handleSearch(searchInput);
    }
    if (e.key === "Backspace" && searchInput) {
      e.preventDefault();
      clearSearch();
    }
    if (e.key === "Escape") {
      setSearchInput("");
      setSearchTicker(null);
      setTickerPrice(null);
    }
  };

  const clearSearch = () => {
    setSearchInput("");
    setSearchTicker(null);
    setTickerPrice(null);
  };

  /* ── Toggle chart for positions table ── */
  const toggleChart = useCallback((ticker: string) => {
    setSearchInput(ticker);
    setSearchTicker(ticker);
    authFetch(`${API_URL}/bars/${ticker}?days=5`)
      .then((r) => r.json())
      .then((data) => {
        const bars = data.bars ?? [];
        if (bars.length > 0) setTickerPrice(bars[bars.length - 1].close);
      })
      .catch(() => {});
  }, []);

  /* ── Display values ──────────────────── */
  const baseValue = searchTicker
    ? tickerPrice ?? portfolio?.equity ?? null
    : portfolio
      ? portfolio.equity
      : null;

  const numericValue = hoverPoint ? hoverPoint.value : baseValue;

  const isPositive = portfolio ? portfolio.daily_pnl >= 0 : true;

  if (loading) {
    return <div className="min-h-screen" />;
  }

  if (!user) {
    return <LoginScreen />;
  }

  return (
    <div className="relative min-h-screen text-foreground overflow-hidden">
      {/* Background chart — fills entire viewport */}
      <BackgroundChart ticker={searchTicker} period={activePeriod} onChangeCalculated={setChartChangePct} onHoverPoint={setHoverPoint} />

      {/* Overlay content — on top of chart, transparent to mouse */}
      <div className="relative z-10 flex flex-col min-h-screen pointer-events-none">
        {/* ── Header bar ──────────────────── */}
        <header className="px-6 py-4 pointer-events-auto">
          <div className="flex items-center justify-between">
            {/* Left: Period selector */}
            <PeriodDropdown activePeriod={activePeriod} onSelect={setActivePeriod} />

            {/* Center: Search bar */}
            <div className="flex items-center gap-1.5 font-mono text-sm text-muted-foreground">
              <div className="flex items-center gap-0">
                <span className="opacity-50">[</span>
                <input
                  ref={searchRef}
                  type="text"
                  size={searchInput.length || 1}
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
                  onKeyDown={handleSearchKeyDown}
                  placeholder=""
                  className="bg-transparent border-0 px-0 text-center text-foreground font-mono text-sm focus:outline-none"
                />
                <span className="opacity-50">]</span>
              </div>
              {searchTicker && (
                <button
                  onClick={clearSearch}
                  className="opacity-40 hover:opacity-100 transition-opacity hover:cursor-pointer text-red-400 text-xs border border-white/10 rounded px-1.5 py-0.5 hover:border-red-400/40"
                >
                  ×
                </button>
              )}
            </div>

            {/* Right: Status + Sidebar */}
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              {lastUpdate && (
                <span className="opacity-50">
                  {new Date(lastUpdate).toLocaleTimeString("en-US", {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                    hour12: true,
                  })}
                </span>
              )}
              <span
                className={`flex items-center gap-1.5 ${
                  connected ? "text-green-500" : "text-red-500"
                }`}
              >
                <span className="relative flex h-2 w-2">
                  {connected && (
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
                  )}
                  <span
                    className={`relative inline-flex h-2 w-2 rounded-full ${
                      connected ? "bg-green-500" : "bg-red-500"
                    }`}
                  />
                </span>
              </span>

              <ConfigSidebar
                portfolio={portfolio}
                showPositions={showPositions}
                onTogglePositions={setShowPositions}
                showHistory={showHistory}
                onToggleHistory={setShowHistory}
                showWatchlist={showWatchlist}
                onToggleWatchlist={setShowWatchlist}
                onSignOut={signOut}
              />
            </div>
          </div>
        </header>

        {/* ── Centered value display ─────── */}
        <div className="flex-1 flex flex-col items-center justify-center pointer-events-none">
          {/* Main price / equity */}
          <div className="text-7xl font-bold tracking-tight">
            {numericValue !== null ? (
              <span className="inline-flex items-baseline gap-2">
                <NumberFlow
                  value={numericValue}
                  format={{ style: "decimal", minimumFractionDigits: 2, maximumFractionDigits: 2 }}
                  transformTiming={{ duration: 500, easing: "ease-out" }}
                  spinTiming={{ duration: 500, easing: "ease-out" }}
                />
                <span className="text-3xl opacity-40">USD</span>
              </span>
            ) : (
              <span className="opacity-30">—</span>
            )}
          </div>

          {/* Period % change or hovered date */}
          {hoverPoint ? (
            <p className="text-sm font-medium mt-1 text-muted-foreground opacity-60">
              {hoverPoint.date}
            </p>
          ) : chartChangePct !== null ? (
            <div
              className={`text-sm font-medium mt-1 flex items-center gap-1 ${
                chartChangePct >= 0 ? "text-green-500" : "text-red-500"
              }`}
            >
              {chartChangePct >= 0 ? "▲" : "▼"}
              <NumberFlow
                value={chartChangePct / 100}
                format={{ style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "always" }}
                transformTiming={{ duration: 400, easing: "ease-out" }}
                spinTiming={{ duration: 400, easing: "ease-out" }}
              />
            </div>
          ) : null}

          {/* P&L (only for portfolio, not ticker) */}
          {!searchTicker && portfolio && (
            <div
              className={`text-sm font-medium mt-1 flex items-center gap-1 ${
                isPositive ? "text-green-500" : "text-red-500"
              }`}
            >
              {isPositive ? "▲" : "▼"}
              <NumberFlow
                value={portfolio.daily_pnl}
                format={{ style: "decimal", minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "always" }}
                transformTiming={{ duration: 400, easing: "ease-out" }}
                spinTiming={{ duration: 400, easing: "ease-out" }}
              />
              <span>USD</span>
              <span>(</span>
              <NumberFlow
                value={portfolio.daily_pnl_pct / 100}
                format={{ style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "always" }}
                transformTiming={{ duration: 400, easing: "ease-out" }}
                spinTiming={{ duration: 400, easing: "ease-out" }}
              />
              <span>)</span>
            </div>
          )}
        </div>



        {/* ── Overlay panels ─────────────── */}
        {(showWatchlist || showPositions || showHistory) && (
          <div className="absolute bottom-14 left-0 right-0 max-h-[50vh] overflow-y-auto px-6 pb-2 space-y-4 bg-gradient-to-t from-background/95 via-background/80 to-transparent pt-16 pointer-events-auto">
            <Suspense fallback={<div className="text-center text-xs text-muted-foreground py-8">Cargando panel...</div>}>
              {showWatchlist && (
                <WatchlistPanel
                  watchlist={watchlist}
                  onAdd={addTicker}
                  onRemove={removeTicker}
                  onAnalyze={triggerAnalysis}
                />
              )}
              {showPositions && (
                <PositionsTable
                  positions={positions}
                  onTickerClick={toggleChart}
                  activeCharts={searchTicker ? [searchTicker] : []}
                />
              )}
              {showHistory && <TradeHistory />}
            </Suspense>
          </div>
        )}
      </div>

      <Toaster theme="dark" position="bottom-right" richColors closeButton />
      <Analytics />
      <SpeedInsights />
    </div>
  );
}

export default App;
