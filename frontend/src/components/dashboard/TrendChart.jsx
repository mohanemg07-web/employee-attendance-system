import { memo, useState, useEffect, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { EmptyState } from "../ui/empty-state";
import { ChevronDown, Loader2 } from "lucide-react";
import { cn } from "../../lib/utils";
import api from "../../api/client";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";

/* ── Range options ─────────────────────────────────── */
const RANGES = [
  { value: "7d",  label: "Last 7 Days" },
  { value: "14d", label: "Last 14 Days" },
  { value: "30d", label: "Last 30 Days" },
  { value: "1y",  label: "1 Year" },
  { value: "2y",  label: "2 Years" },
  { value: "3y",  label: "3 Years" },
  { value: "all", label: "All Time" },
];

/* ── Format hours for tooltip ──────────────────────── */
function formatHours(v) {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  const h = Math.floor(v);
  const m = Math.round((v - h) * 60);
  return `${h}h ${String(m).padStart(2, "0")}min`;
}

/* ── Tooltip component ─────────────────────────────── */
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0]?.payload || {};
  const v = payload[0]?.value;

  return (
    <div className="rounded-lg border border-border bg-popover/95 backdrop-blur-sm px-3 py-2 text-xs shadow-lg">
      <div className="font-semibold text-foreground">{label}</div>
      <div className="mt-1 flex items-center justify-between gap-4 text-muted-foreground">
        <span>{point.total_hours != null ? "Avg Hours" : "Hours"}</span>
        <span className="font-bold text-primary tabular-nums">{formatHours(v)}</span>
      </div>
      {point.total_hours != null && (
        <>
          <div className="flex items-center justify-between gap-4 text-muted-foreground">
            <span>Total</span>
            <span className="font-medium text-foreground tabular-nums">{formatHours(point.total_hours)}</span>
          </div>
          <div className="flex items-center justify-between gap-4 text-muted-foreground">
            <span>Days</span>
            <span className="font-medium text-foreground tabular-nums">{point.days_worked ?? "—"}</span>
          </div>
        </>
      )}
    </div>
  );
}

/* ── Compact selector ──────────────────────────────── */
function RangeSelect({ value, onChange }) {
  return (
    <div className="relative inline-block">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "appearance-none rounded-md border border-border/50 bg-card/80 backdrop-blur-sm",
          "pl-2 pr-6 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
          "text-muted-foreground cursor-pointer",
          "hover:border-border hover:bg-card transition-colors duration-150",
          "focus:outline-none focus:ring-1 focus:ring-ring/50"
        )}
      >
        {RANGES.map((r) => (
          <option key={r.value} value={r.value}>
            {r.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 h-2.5 w-2.5 text-muted-foreground/50" />
    </div>
  );
}

/* ── Main component ────────────────────────────────── */
export default memo(function TrendChart({ data: initialData }) {
  const [selectedRange, setSelectedRange] = useState("30d");
  const [trendData, setTrendData] = useState(null);
  const [loading, setLoading] = useState(false);

  // For "30d" use initialData (from dashboard), fetch for others
  const isDefault = selectedRange === "30d";
  const initialSafe = Array.isArray(initialData) ? initialData : [];

  useEffect(() => {
    if (isDefault) {
      setTrendData(null); // use initialData
      return;
    }

    let cancelled = false;
    setLoading(true);
    api
      .get("/attendance/me/work-hours-trend", { params: { range: selectedRange } })
      .then((res) => {
        if (!cancelled) {
          setTrendData(res?.data?.points ?? []);
        }
      })
      .catch(() => {
        if (!cancelled) setTrendData([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [selectedRange, isDefault]);

  const activeData = isDefault && trendData === null ? initialSafe : (Array.isArray(trendData) ? trendData : []);
  const has = activeData.length > 0;

  // Dynamic Y-axis max
  const yMax = useMemo(() => {
    if (!has) return 12;
    const max = Math.max(...activeData.map((p) => p.hours || 0));
    return Math.ceil(max / 3) * 3 + 3; // round up to nearest 3, add buffer
  }, [activeData, has]);

  // Generate evenly-spaced tick indices, always including first and last
  const xTicks = useMemo(() => {
    const len = activeData.length;
    if (len <= 1) return activeData.map((_, i) => i);
    const maxTicks = len <= 10 ? len : len <= 20 ? 8 : 7;
    const step = (len - 1) / (maxTicks - 1);
    const indices = new Set();
    for (let i = 0; i < maxTicks; i++) {
      indices.add(Math.round(i * step));
    }
    indices.add(0);
    indices.add(len - 1);
    return [...indices].sort((a, b) => a - b).map((i) => activeData[i]?.date);
  }, [activeData]);

  const rangeLabel = RANGES.find((r) => r.value === selectedRange)?.label ?? selectedRange;

  return (
    <Card className="rounded-xl border border-border shadow-sm transition-shadow duration-200 hover:shadow-md">
      <CardHeader className="px-4 pb-2 pt-4">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <CardTitle className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            Work Hours Trend
          </CardTitle>
          <RangeSelect value={selectedRange} onChange={setSelectedRange} />
        </div>
      </CardHeader>
      <CardContent className="px-2 pb-3 pt-0">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : has ? (
          <div className="h-[220px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={activeData} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
                <defs>
                  <linearGradient id="hoursGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.20} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
                <XAxis
                  dataKey="date"
                  tickLine={false}
                  axisLine={false}
                  fontSize={10}
                  stroke="rgba(148,163,184,0.5)"
                  dy={8}
                  ticks={xTicks}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tickLine={false}
                  axisLine={false}
                  fontSize={10}
                  stroke="rgba(148,163,184,0.5)"
                  width={28}
                  domain={[0, yMax]}
                  tickFormatter={(v) => `${v}h`}
                />
                <Tooltip content={<ChartTooltip />} cursor={{ stroke: "rgba(59,130,246,0.15)", strokeWidth: 24 }} />
                <Area
                  type="monotone"
                  dataKey="hours"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  fill="url(#hoursGradient)"
                  dot={false}
                  activeDot={{
                    r: 4,
                    fill: "#3b82f6",
                    stroke: "#ffffff",
                    strokeWidth: 2,
                    filter: "drop-shadow(0 0 4px rgba(59,130,246,0.4))",
                  }}
                  animationDuration={250}
                  animationEasing="ease-out"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <EmptyState title="No chart data" description="Not enough logs for this range." className="py-8" />
        )}
      </CardContent>
    </Card>
  );
});
