import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  label: string;
  options: string[];
  value: string[];
  onChange: (v: string[]) => void;
  className?: string;
}

/** Compact multi-select dropdown with checkboxes and an inline clear button. */
export function MultiSelect({ label, options, value, onChange, className }: Props) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const toggle = (o: string) => onChange(value.includes(o) ? value.filter((x) => x !== o) : [...value, o]);
  const shown = options.filter((o) => o.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div ref={ref} className={cn("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "flex h-9 min-w-[130px] items-center justify-between gap-2 rounded-lg border bg-background px-3 text-sm shadow-sm hover:bg-accent/60",
          value.length && "border-primary/50 bg-primary/5"
        )}
      >
        <span className="truncate">
          {label}
          {value.length > 0 && <span className="ml-1.5 rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground">{value.length}</span>}
        </span>
        {value.length ? (
          <X className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" onClick={(e) => { e.stopPropagation(); onChange([]); }} />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        )}
      </button>
      {open && (
        <div className="fade-in absolute left-0 top-full z-30 mt-1.5 w-64 rounded-xl border bg-popover p-2 shadow-2xl">
          {options.length > 8 && (
            <input
              autoFocus
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter…"
              className="mb-2 h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
            />
          )}
          <div className="max-h-60 overflow-auto">
            {shown.length === 0 && <div className="px-2 py-3 text-center text-xs text-muted-foreground">No options</div>}
            {shown.map((o) => {
              const on = value.includes(o);
              return (
                <button
                  key={o}
                  type="button"
                  onClick={() => toggle(o)}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
                >
                  <span className={cn("flex h-4 w-4 items-center justify-center rounded border", on ? "border-primary bg-primary text-primary-foreground" : "border-input")}>
                    {on && <Check className="h-3 w-3" />}
                  </span>
                  <span className="truncate">{o}</span>
                </button>
              );
            })}
          </div>
          <div className="mt-2 flex justify-between border-t pt-2">
            <button className="text-xs text-muted-foreground hover:text-foreground" onClick={() => onChange([])}>Clear</button>
            <button className="text-xs font-medium text-primary" onClick={() => setOpen(false)}>Done</button>
          </div>
        </div>
      )}
    </div>
  );
}
