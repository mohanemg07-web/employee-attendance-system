import * as React from "react"
import { cn } from "../../lib/utils"

const badgeVariants = {
  default: "bg-primary/10 text-primary border-primary/20",
  secondary: "bg-secondary text-secondary-foreground border-border",
  outline: "text-foreground border-border",
  present: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
  absent: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20",
  late: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
  leave: "bg-violet-500/10 text-violet-600 dark:text-violet-400 border-violet-500/20",
  weekend: "bg-slate-500/10 text-slate-500 dark:text-slate-400 border-slate-500/20",
  holiday: "bg-slate-500/10 text-slate-500 dark:text-slate-400 border-slate-500/20",
}

function Badge({ className, variant = "default", ...props }) {
  return (
    <div
      className={cn(
        "inline-flex items-center justify-center min-w-[76px] h-6 rounded-full border px-3 text-[10px] font-semibold uppercase tracking-wider transition-colors",
        badgeVariants[variant] || badgeVariants.secondary,
        className
      )}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
