import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Alert } from "../ui/alert";
import { EmptyState } from "../ui/empty-state";

function normalizeInsights(input) {
  if (!Array.isArray(input)) return [];
  return input
    .map((item) => {
      if (typeof item === "string") return { message: item, type: "default" };
      return {
        message: item?.message || item?.text || "No insight",
        type: item?.type || "default",
      };
    })
    .filter((x) => x?.message);
}

function inferVariant(insight) {
  const type = String(insight?.type || "").toLowerCase();
  if (type === "warning" || type === "critical" || type === "positive") return type;
  if (type === "danger") return "critical";
  if (type === "success") return "positive";

  const text = String(insight?.message || "").toLowerCase();
  if (text.includes("critical") || text.includes("absent") || text.includes("failure") || text.includes("breach"))
    return "critical";
  if (text.includes("warning") || text.includes("late") || text.includes("low") || text.includes("drop"))
    return "warning";
  if (text.includes("great") || text.includes("good") || text.includes("consistent") || text.includes("perfect") || text.includes("strong"))
    return "positive";
  return "default";
}

export default function InsightsPanel({ insights }) {
  const items = normalizeInsights(insights);

  return (
    <Card className="rounded-xl border border-border shadow-sm transition-shadow duration-200 hover:shadow-md">
      <CardHeader className="px-4 pb-2 pt-4">
        <CardTitle className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
          AI Insights
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4 pt-1">
        {items.length > 0 ? (
          <div className="space-y-2">
            {items.map((insight, idx) => (
              <Alert key={idx} variant={inferVariant(insight)} description={insight.message} />
            ))}
          </div>
        ) : (
          <EmptyState title="No insights available" description="Insights will appear once enough data is collected." className="py-6" />
        )}
      </CardContent>
    </Card>
  );
}
