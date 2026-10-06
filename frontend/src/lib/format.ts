/** 12,345.67 — blank/zero shows as an em dash the way the SSG tables always did. */
export function money(v: unknown, dashZero = true): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "number" ? v : Number(String(v).replace(/,/g, ""));
  if (Number.isNaN(n)) return String(v);
  if (dashZero && Math.abs(n) < 1e-9) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function count(v: unknown): string {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(String(v).replace(/,/g, ""));
  if (Number.isNaN(n)) return String(v);
  return n === 0 ? "—" : n.toLocaleString("en-US");
}

/** 1.2M / 340K style for chart axes and KPI subtitles. */
export function compact(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return n.toFixed(0);
}

export function toNumber(v: unknown): number {
  const n = typeof v === "number" ? v : Number(String(v ?? "").replace(/,/g, ""));
  return Number.isNaN(n) ? 0 : n;
}

/** "2026-10-05T14:03:22+05:30" -> "2026-10-05 14:03:22+05:30" (the stamp keeps the generating PC's UTC offset). */
export function stamp(v: string | null | undefined): string {
  return String(v ?? "").replace("T", " ");
}

/** Current local time with the PC's UTC offset, e.g. 2026-10-05T14:03:22+05:30 (sent when Generate is clicked). */
export function localIsoStamp(d: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const a = Math.abs(off);
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}${sign}${p(Math.floor(a / 60))}:${p(a % 60)}`;
}
