import { useEffect, useMemo, useState, memo, useCallback, useRef } from "react";
import api from "../api/client";
import { Badge } from "../components/ui/badge";
import { Skeleton, SkeletonCard } from "../components/ui/skeleton";
import { EmptyState } from "../components/ui/empty-state";
import { Alert } from "../components/ui/alert";
import StatCard from "../components/dashboard/StatCard";
import TrendChart from "../components/dashboard/TrendChart";
import HeatmapCalendar from "../components/dashboard/HeatmapCalendar";
import SummaryCards from "../components/dashboard/SummaryCards";
import InsightsPanel from "../components/dashboard/InsightsPanel";
import LogsTable from "../components/dashboard/LogsTable";
import { format, formatDistanceToNowStrict, parseISO } from "date-fns";
import { CalendarCheck, Clock, RefreshCcw, TrendingDown, TrendingUp } from "lucide-react";
import { useCachedFetch } from "../lib/cache";

/** Parse API interval string "HH:MM:SS" or "HH:MM" → decimal hours for charts. */
function grossWorkHrsToDecimalHours(hrsStr) {
  if (!hrsStr || typeof hrsStr !== "string") return 0;
  const parts = hrsStr.trim().split(":");
  if (parts.length < 2) return 0;
  const h = parseInt(parts[0], 10);
  const m = parseInt(parts[1], 10) || 0;
  const s = parseInt(parts[2], 10) || 0;
  if (Number.isNaN(h)) return 0;
  return h + m / 60 + s / 3600;
}

function normalizeStatusBadgeVariant(status) {
  const s = String(status || "").toLowerCase().replace(/\s+/g, "_");
  if (s === "present") return "present";
  if (s === "absent") return "absent";
  if (s === "late") return "late";
  if (s === "on_leave" || s === "leave") return "leave";
  if (s === "weekend") return "weekend";
  if (s === "holiday") return "holiday";
  return "secondary";
}

function normalizeTodayStatus(today) {
  const t = today && typeof today === "object" ? today : {};
  const raw = t.status ?? t.today_status ?? null;
  const s = String(raw || "").trim().toUpperCase();
  if (s === "PRESENT" || s === "ABSENT" || s === "LATE" || s === "LEAVE" || s === "ON_LEAVE" || s === "ON LEAVE") {
    return s === "ON_LEAVE" || s === "ON LEAVE" ? "LEAVE" : s;
  }
  return "NO LOG";
}

export default function EmployeeDashboard() {
  const [lastUpdated, setLastUpdated] = useState(null);
  const [nowTick, setNowTick] = useState(Date.now());
  const prevDataRef = useRef(null);
  const tickRef = useRef(null);

  const fetchDashboardData = useCallback(async () => {
    const res = await api.get("/attendance/me/dashboard");
    return res?.data ?? null;
  }, []);

  const { data, loading, stale, error, refetch } = useCachedFetch(
    "employee-dashboard-v4",
    fetchDashboardData,
    [],
    { ttl: 120_000 }
  );

  // Track lastUpdated only when data reference actually changes
  useEffect(() => {
    if (data && data !== prevDataRef.current) {
      prevDataRef.current = data;
      setLastUpdated(new Date());
    }
  }, [data]);

  // Singleton 60s tick for "last updated X ago" label — one timer only
  useEffect(() => {
    if (tickRef.current) return; // already running
    tickRef.current = setInterval(() => setNowTick(Date.now()), 60_000);
    return () => {
      clearInterval(tickRef.current);
      tickRef.current = null;
    };
  }, []);

  const safe = useMemo(() => {
    const d = data && typeof data === "object" ? data : {};
    const today = d.today && typeof d.today === "object" ? d.today : {};
    const monthly_summary = d.monthly_summary ?? d.monthly ?? d.monthlySummary ?? {};
    const score = d.score ?? {};

    const insights = Array.isArray(d?.insights) ? d.insights : [];
    const logs = d?.logs ?? d?.recent_logs ?? [];
    const safeLogs = Array.isArray(logs) ? logs : [];

    const trend = Array.isArray(d?.trend_data) ? d.trend_data : null;

    return { today, monthly_summary, score, insights, logs: safeLogs, trend_data: trend };
  }, [data]);

  const trendData = useMemo(() => {
    if (Array.isArray(safe.trend_data) && safe.trend_data.length > 0) {
      return [...safe.trend_data]
        .sort((a, b) => {
          const da = a?.date || a?.date_label || a?.day || "";
          const db = b?.date || b?.date_label || b?.day || "";
          return da < db ? -1 : da > db ? 1 : 0;
        })
        .map((p) => {
          const label = p?.date_label || p?.date || p?.day;
          const hours = typeof p?.hours === "number" ? p.hours : grossWorkHrsToDecimalHours(p?.gross_work_hrs);
          return label ? { date: String(label), hours: Number(hours || 0) } : null;
        })
        .filter(Boolean);
    }

    // Fallback: derive from logs — sort ascending by log_date
    return [...safe.logs]
      .sort((a, b) => (a?.log_date || "") < (b?.log_date || "") ? -1 : 1)
      .map((log) => {
        try {
          if (!log?.log_date) return null;
          return {
            date: format(parseISO(log.log_date), "MMM dd"),
            hours: grossWorkHrsToDecimalHours(log?.gross_work_hrs),
          };
        } catch {
          return null;
        }
      })
      .filter((x) => x && x.hours > 0)
      .slice(-30);
  }, [safe.logs, safe.trend_data]);

  const monthlyPct = useMemo(() => {
    const s = safe.monthly_summary && typeof safe.monthly_summary === "object" ? safe.monthly_summary : {};
    // Use backend-computed present_percent as single source of truth
    const pct =
      s.present_percent ??
      s.monthly_present_percent ??
      // Fallback: (PRESENT + LATE) / working_days — mirrors backend formula exactly
      (Number(s.working_days || 0) > 0
        ? (100 * (Number(s.total_present || s.present || 0) + Number(s.total_late || s.late || 0))) / Number(s.working_days || 1)
        : null);
    if (pct == null) return null;
    const n = Number(pct);
    return Number.isFinite(n) ? n : null;
  }, [safe.monthly_summary]);

  const monthlyTrend = useMemo(() => {
    const s = safe.monthly_summary && typeof safe.monthly_summary === "object" ? safe.monthly_summary : {};
    const v = s.present_percent_trend ?? s.trend ?? s.delta_percent;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }, [safe.monthly_summary]);

  const lastUpdatedLabel = useMemo(() => {
    if (!lastUpdated) return null;
    // use nowTick for relative updates
    void nowTick;
    return formatDistanceToNowStrict(lastUpdated, { addSuffix: true });
  }, [lastUpdated, nowTick]);

  const todayStatus = useMemo(() => normalizeTodayStatus(safe.today), [safe.today]);
  const todayHours = useMemo(() => {
    const raw = safe.today?.work_hours ?? safe.today?.gross_work_hrs;
    if (!raw || raw === "—") return "—";
    const str = String(raw);
    // Handle HH:MM:SS or HH:MM format
    const parts = str.split(":");
    if (parts.length >= 2) {
      const h = parseInt(parts[0], 10);
      const m = parseInt(parts[1], 10);
      if (!Number.isNaN(h) && !Number.isNaN(m)) {
        return `${h}h ${String(m).padStart(2, "0")}min`;
      }
    }
    // Handle decimal hours (e.g. 9.5)
    const num = parseFloat(str);
    if (Number.isFinite(num)) {
      const h = Math.floor(num);
      const m = Math.round((num - h) * 60);
      return `${h}h ${String(m).padStart(2, "0")}min`;
    }
    return str;
  }, [safe.today]);
  const hasSummaryData = useMemo(() => {
    const s = safe.monthly_summary && typeof safe.monthly_summary === "object" ? safe.monthly_summary : {};
    const vals = [s.total_present, s.present, s.total_absent, s.absent, s.total_late, s.late, s.total_leave, s.leave, s.total_days, s.total];
    return vals.some((v) => Number(v ?? 0) > 0);
  }, [safe.monthly_summary]);
  const hasScore = safe.score?.overall != null && Number.isFinite(Number(safe.score.overall));
  const isEmpty =
    !loading &&
    !error &&
    safe.logs.length === 0 &&
    trendData.length === 0 &&
    !hasSummaryData &&
    !hasScore &&
    safe.insights.length === 0 &&
    todayStatus === "NO LOG";

  // Show skeletons ONLY on first load with no cached data
  const showSkeleton = loading && !data;

  if (showSkeleton) {
    return (
      <div className="space-y-4 pb-6">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div className="space-y-1.5">
            <Skeleton className="h-7 w-48" />
            <Skeleton className="h-3.5 w-36" />
          </div>
          <Skeleton className="h-8 w-40 rounded-full" />
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <SkeletonCard key={i} />
          ))}
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Skeleton className="h-[260px] w-full rounded-xl" />
          <Skeleton className="h-[260px] w-full rounded-xl" />
        </div>

        <Skeleton className="h-[80px] w-full rounded-xl" />
        <Skeleton className="h-[240px] w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-5 pb-6 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">My Dashboard</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">Attendance overview</p>
        </div>

        <div className="flex items-center gap-3">
          {stale && (
            <span className="text-[10px] font-medium text-amber-500 uppercase tracking-wider animate-pulse">
              Updating…
            </span>
          )}
          <div className="flex items-center gap-2 rounded-full border border-border bg-secondary/30 px-3 py-2 text-xs font-semibold text-muted-foreground">
            <span>Last updated:</span>
            <span className="text-foreground/80">{lastUpdated ? format(lastUpdated, "HH:mm") : "—"}</span>
            {lastUpdatedLabel ? <span className="text-muted-foreground">({lastUpdatedLabel})</span> : null}
          </div>

          <button
            type="button"
            onClick={refetch}
            disabled={loading}
            className="inline-flex items-center justify-center rounded-full border border-border bg-card p-2 shadow-sm transition-transform hover:scale-[1.04] disabled:opacity-50"
            aria-label="Refresh dashboard"
            title="Refresh"
          >
            <RefreshCcw className={`h-4 w-4 text-muted-foreground ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Error */}
      {error ? (
        <Alert
          variant="critical"
          title="Couldn't load dashboard"
          description={
            <div className="flex items-center justify-between gap-4">
              <div className="text-sm">{error?.message || String(error)}</div>
              <button
                type="button"
                onClick={refetch}
                className="rounded-full border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground shadow-sm transition-transform hover:scale-[1.03]"
              >
                Retry
              </button>
            </div>
          }
        />
      ) : null}

      {/* Empty */}
      {isEmpty ? (
        <EmptyState
          title="No dashboard data yet"
          description="Once your attendance data is available, your trends and logs will show up here."
          className="rounded-2xl border border-border bg-card shadow-sm"
        />
      ) : null}

      {/* KPI cards */}
      {!isEmpty ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatCard
            title="Attendance Score"
            value={safe.score?.overall != null ? `${Number(safe.score.overall).toFixed(1)}%` : "—"}
            subtitle="This month"
            valueClassName="text-primary"
          />

          <StatCard
            title="Today Status"
            value={
              <div className="mt-1 inline-flex items-center gap-2">
                <Badge variant={normalizeStatusBadgeVariant(todayStatus)}>
                  {todayStatus}
                </Badge>
              </div>
            }
            icon={CalendarCheck}
          />

          <StatCard title="Work Hours Today" value={todayHours} icon={Clock} />

          <StatCard
            title="Monthly Present %"
            value={monthlyPct != null ? `${monthlyPct.toFixed(1)}%` : "—"}
            icon={monthlyTrend != null ? (monthlyTrend >= 0 ? TrendingUp : TrendingDown) : TrendingUp}
            right={
              <span className={monthlyTrend != null ? (monthlyTrend >= 0 ? "text-emerald-600" : "text-rose-600") : "text-muted-foreground"}>
                {monthlyTrend != null ? `${monthlyTrend >= 0 ? "+" : ""}${monthlyTrend.toFixed(1)}%` : "0%"}
              </span>
            }
          />
        </div>
      ) : null}

      {/* Chart section */}
      {!isEmpty ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <TrendChart data={trendData} />
          <HeatmapCalendar logs={safe.logs} />
        </div>
      ) : null}

      {/* Monthly summary */}
      {!isEmpty ? (
        <div className="space-y-2.5">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Monthly Summary</div>
          <SummaryCards summary={safe.monthly_summary} />
        </div>
      ) : null}

      {/* Insights */}
      {!isEmpty ? <InsightsPanel insights={safe.insights} /> : null}

      {/* Logs */}
      {!isEmpty ? <LogsTable logs={safe.logs} /> : null}
    </div>
  );
}
