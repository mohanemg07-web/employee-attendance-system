import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Badge } from "../ui/badge";
import { EmptyState } from "../ui/empty-state";
import { ArrowUpDown, FileText } from "lucide-react";
import { format, parseISO } from "date-fns";

function safeParseDate(v) {
  try {
    return v ? parseISO(v) : null;
  } catch {
    return null;
  }
}

function statusVariant(status) {
  const s = String(status || "").toLowerCase().replace(/\s+/g, "_");
  if (s === "present") return "present";
  if (s === "absent") return "absent";
  if (s === "late") return "late";
  if (s === "on_leave" || s === "leave") return "leave";
  if (s === "weekend") return "weekend";
  if (s === "holiday") return "holiday";
  return "secondary";
}

/** Map raw backend status → clean display label */
function statusLabel(status) {
  const s = String(status || "").toLowerCase().replace(/\s+/g, "_");
  if (s === "on_leave") return "Leave";
  if (s === "present") return "Present";
  if (s === "absent") return "Absent";
  if (s === "late") return "Late";
  if (s === "weekend") return "Weekend";
  if (s === "holiday") return "Holiday";
  if (s === "half_day") return "Half Day";
  return status || "—";
}

export default function LogsTable({ logs }) {
  const safe = Array.isArray(logs) ? logs : [];
  const [sort, setSort] = useState({ key: "log_date", dir: "desc" });

  const sorted = useMemo(() => {
    const data = [...safe];
    const dirMul = sort.dir === "asc" ? 1 : -1;

    data.sort((a, b) => {
      const ka = a?.[sort.key];
      const kb = b?.[sort.key];

      if (sort.key === "log_date" || sort.key === "first_in" || sort.key === "last_out") {
        const da = safeParseDate(ka)?.getTime?.() ?? -Infinity;
        const db = safeParseDate(kb)?.getTime?.() ?? -Infinity;
        return (da - db) * dirMul;
      }

      const sa = ka == null ? "" : String(ka);
      const sb = kb == null ? "" : String(kb);
      return sa.localeCompare(sb) * dirMul;
    });

    return data;
  }, [safe, sort.dir, sort.key]);

  const onSort = (key) => {
    setSort((p) => {
      if (p.key !== key) return { key, dir: "desc" };
      return { key, dir: p.dir === "desc" ? "asc" : "desc" };
    });
  };

  const COLS = [
    { key: "log_date", label: "Date" },
    { key: "first_in", label: "In" },
    { key: "last_out", label: "Out" },
    { key: "gross_work_hrs", label: "Hours" },
    { key: "status", label: "Status" },
  ];

  return (
    <Card className="rounded-xl border border-border shadow-sm transition-shadow duration-200 hover:shadow-md">
      <CardHeader className="px-4 pb-2 pt-4">
        <CardTitle className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
          Recent Logs
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4 pt-1">
        {safe.length > 0 ? (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-secondary/30">
                  {COLS.map((c) => (
                    <th
                      key={c.key}
                      className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-widest text-muted-foreground"
                    >
                      <button
                        type="button"
                        onClick={() => onSort(c.key)}
                        className="group inline-flex items-center gap-1 hover:text-foreground transition-colors"
                      >
                        {c.label}
                        <ArrowUpDown className="h-2.5 w-2.5 opacity-0 group-hover:opacity-60 transition-opacity" />
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {sorted.slice(0, 10).map((log, idx) => {
                  const d = safeParseDate(log?.log_date);
                  const fi = safeParseDate(log?.first_in);
                  const lo = safeParseDate(log?.last_out);
                  return (
                    <tr key={idx} className="transition-colors hover:bg-secondary/20">
                      <td className="px-3 py-2 font-medium text-foreground whitespace-nowrap">
                        {d ? format(d, "MMM dd, yyyy") : "—"}
                      </td>
                      <td className="px-3 py-2 text-foreground/80 tabular-nums">{fi ? format(fi, "HH:mm") : "—"}</td>
                      <td className="px-3 py-2 text-foreground/80 tabular-nums">{lo ? format(lo, "HH:mm") : "—"}</td>
                      <td className="px-3 py-2 font-medium text-foreground tabular-nums">
                        {log?.gross_work_hrs ? String(log.gross_work_hrs) : "—"}
                      </td>
                      <td className="px-3 py-2">
                        <Badge variant={statusVariant(log?.status)}>{statusLabel(log?.status)}</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            icon={FileText}
            title="No attendance data yet"
            description="Logs will appear once attendance is recorded."
            className="py-6"
          />
        )}
      </CardContent>
    </Card>
  );
}
