import type { ReactNode } from "react";
import { Page } from "../page";
import { Alert } from "./alert";
import { Button } from "./button";
import { Skeleton } from "./skeleton";

export type SkeletonVariant = "stats" | "table" | "form";

/**
 * The only page-load skeleton. Initial route load uses this.
 * A button action uses Button loading. A small inline wait uses Spinner.
 */
export function PageSkeleton({ variant = "stats" }: { variant?: SkeletonVariant }) {
  if (variant === "table") {
    return (
      <div className="space-y-2" aria-busy="true" aria-label="در حال خواندن">
        <Skeleton shimmer className="h-10 w-full rounded-xl" />
        {Array.from({ length: 5 }).map((_, index) => <Skeleton key={index} shimmer className="h-12 w-full rounded-xl" />)}
      </div>
    );
  }
  if (variant === "form") {
    return (
      <div className="space-y-3" aria-busy="true" aria-label="در حال خواندن">
        <Skeleton shimmer className="h-10 w-56 rounded-xl" />
        <Skeleton shimmer className="h-36 w-full rounded-2xl" />
        <Skeleton shimmer className="h-36 w-full rounded-2xl" />
      </div>
    );
  }
  return (
    <div className="space-y-3" aria-busy="true" aria-label="در حال خواندن">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} shimmer className="h-24 rounded-2xl" />)}
      </div>
      <Skeleton shimmer className="h-40 w-full rounded-2xl" />
    </div>
  );
}

export function LoadError({ title, onRetry }: { title: string; onRetry?: () => void }) {
  return (
    <Alert variant="warning" title={title}>
      {onRetry && <Button className="mt-3" variant="outline" onClick={onRetry}>دوباره</Button>}
    </Alert>
  );
}

export function AsyncPage({
  title,
  kicker,
  description,
  actions,
  loading,
  error,
  onRetry,
  skeleton = "stats",
  children,
}: {
  title: string;
  kicker?: string;
  description?: string;
  actions?: ReactNode;
  loading?: boolean;
  error?: string;
  onRetry?: () => void;
  skeleton?: SkeletonVariant;
  children?: ReactNode;
}) {
  return (
    <Page kicker={kicker} title={title} description={description} actions={loading ? undefined : actions}>
      {loading ? <PageSkeleton variant={skeleton} /> : (
        <>
          {error && <LoadError title={error} onRetry={onRetry} />}
          {children}
        </>
      )}
    </Page>
  );
}
