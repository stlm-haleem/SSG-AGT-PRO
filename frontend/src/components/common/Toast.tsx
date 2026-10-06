import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { CheckCircle2, AlertTriangle, X } from "lucide-react";
import { cn } from "@/lib/utils";

type Kind = "success" | "error";
interface ToastItem { id: number; kind: Kind; text: string }
interface ToastApi { success: (t: string) => void; error: (t: string) => void }

const Ctx = createContext<ToastApi>({ success: () => {}, error: () => {} });
export const useToast = () => useContext(Ctx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((kind: Kind, text: string) => {
    const id = Date.now() + Math.random();
    setItems((s) => [...s, { id, kind, text }]);
    setTimeout(() => setItems((s) => s.filter((i) => i.id !== id)), kind === "error" ? 8000 : 4500);
  }, []);
  const api: ToastApi = { success: (t) => push("success", t), error: (t) => push("error", t) };

  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-[100] flex w-[380px] max-w-[calc(100vw-2rem)] flex-col gap-2">
        {items.map((t) => (
          <div
            key={t.id}
            className={cn(
              "fade-in pointer-events-auto flex items-start gap-3 rounded-xl border bg-card p-3.5 text-sm shadow-xl",
              t.kind === "success" ? "border-success/40" : "border-destructive/40"
            )}
          >
            {t.kind === "success" ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
            ) : (
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            )}
            <div className="flex-1 leading-snug">{t.text}</div>
            <button onClick={() => setItems((s) => s.filter((i) => i.id !== t.id))} className="text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
