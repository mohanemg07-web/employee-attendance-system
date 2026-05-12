import { Database, CheckCircle2, Pencil, XCircle } from "lucide-react";
import { Card, CardContent } from "../ui/card";
import { cn } from "../../lib/utils";

function asNumber(v, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function pct(part, total) {
  if (total <= 0) return 0;
  return (100 * part) / total;
}

const STATS = [
  { key: "total_rows", alt: "total", label: "Total", icon: Database, color: "text-foreground" },
  { key: "inserted", label: "Inserted", icon: CheckCircle2, color: "text-emerald-600" },
  { key: "updated", label: "Updated", icon: Pencil, color: "text-amber-600" },
  { key: "skipped", label: "Skipped", icon: XCircle, color: "text-rose-600" },
];

export default function ImportSummary({ summary }) {
  const s = summary && typeof summary === "object" ? summary : {};
  const total = asNumber(s.total_rows ?? s.total ?? 0);

  return (
    <Card className="w-full rounded-xl shadow-sm">
      <CardContent className="p-4">
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
          Import Summary
        </div>
        <div className="grid grid-cols-4 gap-2">
          {STATS.map(({ key, alt, label, icon: Icon, color }) => {
            const val = asNumber(s[key] ?? (alt ? s[alt] : 0));
            return (
              <div
                key={key}
                className="flex items-center gap-2.5 rounded-lg border border-border bg-secondary/10 px-3 py-2"
              >
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border bg-card text-muted-foreground">
                  <Icon className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0">
                  <div className={cn("text-lg font-semibold leading-tight", color)}>
                    {val}
                  </div>
                  <div className="text-[10px] text-muted-foreground leading-tight">
                    {label} · {pct(val, total).toFixed(0)}%
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
