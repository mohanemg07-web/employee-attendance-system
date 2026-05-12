import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { format, formatDistanceToNowStrict } from "date-fns";
import { RefreshCcw } from "lucide-react";
import api from "../api/client";
import { Skeleton, SkeletonCard } from "../components/ui/skeleton";
import { EmptyState } from "../components/ui/empty-state";
import { Alert } from "../components/ui/alert";
import TeamStats from "../components/team-dashboard/TeamStats";
import TeamTrendChart from "../components/team-dashboard/TeamTrendChart";
import TopPerformers from "../components/team-dashboard/TopPerformers";
import RiskAlerts from "../components/team-dashboard/RiskAlerts";
import TeamTable from "../components/team-dashboard/TeamTable";
import EmployeeModal from "../components/team-dashboard/EmployeeModal";
import { useCachedFetch } from "../lib/cache";

export default function ManagerDashboard() {
  const [selectedMember, setSelectedMember] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [nowTick, setNowTick] = useState(Date.now());
  const prevDataRef = useRef(null);
  const tickRef = useRef(null);

  const fetchDashboardData = useCallback(async () => {
    const now = new Date();
    const targetDate = now.toISOString().slice(0, 10);
    const month = now.getMonth() + 1;
    const year = now.getFullYear();

    const res = await api.get("/attendance/team/dashboard", {
      params: { target_date: targetDate, month, year },
    });

    const dashboardData = res?.data ?? {};
    return {
      dashboard: dashboardData,
      monthly: { records: dashboardData.members ?? [] },
    };
  }, []);

  const { data, loading, stale, error, refetch } = useCachedFetch(
    "team-dashboard-v2",
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

  // Singleton 60s tick for "last updated X ago" label
  useEffect(() => {
    if (tickRef.current) return;
    tickRef.current = setInterval(() => setNowTick(Date.now()), 60_000);
    return () => {
      clearInterval(tickRef.current);
      tickRef.current = null;
    };
  }, []);

  const safe = useMemo(() => {
    const root = data && typeof data === "object" ? data : {};
    const d = root.dashboard && typeof root.dashboard === "object" ? root.dashboard : {};
    const monthly = root.monthly && typeof root.monthly === "object" ? root.monthly : {};

    const teamSize = Number(d.team_size ?? 0) || 0;

    // Today's summary — prefer backend's today_summary, fallback to root-level fields
    const ts = d.today_summary && typeof d.today_summary === "object" ? d.today_summary : {};
    const team_stats = {
      team_members: Number(ts.team_members ?? d.team_size ?? teamSize) || 0,
      team_members_present: Number(ts.team_members_present ?? (Number(ts.present ?? d.total_present ?? 0) + Number(ts.late ?? d.total_late ?? 0))) || 0,
      present: Number(ts.present ?? d.total_present ?? 0) || 0,
      absent: Number(ts.absent ?? d.total_absent ?? 0) || 0,
      late: Number(ts.late ?? d.total_late ?? 0) || 0,
      attendance_rate: Number(ts.attendance_rate ?? d.attendance_rate ?? 0) || 0,
    };

    const trend_data = Array.isArray(d.trend_data) ? d.trend_data : [];
    const top_performers = Array.isArray(d.top_performers) ? d.top_performers : [];
    const risk_alerts = d.risk_alerts ?? {};

    const dashboardMembers = Array.isArray(d.members) ? d.members : [];
    const monthlyMembers = Array.isArray(monthly.records) ? monthly.records : [];
    const sourceMembers = dashboardMembers.length > 0 ? dashboardMembers : monthlyMembers;

    // Normalize members to keys used by TeamTable/Modal
    const normalizedTeam = sourceMembers.map((m) => {
      const present = Number(m?.present ?? m?.total_present ?? 0) || 0;
      const absent = Number(m?.absent ?? m?.total_absent ?? 0) || 0;
      const late = Number(m?.late ?? m?.total_late ?? 0) || 0;
      const workingDays = Number(m?.working_days ?? 0) || 0;
      // Use backend score directly — no frontend re-derivation
      const backendScore = Number(m?.score ?? m?.attendance_score ?? 0) || 0;
      return {
        ...m,
        id: m?.id ?? m?.employee_id,
        name: m?.name ?? m?.full_name ?? m?.employee_name,
        department: m?.department ?? m?.team,
        present,
        absent,
        late,
        working_days: workingDays,
        total_days: workingDays,
        score: backendScore,
      };
    });

    return {
      team_stats,
      trend_data,
      top_performers,
      risk_alerts,
      team_size: teamSize,
      team: normalizedTeam,
    };
  }, [data]);

  const trendChartData = useMemo(() => {
    const safeTrend = Array.isArray(safe.trend_data) ? safe.trend_data : [];
    if (safeTrend.length > 0) {
      return safeTrend
        .map((p) => {
          const date = p?.date_label ?? p?.date ?? p?.day;
          const attendancePct = Number(p?.attendance_pct ?? p?.attendance ?? p?.attendance_rate);
          return date
            ? {
                date: String(date),
                attendancePct: Number.isFinite(attendancePct) ? attendancePct : 0,
              }
            : null;
        })
        .filter(Boolean);
    }
    return [];
  }, [safe.trend_data]);

  const performers = useMemo(() => {
    const fromApi = safe.top_performers;
    if (fromApi.length > 0) return fromApi;
    return [...safe.team]
      .sort((a, b) => Number(b?.score ?? 0) - Number(a?.score ?? 0))
      .slice(0, 5)
      .map((m) => ({ ...m, name: m?.name ?? m?.full_name }));
  }, [safe.team, safe.top_performers]);

  const computedRiskAlerts = useMemo(() => {
    const apiAlerts = safe.risk_alerts && typeof safe.risk_alerts === "object" ? safe.risk_alerts : {};
    // If backend returned employee lists, use them directly
    if (Array.isArray(apiAlerts.low_attendance_employees) || Array.isArray(apiAlerts.frequent_late_employees) || Array.isArray(apiAlerts.missing_logs_employees)) {
      return apiAlerts;
    }

    // Fallback: compute from team data with employee arrays
    const lowList = safe.team.filter((m) => Number(m?.score ?? 0) < 75).map((m) => ({
      employee_id: m?.id, employee_name: m?.name, department: m?.department,
      attendance_pct: Number(m?.score ?? 0), present: Number(m?.present ?? 0),
      late: Number(m?.late ?? 0), absent: Number(m?.absent ?? 0),
    }));
    const lateList = safe.team.filter((m) => Number(m?.late ?? 0) >= 3).map((m) => ({
      employee_id: m?.id, employee_name: m?.name, department: m?.department,
      late_count: Number(m?.late ?? 0),
    }));
    const missList = safe.team.filter((m) => m?.status === "NO_LOG").map((m) => ({
      employee_id: m?.id, employee_name: m?.name, department: m?.department,
      status: "NO_LOG",
    }));
    return {
      low_attendance: lowList.length,
      frequent_late: lateList.length,
      missing_logs: missList.length,
      low_attendance_employees: lowList,
      frequent_late_employees: lateList,
      missing_logs_employees: missList,
    };
  }, [safe.risk_alerts, safe.team]);

  const lastUpdatedLabel = useMemo(() => {
    if (!lastUpdated) return null;
    void nowTick;
    return formatDistanceToNowStrict(lastUpdated, { addSuffix: true });
  }, [lastUpdated, nowTick]);

  const isEmpty = !error && safe.team_size === 0 && safe.team.length === 0 && trendChartData.length === 0;

  // Show skeletons ONLY on first load with no cached data
  const showSkeleton = loading && !data;

  if (showSkeleton) {
    return (
      <div className="space-y-4 pb-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div className="space-y-1.5">
            <Skeleton className="h-7 w-48" />
            <Skeleton className="h-3.5 w-64" />
          </div>
          <Skeleton className="h-8 w-72 rounded-full" />
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {[1, 2, 3, 4, 5].map((i) => (
            <SkeletonCard key={i} />
          ))}
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2.2fr_1fr]">
          <Skeleton className="h-[260px] w-full rounded-xl" />
          <div className="space-y-3">
            <Skeleton className="h-[150px] w-full rounded-xl" />
            <Skeleton className="h-[100px] w-full rounded-xl" />
          </div>
        </div>

        <Skeleton className="h-[280px] w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-4 pb-4 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">Team Dashboard</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">Track your team's attendance and performance</p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
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
          title="Couldn't load team dashboard"
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
          title="No team data yet"
          description="Once your team has attendance records, trends and insights will show up here."
          className="rounded-2xl border border-border bg-card shadow-sm"
        />
      ) : null}

      {/* KPI cards */}
      {!isEmpty ? <TeamStats stats={safe.team_stats} /> : null}

      {/* Main grid: chart + right panels */}
      {!isEmpty ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2.2fr_1fr]">
          <TeamTrendChart data={trendChartData} />
          <div className="space-y-3">
            <TopPerformers performers={performers} onSelect={(m) => setSelectedMember(m)} />
            <RiskAlerts alerts={computedRiskAlerts} />
          </div>
        </div>
      ) : null}

      {/* Team table */}
      {!isEmpty ? <TeamTable team={safe.team} onSelect={(m) => setSelectedMember(m)} /> : null}

      {/* Employee modal */}
      <EmployeeModal open={Boolean(selectedMember)} member={selectedMember} onClose={() => setSelectedMember(null)} />
    </div>
  );
}
