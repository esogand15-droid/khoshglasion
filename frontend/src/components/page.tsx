import type { ReactNode } from "react";

/** Page header. Initial load, error, and retry belong in AsyncPage, not a local spinner. */

export function Page({
  kicker,
  title,
  description,
  actions,
  children,
}: {
  kicker?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          {kicker && <p className="text-xs text-brand">{kicker}</p>}
          <h1 className="text-xl font-bold">{title}</h1>
          {description && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  );
}
