import { WalletCards, Banknote, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/common/PageHeader";
import { KpiCard } from "@/components/common/KpiCard";
import { DataTable, type Table } from "@/components/common/DataTable";
import { DashboardSkeleton, ErrorNote } from "@/components/common/States";
import { MiniBar } from "@/components/common/MiniBar";
import { MiniDonut } from "@/components/common/MiniDonut";
import { useFetch } from "@/hooks/useFetch";
import { money, compact } from "@/lib/format";

const DONUT_COLORS = ["#6366f1", "#14b8a6", "#f59e0b", "#f43f5e", "#0ea5e9", "#a855f7"];

interface Resp {
  kind: string;
  wallets: string[];
  cards: { wallet: string; system_balance: number | null }[];
  table: Table;
  counts: { title: string; table: Table }[];
}

const TONES = ["primary", "info", "warning", "success"] as const;

export function CihWallets({ token, personal }: { token: string; personal: boolean }) {
  const { data, loading, error, reload } = useFetch<Resp>(`/ssg/cih/${personal ? "personal" : "agent"}`, token);
  if (loading && !data) return <DashboardSkeleton kpis={5} />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const rows = data.table.rows.filter((r) => String(r["Wallet Name"]).toUpperCase() !== "TOTAL");
  const chartData = rows.map((r) => ({
    wallet: r["Wallet Name"], "System Balance": Number(r["System Balance"] ?? 0), "Final Closing Bal": Number(r["Final Closing Bal"] ?? 0),
  }));
  const totalSystem = data.cards.reduce((s, c) => s + (c.system_balance ?? 0), 0);
  const shareSlices = data.cards
    .map((c, i) => ({ name: c.wallet, value: Math.max(c.system_balance ?? 0, 0), color: DONUT_COLORS[i % DONUT_COLORS.length] }))
    .filter((s) => s.value > 0);

  return (
    <div className="space-y-6">
      <PageHeader
        icon={personal ? <Banknote className="h-5 w-5" /> : <WalletCards className="h-5 w-5" />}
        title={personal ? "Personal Wallet Balances" : "Agent Wallet Balances"}
        subtitle={`Wallet-level CIH position for ${data.wallets.join(", ")}`}
        actions={<Button variant="outline" size="sm" onClick={() => reload()}><RefreshCw className="h-3.5 w-3.5" /> Refresh</Button>}
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {data.cards.map((c, i) => (
          <KpiCard key={c.wallet} label={c.wallet} value={money(c.system_balance, false)} numeric={c.system_balance ?? 0} format={(n) => money(n, false)} hint="System balance" tone={TONES[i % 4]} icon={<WalletCards className="h-4 w-4" />} />
        ))}
        <KpiCard label="All wallets" value={compact(totalSystem)} numeric={totalSystem} format={compact} hint="Combined system balance" tone="neutral" />
      </div>

      <div className="grid gap-6 xl:grid-cols-4">
        <section className="surface p-5 xl:col-span-1">
          <h2 className="text-sm font-semibold">Wallet share</h2>
          <p className="mb-2 text-xs text-muted-foreground">Of combined system balance</p>
          {shareSlices.length ? <MiniDonut data={shareSlices} centerLabel="Total" centerValue={compact(totalSystem)} /> : (
            <div className="py-14 text-center text-sm text-muted-foreground">No balances yet</div>
          )}
        </section>
        <section className="surface p-5 xl:col-span-1">
          <h2 className="text-sm font-semibold">System vs closing balance</h2>
          <p className="mb-2 text-xs text-muted-foreground">Per wallet family</p>
          <MiniBar data={chartData} xKey="wallet" series={[
            { key: "System Balance", label: "System", color: "#6366f1" },
            { key: "Final Closing Bal", label: "Closing", color: "#f59e0b" },
          ]} />
        </section>
        <section className="surface p-5 xl:col-span-2">
          <h2 className="mb-3 text-sm font-semibold">{personal ? "Personal" : "Agent"} wallet balances</h2>
          <DataTable table={data.table} dense emptyTitle="No wallet data" emptyHint="Import Limit, Opening and the histories, then generate the summary." />
        </section>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        {data.counts.map((c) => (
          <section key={c.title} className="surface p-5">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{c.title}</h2>
            <DataTable table={c.table} dense emptyTitle="No counts yet" />
          </section>
        ))}
      </div>
    </div>
  );
}
