import { Card, CardContent } from "../ui/card";
import { cn } from "../../lib/utils";

const TONES = {
  present: { bg: "bg-emerald-500/[0.04]", border: "border-emerald-500/20", dot: "bg-emerald-500", text: "text-emerald-400" },
  absent:  { bg: "bg-rose-500/[0.04]",    border: "border-rose-500/20",    dot: "bg-rose-500",    text: "text-rose-400" },
  late:    { bg: "bg-amber-500/[0.04]",    border: "border-amber-500/20",   dot: "bg-amber-500",   text: "text-amber-400" },
  leave:   { bg: "bg-violet-500/[0.04]",   border: "border-violet-500/20",  dot: "bg-violet-500",  text: "text-violet-400" },
  total:   { bg: "bg-slate-500/[0.04]",     border: "border-slate-500/20",   dot: "bg-slate-400",   text: "text-slate-400" },
};

function SummaryItem({ label, value, tone = "total" }) {
  const t = TONES[tone] || TONES.total;
  return (
    <Card className={cn(
      "rounded-xl border shadow-sm transition-all duration-200 hover:shadow-md hover:-translate-y-0.5",
      t.bg, t.border
    )}>
      <CardContent className="px-4 py-3">
        <div className="flex items-center gap-2 mb-1.5">
          <div className={cn("h-1.5 w-1.5 rounded-full", t.dot)} />
          <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{label}</div>
        </div>
        <div className="text-xl font-bold tracking-tight text-foreground tabular-nums">{value ?? "—"}</div>
      </CardContent>
    </Card>
  );
}

export default function SummaryCards({ summary }) {
  const s = summary && typeof summary === "object" ? summary : {};

  const present = s.present ?? s.total_present ?? 0;
  const absent = s.absent ?? s.total_absent ?? 0;
  const late = s.late ?? s.total_late ?? 0;
  const leave = s.leave ?? s.total_leave ?? s.total_on_leave ?? 0;
  const total = s.working_days ?? s.total_days ?? s.total ?? 0;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
      <SummaryItem label="Days Present" value={present} tone="present" />
      <SummaryItem label="Absent" value={absent} tone="absent" />
      <SummaryItem label="Late" value={late} tone="late" />
      <SummaryItem label="Leave" value={leave} tone="leave" />
      <SummaryItem label="Total Working Days" value={total} tone="total" />
    </div>
  );
}
