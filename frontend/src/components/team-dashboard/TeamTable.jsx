import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { ArrowUpDown } from "lucide-react";
import { cn } from "../../lib/utils";
import { EmptyState } from "../ui/empty-state";

function cmp(a, b) {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b));
}

export default function TeamTable({ team, onSelect }) {
  const safe = Array.isArray(team) ? team : [];
  const [sort, setSort] = useState({ key: "score", dir: "desc" });
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const sorted = useMemo(() => {
    const data = [...safe];
    const dirMul = sort.dir === "asc" ? 1 : -1;
    data.sort((x, y) => cmp(x?.[sort.key], y?.[sort.key]) * dirMul);
    return data;
  }, [safe, sort.dir, sort.key]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const pageSafe = Math.min(totalPages, Math.max(1, page));
  const slice = sorted.slice((pageSafe - 1) * pageSize, pageSafe * pageSize);

  const onSort = (key) => {
    setPage(1);
    setSort((p) => {
      if (p.key !== key) return { key, dir: "desc" };
      return { key, dir: p.dir === "desc" ? "asc" : "desc" };
    });
  };

  const COLS = [
    { key: "name", label: "Name" },
    { key: "department", label: "Dept" },
    { key: "present", label: "Present" },
    { key: "absent", label: "Absent" },
    { key: "late", label: "Late" },
    { key: "score", label: "Score" },
  ];

  return (
    <Card className="rounded-xl border border-border shadow-sm transition-shadow duration-200 hover:shadow-md">
      <CardHeader className="px-4 pb-2 pt-4">
        <CardTitle className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
          Team Overview
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4 pt-1">
        {safe.length > 0 ? (
          <div className="space-y-3">
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
                  {slice.map((m) => {
                    const score = Number(m?.score ?? 0);
                    const low = Number.isFinite(score) && score < 50;
                    return (
                      <tr
                        key={m?.id ?? `${m?.name}-${m?.department}`}
                        className={cn(
                          "cursor-pointer transition-colors hover:bg-secondary/20",
                          low && "bg-rose-500/[0.03] hover:bg-rose-500/[0.06]"
                        )}
                        onClick={() => onSelect?.(m)}
                      >
                        <td className="px-3 py-2 font-medium text-foreground whitespace-nowrap">{m?.name ?? m?.full_name ?? "—"}</td>
                        <td className="px-3 py-2 text-muted-foreground">{m?.department ?? "—"}</td>
                        <td className="px-3 py-2 text-foreground/80 tabular-nums">{m?.present ?? m?.total_present ?? "—"}</td>
                        <td className="px-3 py-2 text-foreground/80 tabular-nums">{m?.absent ?? m?.total_absent ?? "—"}</td>
                        <td className="px-3 py-2 text-foreground/80 tabular-nums">{m?.late ?? m?.total_late ?? "—"}</td>
                        <td className="px-3 py-2 font-bold text-foreground tabular-nums">
                          {Number.isFinite(score) ? `${score.toFixed(1)}%` : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {totalPages > 1 ? (
              <div className="flex items-center justify-between">
                <div className="text-[10px] text-muted-foreground">
                  Page {pageSafe} of {totalPages}
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    className="rounded-md border border-border bg-card px-2.5 py-1 text-[10px] font-semibold text-foreground shadow-sm transition-all hover:shadow-md disabled:opacity-40"
                    disabled={pageSafe === 1}
                  >
                    Prev
                  </button>
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    className="rounded-md border border-border bg-card px-2.5 py-1 text-[10px] font-semibold text-foreground shadow-sm transition-all hover:shadow-md disabled:opacity-40"
                    disabled={pageSafe === totalPages}
                  >
                    Next
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <EmptyState title="No team members" description="No direct reports are assigned to you yet." className="py-6" />
        )}
      </CardContent>
    </Card>
  );
}
