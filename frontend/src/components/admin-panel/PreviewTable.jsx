import { Badge } from "../ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { EmptyState } from "../ui/empty-state";
import { FileText } from "lucide-react";

function statusVariant(status) {
  const s = String(status || "").toLowerCase();
  if (s === "present") return "present";
  if (s === "late") return "late";
  if (s === "absent") return "absent";
  return "secondary";
}

export default function PreviewTable({ rows, onViewAll }) {
  const safe = Array.isArray(rows) ? rows : [];

  return (
    <Card className="rounded-2xl">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Import Preview
          </CardTitle>
          <button
            type="button"
            onClick={onViewAll}
            className="rounded-full border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground shadow-sm transition-transform hover:scale-[1.02]"
          >
            View Full Preview
          </button>
        </div>
      </CardHeader>
      <CardContent>
        {safe.length > 0 ? (
          <div className="overflow-x-auto rounded-2xl border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary/40 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                <tr>
                  {["Employee ID", "Name", "Date", "First In", "Last Out", "Work Hours", "Status"].map((h) => (
                    <th key={h} className="px-4 py-3 text-left">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border bg-card">
                {safe.slice(0, 5).map((r, idx) => (
                  <tr key={idx} className="transition-colors hover:bg-secondary/30">
                    <td className="px-4 py-3 font-medium text-foreground">{r?.employee_id ?? r?.employee_code ?? "—"}</td>
                    <td className="px-4 py-3 text-foreground/90">{r?.name ?? r?.employee_name ?? "—"}</td>
                    <td className="px-4 py-3 text-foreground/80">{r?.date ?? r?.log_date ?? "—"}</td>
                    <td className="px-4 py-3 text-foreground/80">{r?.first_in ?? "—"}</td>
                    <td className="px-4 py-3 text-foreground/80">{r?.last_out ?? "—"}</td>
                    <td className="px-4 py-3 font-medium text-foreground">{r?.work_hours ?? r?.gross_work_hrs ?? "—"}</td>
                    <td className="px-4 py-3">
                      <Badge variant={statusVariant(r?.status)}>{r?.status ?? "—"}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon={FileText} title="No preview available" description="Upload a file to see the first rows here." className="py-10" />
        )}
      </CardContent>
    </Card>
  );
}

