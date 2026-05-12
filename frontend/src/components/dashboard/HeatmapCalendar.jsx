import { useMemo, useState, useRef, memo, useCallback, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { EmptyState } from "../ui/empty-state";
import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSunday } from "date-fns";
import { cn } from "../../lib/utils";
import { ChevronDown, Loader2 } from "lucide-react";
import api from "../../api/client";

const STATUS_META = {
  PRESENT: { label: "Present", className: "bg-emerald-500",   ring: "ring-emerald-400/40" },
  LATE:    { label: "Late",    className: "bg-amber-500",     ring: "ring-amber-400/40" },
  ABSENT:  { label: "Absent",  className: "bg-rose-500",      ring: "ring-rose-400/40" },
  LEAVE:   { label: "Leave",   className: "bg-violet-500",    ring: "ring-violet-400/40" },
  WEEKEND: { label: "Sunday",  className: "bg-slate-500/50",  ring: "ring-slate-400/20" },
  HOLIDAY: { label: "Holiday", className: "bg-slate-500/50",  ring: "ring-slate-400/20" },
  NONE:    { label: "No Data", className: "border border-border/50 bg-muted/30", ring: "" },
};

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function normalizeStatus(raw, isSun) {
  if (isSun) return "WEEKEND";
  const s = String(raw || "").toUpperCase().trim().replace(/\s+/g, "_");
  if (s === "ON_LEAVE") return "LEAVE";
  if (s === "PRESENT") return "PRESENT";
  if (s === "LATE") return "LATE";
  if (s === "ABSENT") return "ABSENT";
  if (s === "LEAVE") return "LEAVE";
  if (s === "HOLIDAY") return "HOLIDAY";
  return "NONE";
}

/* ── Compact dropdown selector ─────────────────────── */
function MiniSelect({ value, options, onChange, className }) {
  return (
    <div className={cn("relative inline-block", className)}>
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
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 h-2.5 w-2.5 text-muted-foreground/50" />
    </div>
  );
}

export default memo(function HeatmapCalendar({ logs: initialLogs }) {
  const now = new Date();
  const [selectedMonth, setSelectedMonth] = useState(now.getMonth()); // 0-indexed
  const [selectedYear, setSelectedYear] = useState(now.getFullYear());
  const [heatmapLogs, setHeatmapLogs] = useState(null);
  const [loading, setLoading] = useState(false);
  const [hoveredIdx, setHoveredIdx] = useState(-1);
  const gridRef = useRef(null);

  // Is the currently selected month the same as the initial (dashboard) month?
  const isCurrentMonth = selectedMonth === now.getMonth() && selectedYear === now.getFullYear();

  // Use initialLogs for the current month, fetch for others
  const activeLogs = isCurrentMonth && heatmapLogs === null
    ? (Array.isArray(initialLogs) ? initialLogs : [])
    : (Array.isArray(heatmapLogs) ? heatmapLogs : []);

  // Fetch heatmap data when month/year changes (non-current month)
  useEffect(() => {
    if (isCurrentMonth) {
      setHeatmapLogs(null); // reset to use initialLogs
      return;
    }

    let cancelled = false;
    setLoading(true);
    api
      .get("/attendance/me/heatmap", {
        params: { month: selectedMonth + 1, year: selectedYear },
      })
      .then((res) => {
        if (!cancelled) {
          setHeatmapLogs(res?.data?.logs ?? []);
        }
      })
      .catch(() => {
        if (!cancelled) setHeatmapLogs([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [selectedMonth, selectedYear, isCurrentMonth]);

  // Build calendar grid
  const monthDate = useMemo(
    () => new Date(selectedYear, selectedMonth, 1),
    [selectedMonth, selectedYear]
  );

  const { days, padding } = useMemo(() => {
    const start = startOfMonth(monthDate);
    const end = endOfMonth(monthDate);
    const all = eachDayOfInterval({ start, end });
    const pad = Array.from({ length: start.getDay() }).map(() => null);
    return { days: all, padding: pad };
  }, [monthDate]);

  const logMap = useMemo(() => {
    const map = new Map();
    activeLogs.forEach((l) => {
      try {
        if (l?.log_date) {
          const key = l.log_date.slice(0, 10);
          map.set(key, l);
        }
      } catch {}
    });
    return map;
  }, [activeLogs]);

  const getLogForDay = useCallback(
    (d) => logMap.get(format(d, "yyyy-MM-dd")) || null,
    [logMap]
  );

  const hasData = activeLogs.length > 0;
  const today = new Date();
  const DAY_LABELS = ["S", "M", "T", "W", "T", "F", "S"];

  // Year options: currentYear-3 → currentYear+1
  const yearOptions = useMemo(() => {
    const cur = now.getFullYear();
    const years = [];
    for (let y = cur - 3; y <= cur + 1; y++) {
      years.push({ value: y, label: String(y) });
    }
    return years;
  }, []);

  const monthOptions = MONTH_NAMES.map((name, i) => ({
    value: i,
    label: name.slice(0, 3).toUpperCase(),
  }));

  return (
    <Card className="rounded-xl border border-border shadow-sm transition-shadow duration-200 hover:shadow-md">
      <CardHeader className="px-3 pb-1 pt-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <CardTitle className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            Attendance Heatmap — {MONTH_NAMES[selectedMonth]} {selectedYear}
          </CardTitle>
          <div className="flex items-center gap-1.5">
            <MiniSelect
              value={selectedMonth}
              options={monthOptions}
              onChange={(v) => setSelectedMonth(Number(v))}
            />
            <MiniSelect
              value={selectedYear}
              options={yearOptions}
              onChange={(v) => setSelectedYear(Number(v))}
            />
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-3 pb-3 pt-1">
        {loading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : hasData ? (
          <div className="flex items-start gap-4">
            <div className="flex-1 min-w-0">
              {/* Day headers */}
              <div className="grid grid-cols-7 gap-[2px] text-center mb-[2px]">
                {DAY_LABELS.map((d, i) => (
                  <div key={i} className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/50 py-0.5">
                    {d}
                  </div>
                ))}
              </div>

              {/* Calendar grid */}
              <div ref={gridRef} className="grid grid-cols-7 gap-[2px]">
                {padding.map((_, i) => (
                  <div key={`pad-${i}`} className="aspect-square" />
                ))}

                {days.map((day, idx) => {
                  const sun = isSunday(day);
                  const log = getLogForDay(day);
                  const statusKey = normalizeStatus(log?.status, sun);
                  const meta = STATUS_META[statusKey] || STATUS_META.NONE;
                  const isFuture = day > today;
                  const isHovered = hoveredIdx === idx;

                  return (
                    <div key={day.toISOString()} className="relative">
                      <button
                        type="button"
                        className={cn(
                          "aspect-square w-full rounded-[3px] outline-none transition-all duration-150",
                          "hover:scale-110 hover:ring-2 hover:z-10",
                          "focus-visible:ring-2 focus-visible:ring-ring",
                          meta.ring,
                          isFuture && "opacity-15"
                        )}
                        onMouseEnter={() => setHoveredIdx(idx)}
                        onMouseLeave={() => setHoveredIdx(-1)}
                        onFocus={() => setHoveredIdx(idx)}
                        onBlur={() => setHoveredIdx(-1)}
                      >
                        <div className={cn("h-full w-full rounded-[3px]", meta.className)} />
                        <span className="sr-only">
                          {format(day, "MMM d")} {meta.label}
                        </span>
                      </button>

                      {/* Tooltip */}
                      {isHovered && (
                        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 z-50 pointer-events-none animate-in fade-in duration-100">
                          <div className="rounded-lg border border-border bg-popover/95 backdrop-blur-md px-2.5 py-1.5 text-[10px] shadow-lg whitespace-nowrap">
                            <div className="font-semibold text-foreground">{format(day, "MMM d, yyyy")}</div>
                            <div className="flex items-center justify-between gap-3 mt-0.5 text-muted-foreground">
                              <span>Status</span>
                              <span className="font-medium text-foreground">{meta.label}</span>
                            </div>
                            {log?.gross_work_hrs ? (
                              <div className="flex items-center justify-between gap-3 text-muted-foreground">
                                <span>Hours</span>
                                <span className="font-medium text-foreground tabular-nums">{log.gross_work_hrs}</span>
                              </div>
                            ) : null}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Legend — compact */}
            <div className="hidden sm:flex flex-col gap-1 pt-3 shrink-0">
              {["PRESENT", "LATE", "ABSENT", "LEAVE", "WEEKEND"].map((k) => (
                <div key={k} className="flex items-center gap-1.5 text-[9px] text-muted-foreground/70">
                  <div className={cn("h-2 w-2 rounded-[2px] shrink-0", STATUS_META[k].className)} />
                  <span className="whitespace-nowrap">{STATUS_META[k].label}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <EmptyState title="No heatmap data" description="No entries for this month." className="py-4" />
        )}

        {/* Mobile legend */}
        <div className="mt-2 sm:hidden flex flex-wrap gap-2.5">
          {["PRESENT", "LATE", "ABSENT", "LEAVE", "WEEKEND"].map((k) => (
            <div key={k} className="flex items-center gap-1 text-[9px] text-muted-foreground/70">
              <div className={cn("h-2 w-2 rounded-[2px]", STATUS_META[k].className)} />
              <span>{STATUS_META[k].label}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
});
