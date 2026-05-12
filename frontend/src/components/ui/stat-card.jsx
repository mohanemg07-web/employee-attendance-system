import { Card, CardContent } from "./card"
import { cn } from "../../lib/utils"

export function StatCard({ 
  title, 
  value, 
  subtitle, 
  icon: Icon, 
  iconClassName, 
  className,
  valueClassName,
  isFeatured = false 
}) {
  return (
    <Card className={cn(
      "flex flex-col justify-center transition-transform duration-200 hover:scale-[1.02]", 
      isFeatured && "md:col-span-2 bg-secondary/20 border-border/50 shadow-inner",
      className
    )}>
      <CardContent className={cn("p-6", isFeatured && "p-8 text-center")}>
        <div className={cn("flex items-center justify-between", isFeatured && "justify-center mb-4")}>
          <p className={cn(
            "uppercase tracking-wider font-bold",
            isFeatured ? "text-sm text-foreground/80 tracking-widest" : "text-xs text-muted-foreground"
          )}>
            {title}
          </p>
          {!isFeatured && Icon && (
            <div className={cn("p-2 rounded-lg bg-secondary text-muted-foreground", iconClassName)}>
              <Icon size={16} />
            </div>
          )}
        </div>
        
        <div className={cn("mt-4 flex items-baseline", isFeatured ? "justify-center gap-2 mt-0" : "gap-1")}>
          <h3 className={cn(
            "font-bold tracking-tight text-foreground", 
            isFeatured ? "text-6xl tracking-tighter" : "text-3xl",
            valueClassName
          )}>
            {value}
          </h3>
          {subtitle && (
            <span className={cn(
              "font-medium",
              isFeatured ? "text-xl text-foreground/50" : "text-sm text-muted-foreground"
            )}>
              {subtitle}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
