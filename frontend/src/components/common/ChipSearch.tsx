import { useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  /** committed search terms (chips) */
  terms: string[];
  onTermsChange: (terms: string[]) => void;
  /** text typed but not yet committed with Enter — it still filters live */
  draft: string;
  onDraftChange: (v: string) => void;
  placeholder?: string;
  className?: string;
}

/** Split pasted / typed text on comma, semicolon, pipe or newline — the same separators the
 * backend search understands. */
export const splitTerms = (v: string) => v.split(/[,;|\n\r]+/).map((t) => t.trim()).filter(Boolean);

/** Join chips + the live draft into the single `q` string the API expects (OR matching). */
export const joinTerms = (terms: string[], draft: string) => [...terms, ...splitTerms(draft)].join(",");

/**
 * Enter-to-chip multi-account search (supervisor V1.83): type an account name / number and press
 * Enter to turn it into a removable chip; every chip stays active and matches with OR.
 * Backspace on an empty input removes the last chip; each chip has its own X.
 */
export function ChipSearch({ terms, onTermsChange, draft, onDraftChange, placeholder = "Account name / number, then Enter", className }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [focused, setFocused] = useState(false);

  const commit = (raw: string) => {
    const incoming = splitTerms(raw);
    if (!incoming.length) return;
    const merged = [...terms];
    incoming.forEach((t) => { if (!merged.some((m) => m.toLowerCase() === t.toLowerCase())) merged.push(t); });
    onTermsChange(merged);
    onDraftChange("");
  };

  return (
    <div
      onClick={() => inputRef.current?.focus()}
      className={cn(
        "flex min-h-9 min-w-[260px] flex-wrap items-center gap-1.5 rounded-lg border bg-background px-2.5 py-1 shadow-sm",
        focused && "border-primary/60 ring-2 ring-primary/20",
        className
      )}
    >
      <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
      {terms.map((t) => (
        <span key={t} className="inline-flex items-center gap-1 rounded-full bg-primary/10 py-0.5 pl-2.5 pr-1 text-xs font-medium text-primary">
          {t}
          <button
            type="button"
            aria-label={`Remove ${t}`}
            className="rounded-full p-0.5 hover:bg-primary/20"
            onClick={(e) => { e.stopPropagation(); onTermsChange(terms.filter((x) => x !== t)); }}
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => onDraftChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); commit(draft); }
          else if (e.key === "Backspace" && !draft && terms.length) onTermsChange(terms.slice(0, -1));
        }}
        onPaste={(e) => {
          const text = e.clipboardData.getData("text");
          if (/[,;|\n\r]/.test(text)) { e.preventDefault(); commit(text); }
        }}
        placeholder={terms.length ? "Add another…" : placeholder}
        className="h-7 min-w-[120px] flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
      />
      {(terms.length > 0 || draft) && (
        <button
          type="button"
          aria-label="Clear search"
          className="text-muted-foreground hover:text-foreground"
          onClick={(e) => { e.stopPropagation(); onTermsChange([]); onDraftChange(""); }}
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
