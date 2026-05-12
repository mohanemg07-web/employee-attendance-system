import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { EmptyState } from "../ui/empty-state";
import { ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

const COLORS = {
  valid: "#10b981", // green
  invalid: "#f59e0b", // yellow
  duplicates: "#ef4444", // red
  missing: "#94a3b8", // gray
};

export default function QualityChart({ quality }) {
  const q = quality && typeof quality === "object" ? quality : null;
  const valid = Number(q?.valid ?? q?.valid_records ?? 0);
  const invalid = Number(q?.invalid ?? q?.invalid_records ?? 0);
  const duplicates = Number(q?.duplicates ?? 0);
  const missing = Number(q?.missing ?? q?.missing_values ?? 0);

  const has =
    [valid, invalid, duplicates, missing].some((n) => Number.isFinite(n) && n > 0);

  const total =
    (Number.isFinite(valid) ? valid : 0) +
    (Number.isFinite(invalid) ? invalid : 0) +
    (Number.isFinite(duplicates) ? duplicates : 0) +
    (Number.isFinite(missing) ? missing : 0);

  const pct = total > 0 ? (100 * (Number.isFinite(valid) ? valid : 0)) / total : null;

  const data = [
    { key: "valid", name: "Valid Records", value: Number.isFinite(valid) ? valid : 0 },
    { key: "invalid", name: "Invalid", value: Number.isFinite(invalid) ? invalid : 0 },
    { key: "duplicates", name: "Duplicates", value: Number.isFinite(duplicates) ? duplicates : 0 },
    { key: "missing", name: "Missing", value: Number.isFinite(missing) ? missing : 0 },
  ].filter((d) => d.value > 0);

  return (
    <Card className="rounded-2xl">
      <CardHeader className="pb-4">
        <CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Data Quality Overview
        </CardTitle>
      </CardHeader>
      <CardContent>
        {has ? (
          <div className="relative h-[180px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={data}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={58}
                  outerRadius={80}
                  paddingAngle={2}
                  stroke="transparent"
                >
                  {data.map((entry) => (
                    <Cell key={entry.key} fill={COLORS[entry.key] || "#64748b"} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>

            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <div className="text-2xl font-semibold text-foreground">
                {pct != null ? `${pct.toFixed(1)}%` : "—"}
              </div>
              <div className="text-xs font-semibold text-muted-foreground">High Quality</div>
            </div>
          </div>
        ) : (
          <EmptyState title="No quality metrics" description="Upload an import to calculate quality." className="py-10" />
        )}

        {has ? (
          <div className="mt-4 space-y-2 text-xs text-muted-foreground">
            {[
              ["Valid Records", COLORS.valid, valid],
              ["Invalid", COLORS.invalid, invalid],
              ["Duplicates", COLORS.duplicates, duplicates],
              ["Missing", COLORS.missing, missing],
            ].map(([label, color, value]) => (
              <div key={label} className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: color }} />
                  <span>{label}</span>
                </div>
                <span className="font-medium text-foreground">{Number.isFinite(value) ? value : 0}</span>
              </div>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

