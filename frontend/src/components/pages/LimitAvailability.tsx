import { useState } from "react";
import { BarChart3, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/common/PageHeader";
import { KpiCard } from "@/components/common/KpiCard";
import { DataTable, type Table } from "@/components/common/DataTable";
import { DashboardSkeleton, ErrorNote } from "@/components/common/States";
import { MiniBar } from "@/components/common/MiniBar";
import { useFetch } from "@/hooks/useFetch";
import { money } from "@/lib/format";

interface Resp {
  agent_limit: Table; agent_limit_total: Table; agent_count: Table; agent_count_total: Table;
  personal_limit: Table; personal_limit_total: Table; personal_count: Table; personal_count_total: Table;
  overall_agent: number | null; overall_personal: number | null;
  personal_mode?: "daily" | "monthly";
}

const join = (a: Table, b: Table): Table => ({ ...a, columns: a.columns.length ? a.columns : b.columns, rows: [...a.rows, ...b.rows], counts: a.counts });

export function LimitAvailability({ token }: { token: string }) {
  // Personal accounts: Daily (default) or Monthly = eligible account count x 300,000
  const [mode, setMode] = useState<"daily" | "monthly">("daily");
  const { data, loading, error, reload } = useFetch<Resp>(`/ssg/cih/limit-availability?personal_mode=${mode}`, token);
  if (loading && !data) return <DashboardSkeleton kpis={2} />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const cnt = (t: Table): Table => ({ ...t, financial: [], counts: t.columns.slice(1) });
  const compareChart = [{ label: "Agent", Available: data.overall_agent ?? 0 }, { label: "Personal", Available: data.overall_personal ?? 0 }];

  return (
    <div className="space-y-6">
      <PageHeader icon={<BarChart3 className="h-5 w-5" />} title="Limit Availability" subtitle="Remaining DP limit by wallet and working-hours bucket"
        actions={<Button variant="outline" size="sm" onClick={() => reload()}><RefreshCw className="h-3.5 w-3.5" /> Refresh</Button>} />
      <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
        <KpiCard label="Overall agent availability" value={money(data.overall_agent, false)} numeric={data.overall_agent ?? 0} format={(n) => money(n, false)} tone="primary" />
        <KpiCard label="Overall personal availability" value={money(data.overall_personal, false)} numeric={data.overall_personal ?? 0} format={(n) => money(n, false)} tone="info" />
        <div className="surface p-3 sm:col-span-2 xl:col-span-1">
          <MiniBar data={compareChart} xKey="label" height={110} series={[{ key: "Available", label: "Available", color: "#6366f1" }]} />
        </div>
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        <section className="surface p-5">
          <h2 className="mb-3 text-sm font-semibold">Agent — limit left</h2>
          <DataTable table={join(data.agent_limit, data.agent_limit_total)} dense />
        </section>
        <section className="surface p-5">
          <h2 className="mb-3 text-sm font-semibold">Agent — account counts</h2>
          <DataTable table={cnt(join(data.agent_count, data.agent_count_total))} dense />
        </section>
        <section className="surface p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">Personal — limit left ({mode === "monthly" ? "monthly" : "daily"})</h2>
            <div className="flex items-center gap-2">
              <div className="inline-flex rounded-lg border p-0.5" role="group" aria-label="Personal account limit period">
                {(["daily", "monthly"] as const).map((m) => (
                  <button key={m} onClick={() => setMode(m)}
                    className={cn("rounded-md px-3 py-1 text-xs font-medium capitalize transition-colors", mode === m ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>
                    {m}
                  </button>
                ))}
              </div>
              {mode === "monthly" && <span className="text-[11px] text-muted-foreground">Eligible account count × 300,000</span>}
            </div>
          </div>
          <DataTable table={join(data.personal_limit, data.personal_limit_total)} dense />
        </section>
        <section className="surface p-5">
          <h2 className="mb-3 text-sm font-semibold">Personal — account counts</h2>
          <DataTable table={cnt(join(data.personal_count, data.personal_count_total))} dense />
        </section>
      </div>
    </div>
  );
}
