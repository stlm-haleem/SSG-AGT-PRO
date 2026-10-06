import type { CSSProperties, ReactNode } from "react";
import { Inbox, Loader2, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-4 w-4 animate-spin", className)} />;
}

export function LoadingBlock({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="surface flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
      <Spinner /> {label}
    </div>
  );
}

/** Plain shimmering block — pure CSS animation (see .skeleton in index.css),
 * no JS cost beyond rendering a div. */
export function Skeleton({ className, style }: { className?: string; style?: CSSProperties }) {
  return <div className={cn("skeleton", className)} style={style} />;
}

/** Table-shaped loading placeholder, swapped in for <LoadingBlock /> on pages
 * whose content is a DataTable — gives an immediate sense of the page's
 * shape instead of a blank spinner, at no extra runtime cost. */
export function TableSkeleton({ rows = 8, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <div className="fade-in space-y-2.5">
      <div className="flex gap-3">
        {Array.from({ length: cols }).map((_, i) => <Skeleton key={i} className="h-4 flex-1" />)}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3">
          {Array.from({ length: cols }).map((_, i) => <Skeleton key={i} className="h-8 flex-1" style={{ animationDelay: `${(r * cols + i) * 15}ms` }} />)}
        </div>
      ))}
    </div>
  );
}

/** KPI-row-shaped loading placeholder for dashboard-style pages. */
export function KpiSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="surface p-4">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="mt-3 h-7 w-28" />
          <Skeleton className="mt-2 h-3 w-24" />
        </div>
      ))}
    </div>
  );
}

/** Full-page placeholder for KPI + chart + table dashboard pages — mirrors
 * their actual layout so the page doesn't "jump" once data arrives. */
export function DashboardSkeleton({ kpis = 4 }: { kpis?: number }) {
  return (
    <div className="fade-in space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Skeleton className="h-6 w-56" />
          <Skeleton className="mt-2 h-3.5 w-80" />
        </div>
        <Skeleton className="h-8 w-24" />
      </div>
      <KpiSkeleton count={kpis} />
      <div className="grid gap-6 xl:grid-cols-3">
        <div className="surface p-5 xl:col-span-1"><Skeleton className="h-48 w-full" /></div>
        <div className="surface p-5 xl:col-span-2"><TableSkeleton rows={5} cols={5} /></div>
      </div>
    </div>
  );
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
        <Inbox className="h-6 w-6" />
      </div>
      <div className="text-sm font-medium">{title}</div>
      {hint && <div className="max-w-md text-xs text-muted-foreground">{hint}</div>}
      {action}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
      <AlertTriangle className="h-4 w-4 shrink-0" /> {message}
    </div>
  );
}

export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "success" | "danger" | "warning" | "info" | "primary" }) {
  const map = {
    neutral: "bg-muted text-muted-foreground",
    success: "bg-success/12 text-success",
    danger: "bg-destructive/12 text-destructive",
    warning: "bg-warning/15 text-warning",
    info: "bg-sky-500/12 text-sky-600 dark:text-sky-400",
    primary: "bg-primary/12 text-primary",
  } as const;
  return <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium", map[tone])}>{children}</span>;
}
