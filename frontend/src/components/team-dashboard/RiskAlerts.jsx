import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { AlertTriangle, Clock, FileWarning, X, ChevronDown } from "lucide-react";
import { cn } from "../../lib/utils";

/* ── Column configs per alert type ─────────────────── */
const COLUMNS = {
  low_attendance: [
    { key: "employee_name", label: "Name" },
    { key: "department", label: "Dept" },
    { key: "attendance_pct", label: "Att %", fmt: (v) => `${v}%` },
    { key: "present", label: "Present" },
    { key: "late", label: "Late" },
    { key: "absent", label: "Absent" },
  ],
  frequent_late: [
    { key: "employee_name", label: "Name" },
    { key: "department", label: "Dept" },
    { key: "late_count", label: "Late Days" },
  ],
  missing_logs: [
    { key: "employee_name", label: "Name" },
    { key: "department", label: "Dept" },
    { key: "status", label: "Status" },
  ],
};

const TITLES = {
  low_attendance: "Low Attendance",
  frequent_late: "Frequent Late",
  missing_logs: "Missing Logs",
};

/* ── Expandable employee table ─────────────────────── */
function EmployeeDrawer({ type, employees, onClose }) {
  const cols = COLUMNS[type] || COLUMNS.missing_logs;
  const list = Array.isArray(employees) ? employees : [];

  return (
    <div className="animate-in slide-in-from-top-2 fade-in duration-200 mt-1.5 rounded-lg border border-border/60 bg-card/80 backdrop-blur-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border/40">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
          {TITLES[type]} — {list.length} employee{list.length !== 1 ? "s" : ""}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-0.5 text-muted-foreground/60 hover:text-foreground hover:bg-secondary/50 transition-colors"
          aria-label="Close"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Empty state */}
      {list.length === 0 ? (
        <div className="px-3 py-4 text-center text-xs text-muted-foreground">
          No employees in this category.
        </div>
      ) : (
        /* Scrollable table */
        <div className="max-h-[200px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-card/95 backdrop-blur-sm">
              <tr>
                {cols.map((c) => (
                  <th
                    key={c.key}
                    className="px-3 py-1.5 text-left text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/70 border-b border-border/30"
                  >
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {list.map((emp, i) => (
                <tr
                  key={emp.employee_id ?? i}
                  className="border-b border-border/10 hover:bg-secondary/20 transition-colors"
                >
                  {cols.map((c) => (
                    <td key={c.key} className="px-3 py-1.5 text-foreground/80 whitespace-nowrap">
                      {c.fmt ? c.fmt(emp[c.key]) : (emp[c.key] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ── Alert card row ────────────────────────────────── */
function AlertCard({ title, count, icon: Icon, tone, isOpen, onClick }) {
  const tones = {
    critical: "border-rose-500/20 bg-rose-500/[0.03]",
    warning: "border-amber-500/20 bg-amber-500/[0.03]",
    info: "border-violet-500/20 bg-violet-500/[0.03]",
  };
  const iconTones = {
    critical: "text-rose-500",
    warning: "text-amber-500",
    info: "text-violet-500",
  };

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full rounded-lg border px-3 py-2 text-left transition-all duration-150 hover:shadow-sm hover:-translate-y-px",
        tones[tone] || "border-border bg-card",
        isOpen && "ring-1 ring-inset ring-white/10"
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <div className={cn("shrink-0", iconTones[tone] || "text-muted-foreground")}>
            <Icon className="h-3.5 w-3.5" />
          </div>
          <div>
            <div className="text-xs font-semibold text-foreground leading-tight">{title}</div>
            <div className="text-[10px] text-muted-foreground leading-tight">{count} employee{count !== 1 ? "s" : ""}</div>
          </div>
        </div>
        <div className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-widest text-muted-foreground/60">
          View
          <ChevronDown className={cn("h-3 w-3 transition-transform duration-200", isOpen && "rotate-180")} />
        </div>
      </div>
    </button>
  );
}

/* ── Main component ────────────────────────────────── */
export default function RiskAlerts({ alerts }) {
  const [openCategory, setOpenCategory] = useState(null);

  const a = alerts && typeof alerts === "object" ? alerts : {};

  const lowAttendance = Number(a.low_attendance ?? a.lowAttendance ?? 0) || 0;
  const frequentLate = Number(a.frequent_late ?? a.frequentLate ?? 0) || 0;
  const missingLogs = Number(a.missing_logs ?? a.missingLogs ?? 0) || 0;

  const lowAttendanceEmployees = Array.isArray(a.low_attendance_employees) ? a.low_attendance_employees : [];
  const frequentLateEmployees = Array.isArray(a.frequent_late_employees) ? a.frequent_late_employees : [];
  const missingLogsEmployees = Array.isArray(a.missing_logs_employees) ? a.missing_logs_employees : [];

  const toggle = (cat) => setOpenCategory((prev) => (prev === cat ? null : cat));

  return (
    <Card className="rounded-xl border border-border shadow-sm transition-shadow duration-200 hover:shadow-md">
      <CardHeader className="px-4 pb-1 pt-4">
        <CardTitle className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
          Risk Alerts
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-3 pt-1 space-y-1.5">
        {/* Low Attendance */}
        <AlertCard
          title="Low Attendance"
          count={lowAttendance}
          icon={AlertTriangle}
          tone="critical"
          isOpen={openCategory === "low_attendance"}
          onClick={() => toggle("low_attendance")}
        />
        {openCategory === "low_attendance" && (
          <EmployeeDrawer
            type="low_attendance"
            employees={lowAttendanceEmployees}
            onClose={() => setOpenCategory(null)}
          />
        )}

        {/* Frequent Late */}
        <AlertCard
          title="Frequent Late"
          count={frequentLate}
          icon={Clock}
          tone="warning"
          isOpen={openCategory === "frequent_late"}
          onClick={() => toggle("frequent_late")}
        />
        {openCategory === "frequent_late" && (
          <EmployeeDrawer
            type="frequent_late"
            employees={frequentLateEmployees}
            onClose={() => setOpenCategory(null)}
          />
        )}

        {/* Missing Logs */}
        <AlertCard
          title="Missing Logs"
          count={missingLogs}
          icon={FileWarning}
          tone="info"
          isOpen={openCategory === "missing_logs"}
          onClick={() => toggle("missing_logs")}
        />
        {openCategory === "missing_logs" && (
          <EmployeeDrawer
            type="missing_logs"
            employees={missingLogsEmployees}
            onClose={() => setOpenCategory(null)}
          />
        )}
      </CardContent>
    </Card>
  );
}
