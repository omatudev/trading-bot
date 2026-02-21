import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import type { TickerProfile } from "@/types";

interface Props {
  watchlist: TickerProfile[];
  onAdd: (ticker: string) => Promise<unknown>;
  onRemove: (ticker: string) => Promise<void>;
  onAnalyze: (ticker: string) => Promise<unknown>;
}

export function WatchlistPanel({ watchlist, onAdd, onRemove, onAnalyze }: Props) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [analyzingTicker, setAnalyzingTicker] = useState<string | null>(null);

  const handleAdd = async () => {
    const ticker = input.trim().toUpperCase();
    if (!ticker) return;
    setLoading(true);
    try {
      await onAdd(ticker);
      setInput("");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleAdd();
  };

  const handleAnalyze = async (ticker: string) => {
    setAnalyzingTicker(ticker);
    try {
      await onAnalyze(ticker);
    } finally {
      setAnalyzingTicker(null);
    }
  };

  return (
    <Card className="border-0 bg-transparent shadow-none">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Watchlist
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <Input
            placeholder="Ej: NVDA, AAPL, TSLA..."
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            onKeyDown={handleKeyDown}
            className="font-mono text-sm h-8"
            disabled={loading}
          />
          <Button
            onClick={handleAdd}
            disabled={!input.trim() || loading}
            size="sm"
            className="shrink-0 h-8 text-xs"
          >
            {loading ? "..." : "Agregar"}
          </Button>
        </div>

        {watchlist.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-3">
            Agrega tickers para empezar
          </p>
        ) : (
          <div className="space-y-1.5">
            {watchlist.map((profile) => (
              <div
                key={profile.ticker}
                className="group flex items-center justify-between rounded-md px-3 py-2 hover:bg-white/5 transition-colors"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-bold text-sm font-mono">
                    {profile.ticker}
                  </span>
                  <Badge
                    variant="outline"
                    className="text-[10px] px-1.5 py-0 shrink-0"
                  >
                    {profile.threshold_extraordinary_pct.toFixed(1)}%
                  </Badge>
                  <span className="text-[10px] text-muted-foreground truncate">
                    {profile.days_gap_up}/{profile.days_analyzed} gap-up
                  </span>
                </div>
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-[11px]"
                    onClick={() => handleAnalyze(profile.ticker)}
                    disabled={analyzingTicker === profile.ticker}
                  >
                    {analyzingTicker === profile.ticker ? "..." : "Analizar"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 w-6 p-0 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10"
                    onClick={() => onRemove(profile.ticker)}
                  >
                    ✕
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
