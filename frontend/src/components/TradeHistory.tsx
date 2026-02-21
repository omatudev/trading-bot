import { useEffect, useState, useCallback } from "react";
import { API_URL } from "@/config";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";

interface Trade {
  id: number;
  ticker: string;
  action: string;
  side: string;
  qty: number;
  price: number;
  pnl_pct: number | null;
  pnl_usd: number | null;
  reason: string | null;
  created_at: string | null;
}

const actionColors: Record<string, string> = {
  BUY: "bg-green-500/10 text-green-500 hover:bg-green-500/20",
  SELL: "bg-red-500/10 text-red-500 hover:bg-red-500/20",
  TAKE_PROFIT: "bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20",
  EXIT_RED_ZONE: "bg-orange-500/10 text-orange-500 hover:bg-orange-500/20",
  CLOSE_EOD: "bg-yellow-500/10 text-yellow-500 hover:bg-yellow-500/20",
  EXTRAORDINARY_GAP_SELL: "bg-purple-500/10 text-purple-400 hover:bg-purple-500/20",
};

const actionLabels: Record<string, string> = {
  BUY: "Compra",
  SELL: "Venta",
  TAKE_PROFIT: "Take Profit",
  EXIT_RED_ZONE: "Salida Rojo",
  CLOSE_EOD: "Cierre EOD",
  EXTRAORDINARY_GAP_SELL: "Gap Extra.",
};

function formatDateTime(dateStr?: string | null): string {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("es-MX", {
      month: "short",
      day: "numeric",
    }) + " " + d.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return "—";
  }
}

export function TradeHistory() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchTrades = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/trades`);
      if (res.ok) {
        const data = await res.json();
        setTrades(data.trades ?? []);
      }
    } catch {
      // silent — will retry on next interval
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTrades();
    const interval = setInterval(fetchTrades, 30_000); // refresh every 30s
    return () => clearInterval(interval);
  }, [fetchTrades]);

  return (
    <Card className="border-0 bg-transparent shadow-none">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          HISTORIAL DE OPERACIONES
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <p className="text-sm text-muted-foreground py-4 text-center">
            Cargando...
          </p>
        ) : trades.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">
            Sin operaciones registradas
          </p>
        ) : (
          <ScrollArea className="h-[300px]">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[70px]">Fecha</TableHead>
                  <TableHead className="w-[60px]">Ticker</TableHead>
                  <TableHead>Acción</TableHead>
                  <TableHead className="text-right">Cant.</TableHead>
                  <TableHead className="text-right">Precio</TableHead>
                  <TableHead className="text-right">P&L %</TableHead>
                  <TableHead className="text-right">P&L $</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trades.map((t) => {
                  const hasPnl = t.pnl_pct !== null && t.pnl_pct !== undefined;
                  const isPositive = hasPnl && (t.pnl_pct ?? 0) >= 0;
                  return (
                    <TableRow key={t.id}>
                      <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                        {formatDateTime(t.created_at)}
                      </TableCell>
                      <TableCell className="font-bold">{t.ticker}</TableCell>
                      <TableCell>
                        <Badge
                          variant="secondary"
                          className={actionColors[t.action] ?? ""}
                        >
                          {actionLabels[t.action] ?? t.action}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">{t.qty}</TableCell>
                      <TableCell className="text-right">
                        ${t.price.toFixed(2)}
                      </TableCell>
                      <TableCell
                        className={`text-right font-medium ${
                          !hasPnl
                            ? "text-muted-foreground"
                            : isPositive
                              ? "text-green-500"
                              : "text-red-500"
                        }`}
                      >
                        {hasPnl
                          ? `${isPositive ? "+" : ""}${t.pnl_pct!.toFixed(1)}%`
                          : "—"}
                      </TableCell>
                      <TableCell
                        className={`text-right font-medium ${
                          t.pnl_usd === null
                            ? "text-muted-foreground"
                            : (t.pnl_usd ?? 0) >= 0
                              ? "text-green-500"
                              : "text-red-500"
                        }`}
                      >
                        {t.pnl_usd !== null
                          ? `${(t.pnl_usd ?? 0) >= 0 ? "+" : ""}$${(t.pnl_usd ?? 0).toFixed(2)}`
                          : "—"}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
