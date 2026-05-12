import { cn } from "../../lib/utils"
import { Inbox } from 'lucide-react'

export function EmptyState({ icon: Icon = Inbox, title, description, className }) {
  return (
    <div className={cn("flex flex-col items-center justify-center p-8 text-center", className)}>
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-secondary mb-4 text-muted-foreground">
        <Icon size={24} strokeWidth={1.5} />
      </div>
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      {description && (
        <p className="mt-1 text-sm text-muted-foreground max-w-sm">{description}</p>
      )}
    </div>
  )
}
