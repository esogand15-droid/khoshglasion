import * as React from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { cn } from "@/lib/utils";

type Variant = "info" | "success" | "warning" | "destructive";

const styles: Record<Variant, { box: string; icon: React.ComponentType<{ className?: string }>; iconColor: string }> = {
  info: { box: "border-border bg-card", icon: Info, iconColor: "text-foreground" },
  success: { box: "border-success/25 bg-success/10", icon: CheckCircle2, iconColor: "text-success" },
  warning: { box: "border-warning/25 bg-warning/10", icon: AlertTriangle, iconColor: "text-warning" },
  destructive: { box: "border-destructive/30 bg-destructive/10", icon: AlertCircle, iconColor: "text-destructive" },
};

export interface AlertProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  variant?: Variant;
  title?: React.ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
}

function readable(value: React.ReactNode): React.ReactNode {
  if (value == null || typeof value === "boolean") return null;
  if (typeof value === "string" || typeof value === "number") return value;
  if (Array.isArray(value)) {
    const notes = value.map((item) => (item && typeof item === "object" && "msg" in item ? String((item as { msg?: unknown }).msg || "") : ""));
    if (notes.some(Boolean)) return notes.filter(Boolean).join(" ");
    return value;
  }
  if (typeof value === "object" && !("$$typeof" in value)) return "درخواست رد شد";
  return value;
}

/** هشدار درون‌صفحه‌ای. Icon at the inline-start; use `role="alert"` for errors that need announcing. */
export function Alert({ variant = "info", title, icon, className, children, ...props }: AlertProps) {
  const s = styles[variant];
  const Icon = icon ?? s.icon;
  const heading = readable(title);
  const body = readable(children);
  return (
    <div role={variant === "destructive" ? "alert" : "status"} className={cn("flex items-start gap-3 rounded-xl border p-4 text-sm", s.box, className)} {...props}>
      <Icon className={cn("mt-0.5 size-4 shrink-0", s.iconColor)} />
      <div className="min-w-0">
        {heading && <p className={cn("font-semibold", variant !== "info" && s.iconColor)}>{heading}</p>}
        {body && <div className={cn("text-foreground/80", heading && "mt-0.5")}>{body}</div>}
      </div>
    </div>
  );
}
