import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { EmptyState } from "../ui/empty-state";
import { Badge } from "../ui/badge";
import { Download, History } from "lucide-react";
import { cn } from "../../lib/utils";

function statusBadge(status) {
  const s = String(status || "").toLowerCase();
  if (s === "completed" || s === "success") return { variant: "present", label: "Completed" };
  if (s === "failed" || s === "error") return { variant: "absent", label: "Failed" };
  return { variant: "secondary", label: status || "Unknown" };
}

export default function HistoryList({ items, onViewAll, onDownload }) {
  const safe = Array.isArray(items) ? items : [];

  return (
    <Card className="rounded-2xl">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Import History
          </CardTitle>
          <button
            type="button"
            onClick={onViewAll}
            className="rounded-full border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground shadow-sm transition-transform hover:scale-[1.02]"
          >
            View All History
          </button>
        </div>
      </CardHeader>
      <CardContent>
        {safe.length > 0 ? (
          <div className="space-y-2">
            {safe.slice(0, 5).map((h, idx) => {
              const meta = statusBadge(h?.status);
              return (
                <div
                  key={h?.id ?? `${h?.file_name}-${idx}`}
                  className="flex items-center justify-between gap-3 rounded-2xl border border-border bg-card px-4 py-3 shadow-sm"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-secondary/40 text-muted-foreground">
                      <History className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold text-foreground">
                        {h?.file_name ?? h?.filename ?? "—"}
                      </div>
                      <div className="mt-0.5 text-xs text-muted-foreground">
                        {h?.uploaded_at ?? h?.created_at ?? "—"} • {h?.rows ?? h?.total_rows ?? "—"} rows
                      </div>
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    <Badge variant={meta.variant}>{meta.label}</Badge>
                    <button
                      type="button"
                      onClick={() => onDownload?.(h)}
                      className={cn(
                        "rounded-full border border-border bg-card p-2 shadow-sm transition-transform hover:scale-[1.04]"
                      )}
                      aria-label="Download"
                      title="Download"
                    >
                      <Download className="h-4 w-4 text-muted-foreground" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <EmptyState title="No import history" description="Imports will appear here once you upload files." className="py-10" />
        )}
      </CardContent>
    </Card>
  );
}

