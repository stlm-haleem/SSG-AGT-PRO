import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface PageMeta { page: number; per_page: number; total: number; pages: number }

interface Props {
  meta: PageMeta | null;
  onPage: (p: number) => void;
  onPerPage: (n: number) => void;
}

export function Pagination({ meta, onPage, onPerPage }: Props) {
  if (!meta) return null;
  const from = meta.total ? (meta.page - 1) * meta.per_page + 1 : 0;
  const to = Math.min(meta.total, meta.page * meta.per_page);
  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
      <div className="num">
        Showing <span className="font-medium text-foreground">{from.toLocaleString()}–{to.toLocaleString()}</span> of{" "}
        <span className="font-medium text-foreground">{meta.total.toLocaleString()}</span>
      </div>
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-1.5">
          Rows
          <select
            value={meta.per_page}
            onChange={(e) => onPerPage(Number(e.target.value))}
            className="h-8 rounded-md border border-input bg-background px-2 text-xs text-foreground"
          >
            {[25, 50, 100, 250].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" disabled={meta.page <= 1} onClick={() => onPage(1)}><ChevronsLeft /></Button>
          <Button variant="outline" size="icon" disabled={meta.page <= 1} onClick={() => onPage(meta.page - 1)}><ChevronLeft /></Button>
          <span className="num px-2 text-foreground">Page {meta.page} / {meta.pages}</span>
          <Button variant="outline" size="icon" disabled={meta.page >= meta.pages} onClick={() => onPage(meta.page + 1)}><ChevronRight /></Button>
          <Button variant="outline" size="icon" disabled={meta.page >= meta.pages} onClick={() => onPage(meta.pages)}><ChevronsRight /></Button>
        </div>
      </div>
    </div>
  );
}
