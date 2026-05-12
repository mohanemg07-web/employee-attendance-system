import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Download, ShieldCheck, ScrollText } from "lucide-react";

function ActionButton({ icon: Icon, label, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-3 rounded-2xl border border-border bg-card px-4 py-3 text-left shadow-sm transition-transform hover:scale-[1.02]"
    >
      <div className="rounded-xl border border-border bg-secondary/40 p-2 text-muted-foreground">
        <Icon className="h-4 w-4" />
      </div>
      <div className="text-sm font-semibold text-foreground">{label}</div>
    </button>
  );
}

export default function QuickActions({ onDownloadTemplate, onViewRules, onViewLogs }) {
  return (
    <Card className="rounded-2xl">
      <CardHeader className="pb-4">
        <CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Quick Actions
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <ActionButton icon={Download} label="Download Sample Template" onClick={onDownloadTemplate} />
        <ActionButton icon={ShieldCheck} label="Data Quality Rules" onClick={onViewRules} />
        <ActionButton icon={ScrollText} label="View Import Logs" onClick={onViewLogs} />
      </CardContent>
    </Card>
  );
}

