import { cn } from "@/lib/utils"

export function Logo({ className, size = 40 }: { className?: string; size?: number }) {
  return (
    <img
      src="/logo.svg"
      alt="Facebook Marketplace Monitor"
      width={size}
      height={size}
      className={cn("rounded-xl shadow-sm", className)}
    />
  )
}

export function BrandTitle({ className }: { className?: string }) {
  return (
    <div className={cn("flex flex-col", className)}>
      <span className="font-bold text-base leading-tight tracking-tight">
        Facebook Marketplace
      </span>
      <span className="text-xs font-medium text-muted-foreground">
        Vehicle Monitor
      </span>
    </div>
  )
}
