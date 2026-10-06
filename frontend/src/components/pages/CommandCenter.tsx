import { useState } from "react";
import { ArrowDownToLine, ArrowUpFromLine, RefreshCw, Scale, Send, Repeat2, LayoutDashboard } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/common/PageHeader";
import { KpiCard } from "@/components/common/KpiCard";
import { DataTable, type Table } from "@/components/common/DataTable";
import { DashboardSkeleton, ErrorNote, Spinner } from "@/components/common/States";
import { MiniBar } from "@/components/common/MiniBar";
import { MiniDonut } from "@/components/common/MiniDonut";
import { useToast } from "@/components/common/Toast";
import { useFetch } from "@/hooks/useFetch";
import { apiSend } from "@/lib/api";
import { money } from "@/lib/format";

interface Resp {
  totals: Record<string, number>;
  utilization: { agent: Table; personal_ebanking: Table; personal_ibanking: Table };
  telegram_configured: boolean;
}

const REPORTS: [string, string][] = [
  ["limit-utilization", "Limit utilization"],
  ["cih-agent", "CIH agent"],
  ["cih-personal", "CIH personal"],
  ["limit-availability", "Limit availability"],
  ["all", "Send all"],
];

export function CommandCenter({ token, can }: { token: string; can: (k: string) => boolean }) {
  const { data, loading, error, reload } = useFetch<Resp>("/ssg/dashboard", token);
  const toast = useToast();
  const [sending, setSending] = useState("");

  const send = async (name: string) => {
    setSending(name);
    try {
      const r = await apiSend<{ message: string }>(`/ssg/telegram/send/${name}`, token, "POST");
      toast.success(r.message);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Send failed");
    } finally {
      setSending("");
    }
  };

  if (loading && !data) return <DashboardSkeleton kpis={4} />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const t = data.totals;
  const dep = t["Total Deposit"] ?? 0;
  const pay = t["Total Pay out"] ?? 0;
  const stlm = t["Total STLM / Top Up"] ?? 0;
  const noData = dep === 0 && pay === 0 && data.utilization.agent.rows.length <= 1;

  const chart = data.utilization.agent.rows
    .filter((r) => String(r["WALLET"]).toUpperCase() !== "TOTAL")
    .map((r) => ({ wallet: r["WALLET"], Limit: Number(r["LIMIT"] ?? 0), Deposit: Number(r["DEPOSIT"] ?? 0) }));

  const flowSlices = [
    { name: "Deposit", value: Math.max(dep, 0), color: "#14b8a6" },
    { name: "Pay out", value: Math.max(pay, 0), color: "#f43f5e" },
    { name: "STLM / Top Up", value: Math.abs(stlm), color: "#6366f1" },
  ].filter((s) => s.value > 0);

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<LayoutDashboard className="h-5 w-5" />}
        title="Command Center"
        subtitle="Live view of today's deposits, payouts and limit utilization"
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => reload()}><RefreshCw className="h-3.5 w-3.5" /> Refresh</Button>
            {data.telegram_configured && can("imports_telegram_reports") && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="mr-1 flex items-center gap-1.5 text-xs text-muted-foreground"><Send className="h-3.5 w-3.5" /> Telegram</span>
                {REPORTS.map(([k, label]) => (
                  <Button key={k} size="sm" variant={k === "all" ? "default" : "outline"} disabled={!!sending} onClick={() => send(k)}>
                    {sending === k && <Spinner />} {label}
                  </Button>
                ))}
              </div>
            )}
          </>
        }
      />

      {noData && (
        <div className="surface border-dashed p-5 text-sm text-muted-foreground">
          No current data yet. Open <b className="text-foreground">Data → Data Import</b>, upload Deposit History, Pay Out History and Limit,
          then generate the summary — this page fills in automatically.
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Total Deposit" value={money(dep, false)} numeric={dep} format={(n) => money(n, false)} icon={<ArrowDownToLine className="h-4 w-4" />} tone="success" hint="Successful transactions" />
        <KpiCard label="Total Pay out" value={money(pay, false)} numeric={pay} format={(n) => money(n, false)} icon={<ArrowUpFromLine className="h-4 w-4" />} tone="danger" hint="Successful transactions" />
        <KpiCard label="STLM / Top Up" value={money(stlm, false)} numeric={stlm} format={(n) => money(n, false)} icon={<Repeat2 className="h-4 w-4" />} tone="info" hint="Net adjustment" />
        <KpiCard label="Net flow" value={money(dep - pay, false)} numeric={dep - pay} format={(n) => money(n, false)} icon={<Scale className="h-4 w-4" />} tone={dep - pay >= 0 ? "primary" : "warning"} hint="Deposit − Pay out" />
      </div>

      <div className="grid gap-6 xl:grid-cols-5">
        <section className="surface p-5 xl:col-span-2">
          <h2 className="text-sm font-semibold">Agent wallets — limit vs deposit</h2>
          <p className="mb-2 text-xs text-muted-foreground">How much of each wallet family's daily limit has been used</p>
          {chart.length ? (
            <MiniBar
              data={chart}
              xKey="wallet"
              series={[{ key: "Limit", label: "Limit", color: "#6366f1" }, { key: "Deposit", label: "Deposit", color: "#14b8a6" }]}
            />
          ) : (
            <div className="py-16 text-center text-sm text-muted-foreground">No chart data yet</div>
          )}
        </section>
        <section className="surface p-5 xl:col-span-2">
          <h2 className="text-sm font-semibold">Today's flow</h2>
          <p className="mb-2 text-xs text-muted-foreground">Deposit vs pay out vs settlement</p>
          {flowSlices.length ? <MiniDonut data={flowSlices} centerLabel="Total flow" /> : (
            <div className="py-16 text-center text-sm text-muted-foreground">No flow data yet</div>
          )}
        </section>
        <section className="surface p-5 xl:col-span-1">
          <h2 className="mb-3 text-sm font-semibold">Snapshot</h2>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between"><span className="text-muted-foreground">Deposit</span><span className="num font-medium text-success">{money(dep, false)}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Pay out</span><span className="num font-medium text-destructive">{money(pay, false)}</span></div>
            <div className="flex justify-between border-t pt-3"><span className="text-muted-foreground">Net flow</span><span className="num font-semibold">{money(dep - pay, false)}</span></div>
          </div>
        </section>
        <section className="surface p-5 xl:col-span-3">
          <h2 className="mb-3 text-sm font-semibold">Agent accounts — utilized limit</h2>
          <DataTable table={data.utilization.agent} dense emptyTitle="No agent limit data" />
        </section>
        <section className="surface p-5 xl:col-span-3">
          <h2 className="mb-3 text-sm font-semibold">Personal eBanking — utilized limit</h2>
          <DataTable table={data.utilization.personal_ebanking} dense emptyTitle="No eBanking data" />
        </section>
        <section className="surface p-5 xl:col-span-2">
          <h2 className="mb-3 text-sm font-semibold">Personal iBanking — utilized limit</h2>
          <DataTable table={data.utilization.personal_ibanking} dense emptyTitle="No iBanking data" />
        </section>
      </div>
    </div>
  );
}
