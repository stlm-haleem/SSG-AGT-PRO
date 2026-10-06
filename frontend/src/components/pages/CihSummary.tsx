import { useState } from "react";
import { RefreshCw, Sigma } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/common/PageHeader";
import { DataTable, type Table } from "@/components/common/DataTable";
import { DashboardSkeleton, ErrorNote } from "@/components/common/States";
import { useFetch } from "@/hooks/useFetch";
import { cn } from "@/lib/utils";

export function CihSummary({ token }: { token: string }) {
  const { data, loading, error, reload } = useFetch<{ tabs: { name: string; table: Table }[] }>("/ssg/cih/summary", token);
  const [active, setActive] = useState(0);
  if (loading && !data) return <DashboardSkeleton kpis={0} />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;
  const tab = data.tabs[active];
  return (
    <div className="space-y-5">
      <PageHeader icon={<Sigma className="h-5 w-5" />} title="CIH Summary" subtitle="Deposit type, merchant deposit and merchant pay out by period"
        actions={<Button variant="outline" size="sm" onClick={() => reload()}><RefreshCw className="h-3.5 w-3.5" /> Refresh</Button>} />
      <div className="inline-flex rounded-xl border bg-muted/60 p-1">
        {data.tabs.map((t, i) => (
          <button key={t.name} onClick={() => setActive(i)} className={cn("rounded-lg px-4 py-1.5 text-sm transition-all", i === active ? "bg-card font-medium shadow-sm" : "text-muted-foreground hover:text-foreground")}>
            {t.name}
          </button>
        ))}
      </div>
      <section className="surface p-5">
        <DataTable table={tab.table} emptyTitle="Nothing generated yet" emptyHint="Go to Data → Data Import and click Generate Summary." />
      </section>
    </div>
  );
}
