import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  ChevronDown, ChevronsLeft, LogOut, Menu, Moon, Search, Settings, Sun, User, Wallet, X,
} from "lucide-react";
import { NAV, ALL_ITEMS, allowed } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { CommandPalette } from "@/components/layout/CommandPalette";
import type { Theme } from "@/hooks/useTheme";
import { stamp } from "@/lib/format";

interface Props {
  route: string;
  onNavigate: (route: string) => void;
  can: (key: string) => boolean;
  username: string;
  role: string;
  theme: Theme;
  onToggleTheme: () => void;
  onLogout: () => void;
  /** this user's most recent Generate Summary timestamp ("" = never) */
  lastGenerate?: string;
  children: ReactNode;
}

const RAIL_W = 76;
const FULL_W = 272;

export function Shell({ route, onNavigate, can, username, role, theme, onToggleTheme, onLogout, lastGenerate = "", children }: Props) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [railMode, setRailMode] = useState(() => localStorage.getItem("ssg_nav_rail") === "1");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() => {
    try { return JSON.parse(localStorage.getItem("ssg_nav_collapsed") || "{}"); } catch { return {}; }
  });

  useEffect(() => localStorage.setItem("ssg_nav_collapsed", JSON.stringify(collapsed)), [collapsed]);
  useEffect(() => localStorage.setItem("ssg_nav_rail", railMode ? "1" : "0"), [railMode]);
  useEffect(() => setMobileOpen(false), [route]);

  // Cmd/Ctrl+K opens the command palette from anywhere in the app.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!userMenuOpen) return;
    const h = (e: MouseEvent) => { if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) setUserMenuOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [userMenuOpen]);

  const groups = useMemo(
    () => NAV.map((g) => ({ ...g, items: g.items.filter((i) => allowed(i, can)) })).filter((g) => g.items.length),
    [can]
  );
  const current = ALL_ITEMS.find((i) => i.route === route);
  const initial = username.slice(0, 1).toUpperCase();

  const sidebar = (showLabels: boolean) => (
    <aside
      className="flex h-full flex-col bg-sidebar text-slate-300 transition-[width] duration-200 ease-out"
      style={{ width: showLabels ? FULL_W : RAIL_W }}
    >
      <div className={cn("flex h-16 shrink-0 items-center gap-3", showLabels ? "px-5" : "justify-center px-2")}>
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-500 text-white shadow-lg shadow-indigo-500/30">
          <Wallet className="h-5 w-5" />
        </div>
        {showLabels && (
          <div className="min-w-0 leading-tight">
            <div className="truncate text-[15px] font-semibold tracking-tight text-white">SSG AGT</div>
            <div className="truncate text-[10px] font-medium uppercase tracking-[0.2em] text-indigo-300/80">Account Monitoring · Pro</div>
          </div>
        )}
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto overflow-x-hidden px-3 pb-3 pt-2">
        {groups.map((g) => {
          const groupCollapsed = showLabels && collapsed[g.id] && !g.items.some((i) => i.route === route);
          return (
            <div key={g.id} className="pb-1">
              {showLabels ? (
                <button
                  onClick={() => setCollapsed((c) => ({ ...c, [g.id]: !c[g.id] }))}
                  className="flex w-full items-center justify-between px-3 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500 hover:text-slate-300"
                >
                  {g.label}
                  <ChevronDown className={cn("h-3 w-3 transition-transform duration-150", groupCollapsed && "-rotate-90")} />
                </button>
              ) : (
                <div className="mx-auto my-3 h-px w-6 bg-white/10" />
              )}
              {!groupCollapsed &&
                g.items.map((item) => {
                  const active = item.route === route;
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.route}
                      title={!showLabels ? item.label : undefined}
                      onClick={() => onNavigate(item.route)}
                      className={cn(
                        "group relative flex w-full items-center gap-3 rounded-lg py-2 text-left text-[13px] transition-colors duration-150",
                        showLabels ? "px-3" : "justify-center px-0",
                        active ? "bg-white/[0.09] font-medium text-white" : "text-slate-400 hover:bg-white/[0.05] hover:text-slate-100"
                      )}
                    >
                      {active && (
                        <span
                          className={cn(
                            "absolute rounded-r bg-gradient-to-b from-indigo-400 to-fuchsia-400 transition-all duration-200",
                            showLabels ? "left-0 top-1/2 h-5 w-[3px] -translate-y-1/2" : "left-0 top-1/2 h-7 w-[3px] -translate-y-1/2"
                          )}
                        />
                      )}
                      <Icon className={cn("h-4 w-4 shrink-0 transition-transform duration-150 group-hover:scale-110", active ? "text-indigo-300" : "text-slate-500 group-hover:text-slate-300")} />
                      {showLabels && <span className="truncate">{item.label}</span>}
                    </button>
                  );
                })}
            </div>
          );
        })}
      </nav>

      <div className="border-t border-white/5 p-3">
        <button
          onClick={() => setRailMode((r) => !r)}
          className={cn(
            "hidden w-full items-center gap-2 rounded-lg px-2.5 py-2 text-xs text-slate-400 hover:bg-white/[0.06] hover:text-slate-200 lg:flex",
            !showLabels && "justify-center"
          )}
          title={railMode ? "Expand sidebar" : "Collapse sidebar"}
        >
          <ChevronsLeft className={cn("h-4 w-4 shrink-0 transition-transform duration-200", railMode && "rotate-180")} />
          {showLabels && "Collapse"}
        </button>
      </div>
    </aside>
  );

  return (
    <div className="app-bg min-h-screen">
      <div className="fixed inset-y-0 left-0 z-40 hidden lg:block">{sidebar(!railMode)}</div>

      {/* Mobile drawer — always mounted, slid off-canvas via transform so it animates both ways */}
      <div className={cn("fixed inset-0 z-50 lg:hidden", !mobileOpen && "pointer-events-none")}>
        <div className={cn("absolute inset-0 bg-black/60 transition-opacity duration-200", mobileOpen ? "opacity-100" : "opacity-0")} onClick={() => setMobileOpen(false)} />
        <div className={cn("relative h-full transition-transform duration-200 ease-out", mobileOpen ? "translate-x-0" : "-translate-x-full")} style={{ width: FULL_W }}>
          {sidebar(true)}
          <button className="absolute right-3 top-4 text-white/80 hover:text-white" onClick={() => setMobileOpen(false)}><X className="h-5 w-5" /></button>
        </div>
      </div>

      <div
        className={cn(
          "flex min-h-screen flex-col transition-[margin-left] duration-200 ease-out",
          railMode ? "lg:ml-[76px]" : "lg:ml-[272px]"
        )}
      >
          <header className="sticky top-0 z-30 flex h-16 items-center gap-2 border-b bg-background/75 px-4 backdrop-blur-xl sm:px-6">
            <button className="rounded-lg p-2 hover:bg-accent lg:hidden" onClick={() => setMobileOpen(true)}><Menu className="h-5 w-5" /></button>

            <div className="hidden min-w-0 text-sm sm:block">
              <span className="text-muted-foreground">{current?.group ?? "SSG AGT"}</span>
              {current && <span className="mx-2 text-muted-foreground/50">/</span>}
              <span className="font-medium">{current?.label}</span>
            </div>
            <span className="min-w-0 truncate text-sm font-medium sm:hidden">{current?.label ?? "SSG AGT"}</span>

            <button
              onClick={() => setPaletteOpen(true)}
              className="ml-2 hidden items-center gap-2 rounded-lg border bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent md:ml-6 md:flex"
            >
              <Search className="h-3.5 w-3.5" />
              Search or jump to…
              <kbd className="ml-4 rounded border bg-background px-1.5 py-0.5 text-[10px] font-medium">⌘K</kbd>
            </button>

            <div className="ml-auto flex items-center gap-1">
              <div className="mr-2 hidden flex-col items-end leading-tight md:flex" title="Your most recent Generate action">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Last Generate</span>
                <span className="num text-xs font-medium">{lastGenerate ? stamp(lastGenerate) : "Not generated yet"}</span>
              </div>
              <button onClick={() => setPaletteOpen(true)} className="rounded-lg p-2 text-muted-foreground hover:bg-accent hover:text-foreground md:hidden" title="Search">
                <Search className="h-[18px] w-[18px]" />
              </button>
              <button onClick={onToggleTheme} title="Toggle theme" className="rounded-lg p-2 text-muted-foreground transition-transform hover:bg-accent hover:text-foreground active:scale-90">
                {theme === "dark" ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
              </button>

              <div ref={userMenuRef} className="relative ml-1">
                <button
                  onClick={() => setUserMenuOpen((o) => !o)}
                  className="flex items-center gap-2 rounded-lg py-1 pl-1 pr-2 hover:bg-accent"
                >
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-xs font-semibold text-white">
                    {initial}
                  </div>
                  <ChevronDown className={cn("hidden h-3.5 w-3.5 text-muted-foreground transition-transform duration-150 sm:block", userMenuOpen && "rotate-180")} />
                </button>
                {userMenuOpen && (
                  <div className="fade-in-pop absolute right-0 top-full z-40 mt-2 w-52 overflow-hidden rounded-xl border bg-popover p-1.5 shadow-2xl">
                    <div className="flex items-center gap-2.5 rounded-lg px-2.5 py-2">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-xs font-semibold text-white">
                        {initial}
                      </div>
                      <div className="min-w-0 leading-tight">
                        <div className="truncate text-sm font-medium">{username}</div>
                        <div className="truncate text-[11px] text-muted-foreground">{role}</div>
                      </div>
                    </div>
                    <div className="my-1 h-px bg-border" />
                    {allowed({ route: "admin/users", label: "", icon: User, perm: "admin_users" }, can) && (
                      <button onClick={() => { onNavigate("admin/users"); setUserMenuOpen(false); }} className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm hover:bg-accent">
                        <Settings className="h-4 w-4 text-muted-foreground" /> Admin settings
                      </button>
                    )}
                    <button onClick={onLogout} className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm text-destructive hover:bg-destructive/10">
                      <LogOut className="h-4 w-4" /> Sign out
                    </button>
                  </div>
                )}
              </div>
            </div>
          </header>

        <main key={route} className="page-enter mx-auto w-full max-w-[1720px] flex-1 p-4 sm:p-6">{children}</main>
      </div>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onNavigate={onNavigate}
        can={can}
        onToggleTheme={onToggleTheme}
        onLogout={onLogout}
        theme={theme}
      />
    </div>
  );
}
