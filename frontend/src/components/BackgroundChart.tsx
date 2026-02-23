import { useEffect, useState, useCallback, useRef } from "react";
import { API_URL } from "@/config";
import { authFetch } from "@/hooks/useAuth";

const W = 1000;
const H = 400;
const PAD_Y = 0.15;
const SAMPLES = 200; // fixed number of points for morphing
const ANIM_MS = 600;

interface Props {
  ticker: string | null;
  period: string;
  onChangeCalculated?: (pct: number | null) => void;
  onHoverPoint?: (point: { value: number; date: string } | null) => void;
}

interface DataPoint {
  date: string;
  value: number;
}

/** Resample an array of numbers to exactly `n` points via linear interpolation */
function resample(arr: number[], n: number): number[] {
  if (arr.length === 0) return new Array(n).fill(H / 2);
  if (arr.length === 1) return new Array(n).fill(arr[0]);
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const t = (i / (n - 1)) * (arr.length - 1);
    const lo = Math.floor(t);
    const hi = Math.min(lo + 1, arr.length - 1);
    const frac = t - lo;
    out.push(arr[lo] * (1 - frac) + arr[hi] * frac);
  }
  return out;
}

/** Convert normalized Y values (0..1 range already mapped to SVG coords) into path strings */
function buildPaths(ys: number[]): { line: string; area: string } {
  const line = ys
    .map((y, i) => {
      const x = (i / (ys.length - 1)) * W;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const area = `${line} L${W},${H} L0,${H} Z`;
  return { line, area };
}

/** Map raw values to SVG Y coordinates */
function valuesToYCoords(values: number[]): number[] {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  return values.map((v) => {
    const normalized = (v - min) / range;
    return H - (normalized * H * (1 - 2 * PAD_Y) + H * PAD_Y);
  });
}

export function BackgroundChart({ ticker, period, onChangeCalculated, onHoverPoint }: Props) {
  const [linePath, setLinePath] = useState("");
  const [areaPath, setAreaPath] = useState("");
  const [isUp, setIsUp] = useState(true);
  const [dataPoints, setDataPoints] = useState<DataPoint[]>([]);
  const [hover, setHover] = useState<{ x: number; y: number; idx: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Keep track of current Y samples for morphing
  const currentYsRef = useRef<number[]>(new Array(SAMPLES).fill(H / 2));
  const animRef = useRef<number>(0);

  const fetchAndBuild = useCallback(async () => {
    try {
      let points: DataPoint[] = [];

      if (ticker) {
        const periodConfig: Record<string, { days: number; tf: string }> = {
          "1D": { days: 2, tf: "5min" },
          "1W": { days: 8, tf: "15min" },
          "1M": { days: 35, tf: "hour" },
          "3M": { days: 95, tf: "day" },
          "6M": { days: 185, tf: "day" },
          "1A": { days: 370, tf: "day" },
          all: { days: 1825, tf: "day" },
        };
        const { days, tf } = periodConfig[period] ?? { days: 30, tf: "day" };
        const res = await authFetch(`${API_URL}/bars/${ticker}?days=${days}&tf=${tf}`);
        if (!res.ok) return;
        const data = await res.json();
        points = (data.bars ?? []).map((b: { timestamp: string; close: number }) => {
          const ts = b.timestamp;
          const date = tf === "day"
            ? ts.substring(0, 10)
            : new Date(ts).toLocaleString("en-US", {
                month: "short", day: "numeric",
                hour: "2-digit", minute: "2-digit",
                hour12: true,
              });
          return { date, value: b.close };
        });
      } else {
        const res = await authFetch(`${API_URL}/portfolio/history?period=${period}`);
        if (!res.ok) return;
        const data = await res.json();
        const history: { timestamp: number; equity: number }[] = data.history ?? [];
        const byDay = new Map<string, number>();
        for (const p of history) {
          const day = new Date(p.timestamp * 1000).toISOString().split("T")[0];
          byDay.set(day, p.equity);
        }
        points = Array.from(byDay.entries())
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([day, equity]) => ({ date: day, value: equity }));
      }

      if (points.length < 2) {
        onChangeCalculated?.(null);
        // Animate to flat line
        const flatYs = new Array(SAMPLES).fill(H / 2);
        animateTo(flatYs);
        setDataPoints([]);
        return;
      }

      setDataPoints(points);
      const values = points.map((p) => p.value);
      const first = values[0];
      const last = values[values.length - 1];
      const changePct = first !== 0 ? ((last - first) / first) * 100 : 0;
      onChangeCalculated?.(changePct);
      setIsUp(last >= first);

      // Compute target Y coords and resample to fixed count
      const rawYs = valuesToYCoords(values);
      const targetYs = resample(rawYs, SAMPLES);
      animateTo(targetYs);
    } catch (e) {
      console.error("BackgroundChart error:", e);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker, period, onChangeCalculated]);

  /** Animate from current Y samples to target Y samples */
  const animateTo = useCallback((targetYs: number[]) => {
    // Cancel any running animation
    if (animRef.current) cancelAnimationFrame(animRef.current);

    const fromYs = [...currentYsRef.current];
    const startTime = performance.now();

    const step = (now: number) => {
      const elapsed = now - startTime;
      const rawT = Math.min(elapsed / ANIM_MS, 1);
      // ease-out cubic
      const t = 1 - Math.pow(1 - rawT, 3);

      const interpolated = fromYs.map((from, i) => from + (targetYs[i] - from) * t);
      currentYsRef.current = interpolated;

      const { line, area } = buildPaths(interpolated);
      setLinePath(line);
      setAreaPath(area);

      if (rawT < 1) {
        animRef.current = requestAnimationFrame(step);
      } else {
        currentYsRef.current = targetYs;
      }
    };

    animRef.current = requestAnimationFrame(step);
  }, []);

  useEffect(() => {
    fetchAndBuild();
    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
  }, [fetchAndBuild]);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!containerRef.current || dataPoints.length < 2) return;
      const rect = containerRef.current.getBoundingClientRect();
      const xPct = (e.clientX - rect.left) / rect.width;
      const idx = Math.round(xPct * (dataPoints.length - 1));
      const clampedIdx = Math.max(0, Math.min(dataPoints.length - 1, idx));
      setHover({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
        idx: clampedIdx,
      });
      onHoverPoint?.(dataPoints[clampedIdx]);
    },
    [dataPoints, onHoverPoint]
  );

  const handleMouseLeave = useCallback(() => {
    setHover(null);
    onHoverPoint?.(null);
  }, [onHoverPoint]);

  const gradientId = isUp ? "bgGradientUp" : "bgGradientDown";
  const lineColor = isUp ? "rgba(34,197,94,0.6)" : "rgba(239,68,68,0.6)";
  const fillTop = isUp ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)";
  const dotColor = isUp ? "rgb(34,197,94)" : "rgb(239,68,68)";

  const hoveredPoint = hover ? dataPoints[hover.idx] : null;
  const crosshairXPct = hover && dataPoints.length > 1
    ? (hover.idx / (dataPoints.length - 1)) * 100
    : 0;

  return (
    <div
      ref={containerRef}
      className="absolute inset-0"
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{ cursor: hover ? "crosshair" : "default" }}
    >
      <svg
        viewBox="0 0 1000 400"
        preserveAspectRatio="none"
        className="w-full h-full pointer-events-none"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={fillTop} />
            <stop offset="100%" stopColor="rgba(0,0,0,0)" />
          </linearGradient>
        </defs>
        {areaPath && (
          <path d={areaPath} fill={`url(#${gradientId})`} />
        )}
        {linePath && (
          <path
            d={linePath}
            fill="none"
            stroke={lineColor}
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>

      {/* Crosshair vertical line */}
      {hover && hoveredPoint && (
        <div
          className="absolute top-0 bottom-0 w-px opacity-30 pointer-events-none"
          style={{
            left: `${crosshairXPct}%`,
            backgroundColor: dotColor,
          }}
        />
      )}
    </div>
  );
}
