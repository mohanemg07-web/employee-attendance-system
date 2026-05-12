import { memo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { EmptyState } from "../ui/empty-state";
import { cn } from "../../lib/utils";

function initials(name) {
  const s = String(name || "").trim();
  if (!s) return "—";
  return s
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export default memo(function TopPerformers({ performers, onSelect }) {
  const safe = Array.isArray(performers) ? performers : [];

  return (
    <Card className="rounded-xl border border-border shadow-sm transition-shadow duration-200 hover:shadow-md">
      <CardHeader className="px-4 pb-1 pt-4">
        <CardTitle className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
          Top Performers
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-3 pt-1">
        {safe.length > 0 ? (
          <div className="space-y-1.5">
            {safe.slice(0, 5).map((p) => {
              const score = Number(p?.score ?? p?.attendance_score ?? 0);
              const clamped = Number.isFinite(score) ? Math.max(0, Math.min(100, score)) : 0;
              return (
                <button
                  key={p?.id ?? `${p?.name}-${p?.department}`}
                  type="button"
                  onClick={() => onSelect?.(p)}
                  className="w-full rounded-lg border border-border/60 bg-card px-3 py-2 text-left transition-all duration-150 hover:shadow-sm hover:border-border hover:-translate-y-px"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2.5">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-secondary text-[10px] font-bold text-foreground">
                        {initials(p?.name ?? p?.full_name)}
                      </div>
                      <div className="min-w-0">
                        <div className="truncate text-xs font-semibold text-foreground leading-tight">
                          {p?.name ?? p?.full_name ?? "—"}
                        </div>
                        <div className="truncate text-[10px] text-muted-foreground leading-tight">
                          {p?.department ?? p?.team ?? "—"}
                        </div>
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="text-xs font-bold text-foreground tabular-nums">{clamped.toFixed(1)}%</div>
                      <div className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                        Score
                      </div>
                    </div>
                  </div>

                  <div className="mt-1.5 h-1 w-full rounded-full bg-secondary/40">
                    <div
                      className={cn("h-1 rounded-full transition-all duration-500", clamped >= 90 ? "bg-emerald-500" : clamped >= 75 ? "bg-blue-500" : "bg-amber-500")}
                      style={{ width: `${clamped}%` }}
                    />
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          <EmptyState title="No performers yet" description="Top performers will appear once the team has data." className="py-5" />
        )}
      </CardContent>
    </Card>
  );
});
