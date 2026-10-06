import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { count as fmtCount, money } from "@/lib/format";
import { EmptyState } from "@/components/common/States";
import { Pill } from "@/components/common/States";

export interface Table {
  columns: string[];
  financial: string[];
  rows: Record<string, unknown>[];
  counts?: string[];
}

export interface RowSelection {
  /** stable key of a row, e.g. its wallet name */
  rowKey: (row: Record<string, unknown>) => string;
  selected: Set<string>;
  onToggle: (key: string) => void;
  /** select / clear every row currently shown */
  onToggleAll: (keys: string[], on: boolean) => void;
}

interface Props {
  table: Table | null;
  /** extra trailing column (row actions) */
  actions?: (row: Record<string, unknown>) => ReactNode;
  actionsLabel?: string;
  emptyTitle?: string;
  emptyHint?: string;
  dense?: boolean;
  /** render these columns as coloured status pills */
  pillColumns?: string[];
  /** optional checkbox column (batch actions) */
  selection?: RowSelection;
  /** max height of the scroll area, e.g. "70vh" */
  maxHeight?: string;
  className?: string;
}

const isTotal = (row: Record<string, unknown>, first: string) => {
  const v = String(row[first] ?? "").trim().toUpperCase();
  return v === "TOTAL" || v === "GRAND TOTAL";
};

function pillTone(text: string): "success" | "danger" | "warning" | "info" | "neutral" {
  const t = text.toLowerCase();
  if (!t) return "neutral";
  if (/(log ?in|active|normal|yes|ok|confirmed)/.test(t) && !/(locked|disabled|inactive)/.test(t)) return "success";
  if (/(lock|delet|stop|log ?out|disabled|frozen|closed|reach limit|kyc)/.test(t)) return "danger";
  if (/(pending|withdraw|wd)/.test(t)) return "warning";
  return "info";
}

export function DataTable({ table, actions, actionsLabel = "", emptyTitle = "No data", emptyHint, dense, pillColumns = [], selection, maxHeight = "68vh", className }: Props) {
  if (!table || !table.rows.length) {
    return (
      <div className={cn("table-scroll", className)}>
        <EmptyState title={emptyTitle} hint={emptyHint} />
      </div>
    );
  }
  const fin = new Set(table.financial);
  const cnt = new Set(table.counts ?? []);
  const first = table.columns[0];
  const pad = dense ? "px-3 py-1.5" : "px-3.5 py-2.5";
  const pageKeys = selection ? table.rows.map((r) => selection.rowKey(r)) : [];
  const allOn = !!selection && pageKeys.length > 0 && pageKeys.every((k) => selection.selected.has(k));
  const someOn = !!selection && pageKeys.some((k) => selection.selected.has(k));

  return (
    <div className={cn("table-scroll bg-card", className)} style={{ maxHeight }}>
      <table className="w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            {selection && (
              <th className={cn("sticky top-0 z-10 w-8 border-b bg-muted/90 backdrop-blur", pad)}>
                <input
                  type="checkbox"
                  aria-label="Select all rows on this page"
                  className="h-3.5 w-3.5 cursor-pointer accent-[hsl(var(--primary))]"
                  checked={allOn}
                  ref={(el) => { if (el) el.indeterminate = !allOn && someOn; }}
                  onChange={(e) => selection.onToggleAll(pageKeys, e.target.checked)}
                />
              </th>
            )}
            {table.columns.map((c) => (
              <th
                key={c}
                className={cn(
                  "sticky top-0 z-10 whitespace-nowrap border-b bg-muted/90 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground backdrop-blur",
                  pad,
                  fin.has(c) || cnt.has(c) ? "text-right" : "text-left"
                )}
              >
                {c}
              </th>
            ))}
            {actions && <th className={cn("sticky top-0 z-10 border-b bg-muted/90 text-right text-[11px] uppercase tracking-wider text-muted-foreground backdrop-blur", pad)}>{actionsLabel}</th>}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => {
            const total = isTotal(row, first);
            return (
              <tr key={i} className={cn("transition-colors", total ? "bg-primary/[0.06] font-semibold" : "hover:bg-accent/60", selection?.selected.has(selection.rowKey(row)) && "bg-primary/[0.07]")}>
                {selection && (
                  <td className={cn("w-8 whitespace-nowrap border-b border-border/60", pad)}>
                    <input
                      type="checkbox"
                      aria-label="Select row"
                      className="h-3.5 w-3.5 cursor-pointer accent-[hsl(var(--primary))]"
                      checked={selection.selected.has(selection.rowKey(row))}
                      onChange={() => selection.onToggle(selection.rowKey(row))}
                    />
                  </td>
                )}
                {table.columns.map((c) => {
                  const v = row[c];
                  const isFin = fin.has(c);
                  const isCnt = cnt.has(c);
                  const n = typeof v === "number" ? v : Number(String(v ?? "").replace(/,/g, ""));
                  let content: ReactNode;
                  if (isFin) content = money(v);
                  else if (isCnt) content = fmtCount(v);
                  else if (pillColumns.includes(c) && v) content = <Pill tone={pillTone(String(v))}>{String(v)}</Pill>;
                  else content = v === null || v === undefined ? "" : String(v);
                  return (
                    <td
                      key={c}
                      className={cn(
                        "whitespace-nowrap border-b border-border/60",
                        pad,
                        (isFin || isCnt) && "num text-right",
                        isFin && !Number.isNaN(n) && n < 0 && "text-destructive",
                        isFin && (v === 0 || v === null) && "text-muted-foreground/60",
                        c === first && !total && "font-medium"
                      )}
                    >
                      {content}
                    </td>
                  );
                })}
                {actions && <td className={cn("whitespace-nowrap border-b border-border/60 text-right", pad)}>{actions(row)}</td>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
