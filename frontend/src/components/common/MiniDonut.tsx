import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { compact } from "@/lib/format";

export interface Slice { name: string; value: number; color: string }

interface Props {
  data: Slice[];
  height?: number;
  centerLabel?: string;
  centerValue?: string;
}

/** Small donut chart with an optional centered total label. */
export function MiniDonut({ data, height = 220, centerLabel, centerValue }: Props) {
  const total = data.reduce((s, d) => s + d.value, 0);
  return (
    <div className="relative" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="92%" paddingAngle={2} stroke="none">
            {data.map((d) => (
              <Cell key={d.name} fill={d.color} />
            ))}
          </Pie>
          <Tooltip
            formatter={(v: number, n: string) => [v.toLocaleString("en-US", { maximumFractionDigits: 2 }), n]}
            contentStyle={{ background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 12, fontSize: 12 }}
          />
        </PieChart>
      </ResponsiveContainer>
      {(centerLabel || centerValue) && (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <div className="num text-lg font-semibold">{centerValue ?? compact(total)}</div>
          {centerLabel && <div className="text-[11px] text-muted-foreground">{centerLabel}</div>}
        </div>
      )}
      <div className="mt-1 flex flex-wrap justify-center gap-x-3 gap-y-1">
        {data.map((d) => (
          <span key={d.name} className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <span className="h-2 w-2 rounded-full" style={{ background: d.color }} />
            {d.name}
          </span>
        ))}
      </div>
    </div>
  );
}
