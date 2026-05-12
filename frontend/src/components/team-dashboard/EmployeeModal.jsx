import { useEffect, useMemo } from "react";
import { X } from "lucide-react";
import { Card, CardContent } from "../ui/card";
import { Badge } from "../ui/badge";
import { EmptyState } from "../ui/empty-state";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip } from "recharts";
import { format, parseISO } from "date-fns";
import { cn } from "../../lib/utils";

function safeParseDate(v) {
  try {
    return v ? parseISO(v) : null;
  } catch {
    return null;
  }
}

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

function statusVariant(status) {
  const s = String(status || "").toLowerCase();
  if (s === "present") return "present";
  if (s === "absent") return "absent";
  if (s === "late") return "late";
  if (s === "on_leave" || s === "on leave" || s === "leave") return "leave";
  return "secondary";
}

function MiniTooltip({ active, payload, label }) {
  if (!active || !payload || payload.length === 0) return null;
  const v = payload[0]?.value;
  return (
    <div className="rounded-xl border border-border bg-popover px-3 py-2 text-xs shadow-md">
      <div className="font-semibold text-foreground">{label}</div>
      <div className="mt-1 flex items-center justify-between gap-6 text-muted-foreground">
        <span>Hours</span>
        <span className="font-medium text-foreground">{typeof v === "number" ? v.toFixed(2) : "—"}</span>
      </div>
    </div>
  );
}

function Stat({ label, value, tone }) {
  const tones = {
    default: "bg-card",
    present: "bg-emerald-500/5 border-emerald-500/15",
    absent: "bg-rose-500/5 border-rose-500/15",
    late: "bg-amber-500/5 border-amber-500/15",
    total: "bg-secondary/20 border-border/60",
  };
  return (
    <Card className={cn("rounded-2xl border border-border shadow-sm", tones[tone] || tones.default)}>
      <CardContent className="p-4">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
        <div className="mt-2 text-2xl font-semibold tracking-tight text-foreground">{value ?? "—"}</div>
      </CardContent>
    </Card>
  );
}

export default function EmployeeModal({ open, member, onClose }) {
  const m = member && typeof member === "object" ? member : null;

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, open]);

  const logs = useMemo(() => {
    const raw = m?.logs ?? m?.recent_logs ?? [];
    return Array.isArray(raw) ? raw : [];
  }, [m]);

  const chartData = useMemo(() => {
    const trend = Array.isArray(m?.trend_data) ? m.trend_data : null;
    if (trend && trend.length > 0) {
      return trend
        .map((p) => {
          const label = p?.date_label || p?.date || p?.day;
          const hours = typeof p?.hours === "number" ? p.hours : grossWorkHrsToDecimalHours(p?.gross_work_hrs);
          return label ? { date: String(label), hours: Number(hours || 0) } : null;
        })
        .filter(Boolean);
    }
    return logs
      .map((l) => {
        const d = safeParseDate(l?.log_date);
        if (!d) return null;
        return { date: format(d, "MMM dd"), hours: grossWorkHrsToDecimalHours(l?.gross_work_hrs) };
      })
      .filter((x) => x && x.hours > 0)
      .slice(-30);
  }, [logs, m]);

  if (!open) return null;

  const score = m?.score ?? m?.attendance_score;
  const present = m?.present ?? m?.total_present;
  const absent = m?.absent ?? m?.total_absent;
  const late = m?.late ?? m?.total_late;
  const totalDays = m?.working_days ?? m?.total_days ?? m?.days ?? (present != null || absent != null || late != null ? (Number(present || 0) + Number(absent || 0) + Number(late || 0)) : null);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose?.();
      }}
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-5xl overflow-hidden rounded-2xl border border-border bg-card shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-border bg-secondary/20 p-6">
          <div className="min-w-0">
            <div className="truncate text-lg font-semibold text-foreground">{m?.name ?? m?.full_name ?? "Employee"}</div>
            <div className="mt-1 text-sm text-muted-foreground">
              {m?.role ?? m?.designation ?? "Employee"}{m?.department ? ` • ${m.department}` : ""}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className="text-3xl font-semibold tracking-tight text-foreground">
                {score != null ? `${Number(score).toFixed(1)}%` : "—"}
              </div>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Attendance Score</div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-border bg-card p-2 shadow-sm transition-transform hover:scale-[1.04]"
              aria-label="Close"
            >
              <X className="h-4 w-4 text-muted-foreground" />
            </button>
          </div>
        </div>

        <div className="max-h-[78vh] overflow-y-auto p-6">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
            <Stat label="Score" value={score != null ? `${Number(score).toFixed(1)}%` : "—"} tone="default" />
            <Stat label="Present" value={present ?? "—"} tone="present" />
            <Stat label="Absent" value={absent ?? "—"} tone="absent" />
            <Stat label="Late" value={late ?? "—"} tone="late" />
            <Stat label="Total Working Days" value={totalDays ?? "—"} tone="total" />
          </div>

          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card className="rounded-2xl">
              <CardContent className="p-5">
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Attendance Trend (Last 30 Days)
                </div>
                <div className="mt-4 h-[220px] w-full">
                  {chartData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
                        <CartesianGrid stroke="rgba(0,0,0,0.06)" vertical={false} />
                        <XAxis dataKey="date" tickLine={false} axisLine={false} fontSize={12} stroke="rgba(0,0,0,0.35)" />
                        <YAxis tickLine={false} axisLine={false} fontSize={12} stroke="rgba(0,0,0,0.35)" width={32} domain={[0, 12]} />
                        <Tooltip content={<MiniTooltip />} />
                        <Line type="monotone" dataKey="hours" stroke="#3b82f6" strokeWidth={2.5} dot={false} activeDot={{ r: 5 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <EmptyState title="No trend data" className="py-10" />
                  )}
                </div>
              </CardContent>
            </Card>

            <Card className="rounded-2xl">
              <CardContent className="p-5">
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Recent Logs</div>
                <div className="mt-4 overflow-x-auto rounded-2xl border border-border">
                  <table className="w-full text-sm">
                    <thead className="bg-secondary/40 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                      <tr>
                        <th className="px-4 py-3 text-left">Date</th>
                        <th className="px-4 py-3 text-left">First In</th>
                        <th className="px-4 py-3 text-left">Last Out</th>
                        <th className="px-4 py-3 text-left">Hours</th>
                        <th className="px-4 py-3 text-left">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border bg-card">
                      {logs.slice(0, 10).map((l, idx) => {
                        const d = safeParseDate(l?.log_date);
                        const fi = safeParseDate(l?.first_in);
                        const lo = safeParseDate(l?.last_out);
                        return (
                          <tr key={idx} className="transition-colors hover:bg-secondary/30">
                            <td className="px-4 py-3 font-medium text-foreground">{d ? format(d, "MMM dd, yyyy") : "—"}</td>
                            <td className="px-4 py-3 text-foreground/90">{fi ? format(fi, "HH:mm") : "—"}</td>
                            <td className="px-4 py-3 text-foreground/90">{lo ? format(lo, "HH:mm") : "—"}</td>
                            <td className="px-4 py-3 font-medium text-foreground">{l?.gross_work_hrs ?? "—"}</td>
                            <td className="px-4 py-3">
                              <Badge variant={statusVariant(l?.status)}>{l?.status ?? "—"}</Badge>
                            </td>
                          </tr>
                        );
                      })}
                      {logs.length === 0 ? (
                        <tr>
                          <td colSpan={5}>
                            <EmptyState title="No logs available" className="py-8" />
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="mt-6 flex justify-end">
            <button
              type="button"
              className="rounded-full border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground shadow-sm transition-transform hover:scale-[1.02]"
            >
              View Full Profile
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

