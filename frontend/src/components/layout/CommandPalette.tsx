import { useEffect, useMemo, useRef, useState } from "react";
import { CornerDownLeft, LogOut, Moon, Search, Sun } from "lucide-react";
import { ALL_ITEMS, allowed } from "@/lib/nav";
import { cn } from "@/lib/utils";

interface Entry {
  key: string;
  label: string;
  group: string;
  icon: React.ComponentType<{ className?: string }>;
  run: () => void;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onNavigate: (route: string) => void;
  can: (key: string) => boolean;
  onToggleTheme: () => void;
  onLogout: () => void;
  theme: "light" | "dark";
}

/** Lightweight Cmd/Ctrl+K command palette — plain React + Tailwind, no extra
 * dependency. Lists pages the user can access plus a couple of quick actions. */
export function CommandPalette({ open, onClose, onNavigate, can, onToggleTheme, onLogout, theme }: Props) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const entries = useMemo<Entry[]>(() => {
    const pages: Entry[] = ALL_ITEMS.filter((i) => allowed(i, can)).map((i) => ({
      key: i.route,
      label: i.label,
      group: i.group,
      icon: i.icon,
      run: () => onNavigate(i.route),
    }));
    const actions: Entry[] = [
      { key: "theme", label: theme === "dark" ? "Switch to light mode" : "Switch to dark mode", group: "Quick actions", icon: theme === "dark" ? Sun : Moon, run: onToggleTheme },
      { key: "logout", label: "Sign out", group: "Quick actions", icon: LogOut, run: onLogout },
    ];
    return [...pages, ...actions];
  }, [can, onNavigate, onToggleTheme, onLogout, theme]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter((e) => e.label.toLowerCase().includes(q) || e.group.toLowerCase().includes(q));
  }, [entries, query]);

  useEffect(() => setActive(0), [query]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, filtered.length - 1)); }
      if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
      if (e.key === "Enter") {
        e.preventDefault();
        const pick = filtered[active];
        if (pick) { pick.run(); onClose(); }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, filtered, active, onClose]);

  if (!open) return null;

  let lastGroup = "";

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[12vh]" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="fade-in-pop surface relative w-full max-w-lg overflow-hidden p-0 shadow-2xl">
        <div className="flex items-center gap-2.5 border-b px-4 py-3">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search pages, actions…"
            className="h-6 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          <kbd className="rounded border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">Esc</kbd>
        </div>
        <div className="max-h-[50vh] overflow-y-auto p-1.5">
          {filtered.length === 0 && <div className="px-3 py-8 text-center text-sm text-muted-foreground">No matches</div>}
          {filtered.map((e, i) => {
            const showGroup = e.group !== lastGroup;
            lastGroup = e.group;
            const Icon = e.icon;
            return (
              <div key={e.key}>
                {showGroup && (
                  <div className="px-2.5 pb-1 pt-2.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{e.group}</div>
                )}
                <button
                  onMouseEnter={() => setActive(i)}
                  onClick={() => { e.run(); onClose(); }}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-colors",
                    i === active ? "bg-primary/10 text-primary" : "hover:bg-accent"
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="flex-1 truncate">{e.label}</span>
                  {i === active && <CornerDownLeft className="h-3.5 w-3.5 opacity-60" />}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
