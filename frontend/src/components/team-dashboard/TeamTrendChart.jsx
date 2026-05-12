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
  { value: "7d",   label: "Last 7 Days" },
  { value: "14d",  label: "Last 14 Days" },
  { value: "30d",  label: "Last 30 Days" },
  { value: "60d",  label: "Last 60 Days" },
  { value: "120d", label: "Last 120 Days" },
  { value: "180d", label: "Last 180 Days" },
  { value: "1y",   label: "1 Year" },
  { value: "2y",   label: "2 Years" },
  { value: "3y",   label: "3 Years" },
  { value: "all",  label: "All Time" },
];

/* ── Tooltip ───────────────────────────────────────── */
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload || payload.length === 0) return null;
  const a = payload.find((p) => p.dataKey === "attendancePct")?.value;
  return (
    <div className="rounded-lg border border-border bg-popover/95 backdrop-blur-sm px-3 py-2 text-xs shadow-lg">
      <div className="font-semibold text-foreground">{label}</div>
      <div className="mt-1 text-muted-foreground">
        <div className="flex items-center justify-between gap-5">
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />Attendance
          </span>
          <span className="font-bold text-foreground tabular-nums">{typeof a === "number" ? `${a.toFixed(1)}%` : "—"}</span>
        </div>
      </div>
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
          <option key={r.value} value={r.value}>{r.label}</option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 h-2.5 w-2.5 text-muted-foreground/50" />
    </div>
  );
}

/* ── Main component ────────────────────────────────── */
export default memo(function TeamTrendChart({ data: initialData }) {
  const [selectedRange, setSelectedRange] = useState("30d");
  const [trendData, setTrendData] = useState(null);
  const [loading, setLoading] = useState(false);

  // For "30d" use initialData passed from dashboard
  const isDefault = selectedRange === "30d";
  const initialSafe = useMemo(() => {
    const arr = Array.isArray(initialData) ? initialData : [];
    // Ensure ascending date order
    return [...arr].sort((a, b) => {
      const da = a?.date || a?.date_label || "";
      const db = b?.date || b?.date_label || "";
      return da < db ? -1 : da > db ? 1 : 0;
    });
  }, [initialData]);

  useEffect(() => {
    if (isDefault) {
      setTrendData(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    api
      .get("/attendance/team/attendance-trend", { params: { range: selectedRange } })
      .then((res) => {
        if (!cancelled) setTrendData(res?.data?.points ?? []);
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

  // Generate evenly-spaced tick labels, always including first and last
  const xTicks = useMemo(() => {
    const len = activeData.length;
    if (len <= 1) return activeData.map((p) => p?.date);
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

  return (
    <Card className="rounded-xl border border-border shadow-sm transition-shadow duration-200 hover:shadow-md h-full">
      <CardHeader className="px-4 pb-1 pt-4">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <CardTitle className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            Team Attendance Trend
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
              <AreaChart data={activeData} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
                <defs>
                  <linearGradient id="teamAttGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.01} />
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
                  width={42}
                  domain={[0, 100]}
                  ticks={[0, 20, 40, 60, 80, 100]}
                  tickFormatter={(v) => `${v}%`}
                />
                <Tooltip content={<ChartTooltip />} cursor={{ stroke: "rgba(59,130,246,0.1)", strokeWidth: 20 }} />
                <Area
                  type="monotone"
                  dataKey="attendancePct"
                  name="Attendance %"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  fill="url(#teamAttGradient)"
                  dot={false}
                  activeDot={{ r: 4, fill: "#3b82f6", stroke: "#fff", strokeWidth: 2, filter: "drop-shadow(0 0 3px rgba(59,130,246,0.4))" }}
                  animationDuration={250}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <EmptyState title="No trend data" description="Not enough data to display team trends." className="py-6" />
        )}
      </CardContent>
    </Card>
  );
});
