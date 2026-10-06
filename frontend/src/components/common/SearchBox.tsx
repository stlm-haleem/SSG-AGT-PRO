import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
}

export function SearchBox({ value, onChange, placeholder = "Search…", className }: Props) {
  return (
    <div className={cn("relative", className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-9 w-full min-w-[220px] rounded-lg border bg-background pl-9 pr-8 text-sm shadow-sm outline-none placeholder:text-muted-foreground focus:border-primary/60 focus:ring-2 focus:ring-primary/20"
      />
      {value && (
        <button className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground" onClick={() => onChange("")}>
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
