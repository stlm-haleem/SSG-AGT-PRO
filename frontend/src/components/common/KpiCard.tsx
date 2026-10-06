import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useCountUp } from "@/hooks/useCountUp";

type Tone = "primary" | "success" | "danger" | "warning" | "info" | "neutral";

const TONES: Record<Tone, { chip: string; bar: string }> = {
  primary: { chip: "bg-primary/10 text-primary", bar: "from-primary to-violet-500" },
  success: { chip: "bg-success/10 text-success", bar: "from-emerald-500 to-teal-400" },
  danger: { chip: "bg-destructive/10 text-destructive", bar: "from-rose-500 to-orange-400" },
  warning: { chip: "bg-warning/10 text-warning", bar: "from-amber-500 to-yellow-400" },
  info: { chip: "bg-sky-500/10 text-sky-600 dark:text-sky-400", bar: "from-sky-500 to-cyan-400" },
  neutral: { chip: "bg-muted text-muted-foreground", bar: "from-slate-400 to-slate-300" },
};

interface Props {
  label: string;
  value: ReactNode;
  /** When set alongside `format`, the displayed number animates toward this
   * value on change instead of just appearing — cheap (CSS-free, rAF-driven,
   * numbers only) and skipped entirely on first render. */
  numeric?: number;
  format?: (n: number) => string;
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: Tone;
  className?: string;
}

export function KpiCard({ label, value, numeric, format, hint, icon, tone = "primary", className }: Props) {
  const t = TONES[tone];
  const animated = useCountUp(numeric ?? 0);
  const display = numeric !== undefined && format ? format(animated) : value;
  return (
    <div className={cn("surface fade-in group relative overflow-hidden p-4 transition-shadow hover:shadow-md", className)}>
      <div className={cn("absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r opacity-90", t.bar)} />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
          <div className="num mt-1.5 truncate text-2xl font-semibold tracking-tight">{display}</div>
          {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
        </div>
        {icon && (
          <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-transform group-hover:scale-110", t.chip)}>
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}
