import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { compact } from "@/lib/format";

export interface Series { key: string; label: string; color: string }

interface Props {
  data: Record<string, unknown>[];
  xKey: string;
  series: Series[];
  height?: number;
}

export function MiniBar({ data, xKey, series, height = 260 }: Props) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={4}>
        <defs>
          {series.map((s) => (
            <linearGradient key={s.key} id={`g-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity={0.95} />
              <stop offset="100%" stopColor={s.color} stopOpacity={0.55} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
        <XAxis dataKey={xKey} tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} />
        <YAxis tickLine={false} axisLine={false} width={56} tickFormatter={compact} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
        <Tooltip
          cursor={{ fill: "hsl(var(--accent))", opacity: 0.5 }}
          formatter={(v: number) => v.toLocaleString("en-US", { maximumFractionDigits: 2 })}
          contentStyle={{ background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 12, fontSize: 12 }}
        />
        {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
        {series.map((s) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} fill={`url(#g-${s.key})`} radius={[6, 6, 0, 0]} maxBarSize={44} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
