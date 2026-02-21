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
import type { Position } from "@/types";

interface Props {
  positions: Position[];
  onTickerClick?: (ticker: string) => void;
  activeCharts?: string[];
}

export function PositionsTable({ positions, onTickerClick, activeCharts = [] }: Props) {
  return (
    <Card className="border-0 bg-transparent shadow-none">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          POSICIONES ABIERTAS
        </CardTitle>
      </CardHeader>
      <CardContent>
        {positions.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">
            Sin posiciones abiertas
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[80px]">Ticker</TableHead>
                <TableHead className="text-right">Cant.</TableHead>
                <TableHead className="text-right">Entrada</TableHead>
                <TableHead className="text-right">Actual</TableHead>
                <TableHead className="text-right">Valor</TableHead>
                <TableHead className="text-right">P&L</TableHead>
                <TableHead className="text-right">P&L %</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {positions.map((pos) => {
                const isPositive = pos.unrealized_pnl >= 0;
                return (
                  <TableRow key={pos.ticker}>
                    <TableCell
                      className={`font-bold cursor-pointer select-none transition-colors hover:text-blue-400 ${
                        activeCharts.includes(pos.ticker) ? "text-blue-400" : ""
                      }`}
                      onClick={() => onTickerClick?.(pos.ticker)}
                    >
                      <span className="flex items-center gap-1">
                        {pos.ticker}
                        <svg
                          className={`w-3 h-3 opacity-40 transition-transform ${activeCharts.includes(pos.ticker) ? "rotate-180" : ""}`}
                          viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                        >
                          <polyline points="6 9 12 15 18 9" />
                        </svg>
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      {pos.qty}
                    </TableCell>
                    <TableCell className="text-right">
                      ${pos.avg_entry.toFixed(2)}
                    </TableCell>
                    <TableCell className="text-right">
                      ${pos.current_price.toFixed(2)}
                    </TableCell>
                    <TableCell className="text-right">
                      ${pos.market_value.toLocaleString("en-US", {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </TableCell>
                    <TableCell
                      className={`text-right font-medium ${
                        isPositive ? "text-green-500" : "text-red-500"
                      }`}
                    >
                      {isPositive ? "+" : ""}$
                      {pos.unrealized_pnl.toFixed(2)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Badge
                        variant={isPositive ? "default" : "destructive"}
                        className={
                          isPositive
                            ? "bg-green-500/10 text-green-500 hover:bg-green-500/20"
                            : ""
                        }
                      >
                        {isPositive ? "+" : ""}
                        {pos.unrealized_pnl_pct.toFixed(2)}%
                      </Badge>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
