import { Card, CardContent } from "../ui/card";
import { cn } from "../../lib/utils";

export default function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  right,
  className,
  valueClassName,
}) {
  return (
    <Card
      className={cn(
        "rounded-xl border border-border/50 bg-card text-card-foreground shadow-sm",
        "transition-all duration-200 hover:shadow-md hover:-translate-y-0.5",
        className
      )}
    >
      <CardContent className="px-4 py-3.5">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
              {title}
            </div>
            <div
              className={cn(
                "mt-1.5 text-2xl font-semibold leading-tight tracking-tight text-foreground",
                valueClassName
              )}
            >
              {value}
            </div>
            {subtitle ? (
              <div className="mt-0.5 text-[11px] text-muted-foreground/70">
                {subtitle}
              </div>
            ) : null}
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {right ? <div className="text-xs font-medium text-muted-foreground">{right}</div> : null}
            {Icon ? (
              <div className="rounded-lg bg-muted p-1.5 text-muted-foreground">
                <Icon className="h-3.5 w-3.5" />
              </div>
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
