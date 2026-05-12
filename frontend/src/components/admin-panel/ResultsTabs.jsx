import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { EmptyState } from "../ui/empty-state";
import { cn } from "../../lib/utils";

function TabButton({ active, children, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1.5 text-xs font-semibold shadow-sm transition-transform hover:scale-[1.02]",
        active
          ? "border-border bg-card text-foreground"
          : "border-border bg-secondary/20 text-muted-foreground hover:text-foreground"
      )}
    >
      {children}
    </button>
  );
}

export default function ResultsTabs({ results }) {
  const r = results && typeof results === "object" ? results : {};

  const inserted = Array.isArray(r.inserted_rows ?? r.inserted) ? r.inserted_rows ?? r.inserted : [];
  const updated = Array.isArray(r.updated_rows ?? r.updated) ? r.updated_rows ?? r.updated : [];
  const skipped = Array.isArray(r.skipped_rows ?? r.skipped) ? r.skipped_rows ?? r.skipped : [];

  const [tab, setTab] = useState("inserted");
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const rows = useMemo(() => {
    if (tab === "updated") return updated;
    if (tab === "skipped") return skipped;
    return inserted;
  }, [inserted, skipped, tab, updated]);

  const header = tab === "updated" ? "Updated" : tab === "skipped" ? "Skipped" : "Inserted";
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const pageSafe = Math.min(totalPages, Math.max(1, page));
  const slice = rows.slice((pageSafe - 1) * pageSize, pageSafe * pageSize);

  return (
    <Card className="rounded-2xl">
      <CardHeader className="pb-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Import Results Breakdown
          </CardTitle>
          <div className="flex items-center gap-2">
            <TabButton active={tab === "inserted"} onClick={() => setTab("inserted")}>
              Inserted ({inserted.length})
            </TabButton>
            <TabButton
              active={tab === "updated"}
              onClick={() => {
                setTab("updated");
                setPage(1);
              }}
            >
              Updated ({updated.length})
            </TabButton>
            <TabButton
              active={tab === "skipped"}
              onClick={() => {
                setTab("skipped");
                setPage(1);
              }}
            >
              Skipped ({skipped.length})
            </TabButton>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {rows.length > 0 ? (
          <div className="space-y-4">
            <div className="overflow-x-auto rounded-2xl border border-border">
              <table className="w-full text-sm">
                <thead className="bg-secondary/40 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  <tr>
                    {["Employee ID", "Name", "Date", "Status"].map((h) => (
                      <th key={h} className="px-4 py-3 text-left">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border bg-card">
                  {slice.map((row, idx) => (
                    <tr key={idx} className="transition-colors hover:bg-secondary/30">
                      <td className="px-4 py-3 font-medium text-foreground">
                        {row?.employee_id ?? row?.employee_code ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-foreground/90">{row?.name ?? row?.employee_name ?? "—"}</td>
                      <td className="px-4 py-3 text-foreground/80">{row?.date ?? row?.log_date ?? "—"}</td>
                      <td className="px-4 py-3 font-medium text-foreground">{header}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 ? (
              <div className="flex items-center justify-between">
                <div className="text-xs text-muted-foreground">
                  Page {pageSafe} of {totalPages}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    className="rounded-full border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground shadow-sm transition-transform hover:scale-[1.02]"
                    disabled={pageSafe === 1}
                  >
                    Prev
                  </button>
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    className="rounded-full border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground shadow-sm transition-transform hover:scale-[1.02]"
                    disabled={pageSafe === totalPages}
                  >
                    Next
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <EmptyState
            title={`No ${header.toLowerCase()} rows`}
            description="Run an import to populate this section."
            className="py-10"
          />
        )}
      </CardContent>
    </Card>
  );
}

