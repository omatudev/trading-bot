import { useCallback, useEffect, useRef, useState } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Input } from "@/components/ui/input";

import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Switch } from "@/components/ui/switch";
import type { Portfolio } from "@/types";

import { API_URL } from "@/config";
import { authFetch } from "@/hooks/useAuth";

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */
interface Props {
  portfolio: Portfolio | null;
  showPositions: boolean;
  onTogglePositions: (v: boolean) => void;
  showHistory: boolean;
  onToggleHistory: (v: boolean) => void;
  showWatchlist: boolean;
  onToggleWatchlist: (v: boolean) => void;
  onSignOut?: () => void;
}

/* ------------------------------------------------------------------ */
/*  Editable row helper                                                */
/* ------------------------------------------------------------------ */
function EditableRow({
  label,
  value,
  onChange,
  suffix,
  icon,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  suffix?: string;
  icon?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <span className="flex items-center gap-2 text-xs text-muted-foreground">
        {icon && <span className="text-sm leading-none">{icon}</span>}
        {label}
      </span>
      <div className="flex items-center gap-1">
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-7 w-16 text-center font-mono text-xs px-1"
        />
        {suffix && (
          <span className="text-[10px] text-muted-foreground w-4">
            {suffix}
          </span>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */
export function ConfigSidebar({
  portfolio,
  showPositions,
  onTogglePositions,
  showHistory,
  onToggleHistory,
  showWatchlist,
  onToggleWatchlist,
  onSignOut,
}: Props) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* ── Editable schedule state ────────────────── */
  const [schedule, setSchedule] = useState({
    preOpen: "9:20",
    open: "9:30",
    mid: "10:00",
    preClose: "3:30",
  });

  /* ── Editable rules state ────────────────────── */
  const [rules, setRules] = useState({
    takeProfit: "10",
    gapSell: "60",
    maxDaysRed: "15",
    minProfitExit: "0.5",
  });

  /* ── Load settings from backend when sidebar opens ── */
  const loadSettings = useCallback(async () => {
    try {
      const res = await authFetch(`${API_URL}/settings`);
      const data = await res.json();
      if (data.schedule) {
        setSchedule({
          preOpen: data.schedule.pre_open ?? "9:20",
          open: data.schedule.open ?? "9:30",
          mid: data.schedule.mid ?? "10:00",
          preClose: data.schedule.pre_close ?? "3:30",
        });
      }
      if (data.rules) {
        setRules({
          takeProfit: String(data.rules.take_profit_pct ?? 10),
          gapSell: String(data.rules.extraordinary_gap_sell_pct ?? 60),
          maxDaysRed: String(data.rules.max_position_days_red ?? 15),
          minProfitExit: String(data.rules.min_profit_to_exit_red ?? 0.5),
        });
      }
    } catch (err) {
      console.error("Failed to load settings:", err);
    }
  }, []);

  useEffect(() => {
    if (open) loadSettings();
  }, [open, loadSettings]);

  /* ── Save settings to backend (debounced 800ms) ── */
  const saveSettings = useCallback(
    (newSchedule: typeof schedule, newRules: typeof rules) => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(async () => {
        setSaving(true);
        try {
          await authFetch(`${API_URL}/settings`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              schedule: {
                pre_open: newSchedule.preOpen,
                open: newSchedule.open,
                mid: newSchedule.mid,
                pre_close: newSchedule.preClose,
              },
              rules: {
                take_profit_pct: parseFloat(newRules.takeProfit) || 10,
                extraordinary_gap_sell_pct: parseFloat(newRules.gapSell) || 60,
                max_position_days_red: parseInt(newRules.maxDaysRed) || 15,
                min_profit_to_exit_red: parseFloat(newRules.minProfitExit) || 0.5,
              },
            }),
          });
        } catch (err) {
          console.error("Failed to save settings:", err);
        } finally {
          setSaving(false);
        }
      }, 800);
    },
    [],
  );

  /* ── Handlers ───────────────────────────────── */
  const updateSchedule = (key: keyof typeof schedule) => (v: string) => {
    const next = { ...schedule, [key]: v };
    setSchedule(next);
    saveSettings(next, rules);
  };

  const updateRule = (key: keyof typeof rules) => (v: string) => {
    const next = { ...rules, [key]: v };
    setRules(next);
    saveSettings(schedule, next);
  };

  /* ── Nav trigger icon ────────────────────────── */
  const TriggerButton = (
    <SheetTrigger asChild>
      <button
        className="relative flex items-center justify-center h-9 w-9 rounded-md hover:bg-white/5 transition-colors"
        aria-label="Abrir configuración"
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>
    </SheetTrigger>
  );

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      {TriggerButton}

      <SheetContent
        side="right"
        className="w-[380px] sm:w-[400px] p-0 flex flex-col"
      >
        <SheetHeader className="px-5 pt-5 pb-3">
          <SheetTitle className="text-base font-semibold tracking-tight flex items-center gap-2">
            Configuración
            {saving && (
              <span className="text-[10px] font-normal text-muted-foreground animate-pulse">
                Guardando...
              </span>
            )}
          </SheetTitle>
        </SheetHeader>

        <ScrollArea className="flex-1 px-5 pb-5">
          <div className="space-y-5">
            {/* ───────── PORTFOLIO STATS ───────── */}
            {portfolio && (
              <section>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                  Portfolio
                </h3>
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Cash</span>
                    <span className="font-medium">
                      ${portfolio.cash.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Invertido</span>
                    <span className="font-medium">
                      ${(portfolio.equity - portfolio.cash).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Buying Power</span>
                    <span className="font-medium">
                      ${portfolio.buying_power.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                  </div>
                </div>
              </section>
            )}

            <Separator className="opacity-30" />

            {/* ───────── PANELES ───────── */}
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                Paneles
              </h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm">Posiciones abiertas</span>
                  <Switch checked={showPositions} onCheckedChange={onTogglePositions} />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm">Historial de operaciones</span>
                  <Switch checked={showHistory} onCheckedChange={onToggleHistory} />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm">Watchlist</span>
                  <Switch checked={showWatchlist} onCheckedChange={onToggleWatchlist} />
                </div>
              </div>
            </section>

            <Separator className="opacity-50" />

            {/* ───────── HORARIOS ───────── */}
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                Horarios
                <span className="ml-1 text-[10px] font-normal normal-case opacity-60">
                  ET
                </span>
              </h3>

              <div className="rounded-md border border-border/40 px-3 divide-y divide-border/30">
                <EditableRow
                  label="Pre-apertura"
                  value={schedule.preOpen}
                  onChange={updateSchedule("preOpen")}
                />
                <EditableRow
                  label="Apertura"
                  value={schedule.open}
                  onChange={updateSchedule("open")}
                />
                <EditableRow
                  label="Mid-morning"
                  value={schedule.mid}
                  onChange={updateSchedule("mid")}
                />
                <EditableRow
                  label="Pre-cierre"
                  value={schedule.preClose}
                  onChange={updateSchedule("preClose")}
                />
              </div>
            </section>

            <Separator className="opacity-50" />

            {/* ───────── REGLAS ───────── */}
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                Reglas de Salida
              </h3>

              <div className="rounded-md border border-border/40 px-3 divide-y divide-border/30">
                <EditableRow
                  label="Take profit"
                  value={rules.takeProfit}
                  onChange={updateRule("takeProfit")}
                  suffix="%"
                />
                <EditableRow
                  label="Gap-up extraordinario"
                  value={rules.gapSell}
                  onChange={updateRule("gapSell")}
                  suffix="%"
                />
                <EditableRow
                  label="Días máx en rojo"
                  value={rules.maxDaysRed}
                  onChange={updateRule("maxDaysRed")}
                  suffix="d"
                />
                <EditableRow
                  label="Salida mín profit"
                  value={rules.minProfitExit}
                  onChange={updateRule("minProfitExit")}
                  suffix="%"
                />
              </div>
            </section>

            {/* Sign out */}
            {onSignOut && (
              <section>
                <Separator className="opacity-30" />
                <button
                  onClick={onSignOut}
                  className="w-full mt-4 py-2 text-xs text-red-400 hover:text-red-300 transition-colors"
                >
                  Sign out
                </button>
              </section>
            )}

            <div className="h-4" />
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
