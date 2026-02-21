/**
 * TypeScript types shared between frontend components.
 * Mirror the backend API response shapes.
 */

export interface Portfolio {
  equity: number;
  cash: number;
  buying_power: number;
  portfolio_value: number;
  daily_pnl: number;
  daily_pnl_pct: number;
}

export interface Position {
  ticker: string;
  qty: number;
  avg_entry: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  side: string;
}

export interface Signal {
  id?: number;
  ticker: string;
  signal: "BUY" | "SELL" | "HOLD";
  confidence: number;
  reasoning: string;
  catalysts: string | string[];
  catalyst_type?: string;
  sentiment_score?: number;
  risk_level?: string;
  analysis_window?: string;
  created_at?: string;
}

export interface TickerProfile {
  ticker: string;
  analysis_date: string | null;
  days_analyzed: number;
  days_gap_up: number;
  gap_up_frequency_pct: number;
  gap_up_avg_pct: number;
  gap_up_max_pct: number;
  gap_up_p75_pct: number;
  threshold_extraordinary_pct: number;
  next_recalc_date: string | null;
}

export interface WsMessage {
  type: string;
  portfolio?: Portfolio;
  positions?: Position[];
  signals?: Signal[];
  timestamp?: string;
  [key: string]: unknown;
}
