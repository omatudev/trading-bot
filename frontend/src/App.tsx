import { useState, useCallback } from "react";
import NumberFlow from "@number-flow/react";
import { Toaster } from "sonner";
import { useTradingBot } from "@/hooks/useTradingBot";
import { BackgroundChart } from "@/components/BackgroundChart";
import { API_URL } from "@/config";
import { PositionsTable } from "@/components/PositionsTable";
import { TradeHistory } from "@/components/TradeHistory";
import { WatchlistPanel } from "@/components/WatchlistPanel";
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

function App() {
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
        const res = await fetch(
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
    fetch(`${API_URL}/bars/${ticker}?days=5`)
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

  return (
    <div className="relative min-h-screen text-foreground overflow-hidden">
      {/* Background chart — fills entire viewport */}
      <BackgroundChart ticker={searchTicker} period={activePeriod} onChangeCalculated={setChartChangePct} onHoverPoint={setHoverPoint} />

      {/* Overlay content — on top of chart, transparent to mouse */}
      <div className="relative z-10 flex flex-col min-h-screen pointer-events-none">
        {/* ── Header bar ──────────────────── */}
        <header className="px-6 py-4 pointer-events-auto">
          <div className="flex items-center justify-between">
            {/* Left: Title */}
            <h1 className="text-lg font-semibold tracking-tight opacity-60">
              Aragi Bot
            </h1>

            {/* Center: Search bar */}
            <div className="flex-1 flex justify-center px-8">
              <div className="relative w-full max-w-sm">
                <input
                  type="text"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
                  onKeyDown={handleSearchKeyDown}
                  placeholder="..."
                  className="w-full bg-white/5 border-0 rounded-full px-4 py-1.5 text-sm font-mono text-center placeholder:text-muted-foreground/50 focus:outline-none focus:bg-white/10 transition-colors"
                />
                {searchTicker && (
                  <button
                    onClick={clearSearch}
                    className="absolute right-3 top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-red-500/10 outline outline-red-500/30 hover:scale-150 transition-transform duration-150 hover:cursor-pointer hover:bg-red-500/20"
                  />
                )}
              </div>
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

        {/* ── Bottom: Period selector ─────── */}
        <div className="px-6 py-4 pointer-events-auto">
          <div className="flex items-center gap-1">
            {PERIODS.map((p) => (
              <button
                key={p.value}
                onClick={() => setActivePeriod(p.value)}
                className={`px-2.5 py-1 text-xs rounded transition-colors ${
                  activePeriod === p.value
                    ? "bg-white/10 text-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground hover:bg-white/5"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* ── Overlay panels ─────────────── */}
        {(showWatchlist || showPositions || showHistory) && (
          <div className="absolute bottom-14 left-0 right-0 max-h-[50vh] overflow-y-auto px-6 pb-2 space-y-4 bg-gradient-to-t from-background/95 via-background/80 to-transparent pt-16 pointer-events-auto">
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
          </div>
        )}
      </div>

      <Toaster theme="dark" position="bottom-right" richColors closeButton />
    </div>
  );
}

export default App;
