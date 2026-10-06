import type { ReactNode } from "react";

interface Props {
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({ title, subtitle, icon, actions }: Props) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="flex items-center gap-3">
        {icon && (
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-violet-500 text-white shadow-lg shadow-primary/25">
            {icon}
          </div>
        )}
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
          {subtitle && <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
