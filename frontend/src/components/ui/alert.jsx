import * as React from "react"
import { cn } from "../../lib/utils"
import { AlertTriangle, XCircle, CheckCircle2, Info } from "lucide-react"

const alertVariants = {
  default: "bg-secondary text-foreground border-border",
  positive: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
  warning: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
  critical: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20",
}

const alertIcons = {
  default: Info,
  positive: CheckCircle2,
  warning: AlertTriangle,
  critical: XCircle,
}

const Alert = React.forwardRef(({ className, variant = "default", title, description, ...props }, ref) => {
  const Icon = alertIcons[variant]
  return (
    <div
      ref={ref}
      role="alert"
      className={cn(
        "relative w-full rounded-lg border p-4 flex gap-3 items-start",
        alertVariants[variant],
        className
      )}
      {...props}
    >
      <Icon className="h-5 w-5 shrink-0 mt-0.5" />
      <div className="flex flex-col gap-1">
        {title && <h5 className="mb-1 font-medium leading-none tracking-tight">{title}</h5>}
        <div className="text-sm opacity-90 leading-relaxed">
          {description}
        </div>
      </div>
    </div>
  )
})
Alert.displayName = "Alert"

export { Alert }
