import { useEffect, useState } from "react";
import { ArrowDownToLine, ArrowUpFromLine, RefreshCw, Scale, Send, Repeat2, LayoutDashboard, Clock, PauseCircle, PlayCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MultiSelect } from "@/components/common/MultiSelect";
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

type TableKey = "agent_normal" | "ebanking_normal" | "ibanking_normal" | "agent_vip" | "ebanking_vip" | "ibanking_vip";
interface TableFilter { group_code: string[]; wallet: string[]; hours: string[] }
interface Win { start: string; end: string }
interface Resp {
  totals: Record<string, number>;
  utilization: Record<TableKey, Table>;
  titles: Record<TableKey, string>;
  options: Record<TableKey, TableFilter>;
  chart: { wallet: string; Limit: number; Deposit: number }[];
  view: {
    auto_enabled: boolean;
    windows: Record<string, Win>;
    now_bdt: string;
    open_hours: string[];
    closed_hours: string[];
    summary: string;
    tables: Record<TableKey, TableFilter>;
  };
  telegram_configured: boolean;
}

const NORMAL_KEYS: TableKey[] = ["agent_normal", "ebanking_normal", "ibanking_normal"];
const VIP_KEYS: TableKey[] = ["agent_vip", "ebanking_vip", "ibanking_vip"];
const SPANS = ["xl:col-span-3", "xl:col-span-3", "xl:col-span-2"];

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
  const [wins, setWins] = useState<Record<string, Win>>({});
  const canEditView = can("dashboard_generate");

  useEffect(() => { if (data) setWins(data.view.windows); }, [data]);

  const saveView = async (body: Record<string, unknown>, okMsg?: string) => {
    try {
      await apiSend("/ssg/dashboard/view", token, "POST", body);
      if (okMsg) toast.success(okMsg);
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save the view");
    }
  };
  const setFilter = (key: TableKey, field: keyof TableFilter, value: string[]) => {
    if (!data) return;
    saveView({ tables: { [key]: { ...data.view.tables[key], [field]: value } } });
  };

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
  const noData = dep === 0 && pay === 0 && data.utilization.agent_normal.rows.length <= 1;

  const chart = data.chart.map((r) => ({ wallet: r.wallet, Limit: Number(r.Limit ?? 0), Deposit: Number(r.Deposit ?? 0) }));
  const v = data.view;

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
      </div>

      <section className="surface space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <Clock className="h-4 w-4 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold">Working-hours auto filter <span className="font-normal text-muted-foreground">· {v.now_bdt}</span></div>
            <div className={v.auto_enabled ? "text-xs text-muted-foreground" : "text-xs font-medium text-warning"}>{v.summary}</div>
          </div>
          {canEditView && (
            <Button size="sm" variant={v.auto_enabled ? "outline" : "default"} onClick={() => saveView({ auto_enabled: !v.auto_enabled })}>
              {v.auto_enabled ? <><PauseCircle className="h-3.5 w-3.5" /> Stop auto filter</> : <><PlayCircle className="h-3.5 w-3.5" /> Resume auto filter</>}
            </Button>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-4 border-t pt-3 text-xs">
          {["14", "16"].map((h) => (
            <div key={h} className="flex items-center gap-2">
              <span className="w-14 font-medium">{h} Hours</span>
              <input type="time" disabled={!canEditView} value={wins[h]?.start ?? ""} onChange={(e) => setWins({ ...wins, [h]: { ...wins[h], start: e.target.value } })} className="h-8 rounded-md border border-input bg-background px-2" />
              <span>to</span>
              <input type="time" disabled={!canEditView} value={wins[h]?.end ?? ""} onChange={(e) => setWins({ ...wins, [h]: { ...wins[h], end: e.target.value } })} className="h-8 rounded-md border border-input bg-background px-2" />
            </div>
          ))}
          <span className="text-muted-foreground">Bangladesh time (BDT). 24-hour accounts always count.</span>
          {canEditView && <Button size="sm" variant="outline" onClick={() => saveView({ windows: wins }, "Working hours saved.")}>Save hours</Button>}
        </div>
      </section>

      {([["Normal accounts", NORMAL_KEYS], ["VIP accounts (DP set for VIP levels)", VIP_KEYS]] as [string, TableKey[]][]).map(([label, keys]) => (
        <section key={label} className="surface space-y-4 p-5">
          <h2 className="text-base font-semibold">{label}</h2>
          <div className="grid gap-6 xl:grid-cols-8">
            {keys.map((k, i) => (
              <div key={k} className={`${SPANS[i]} min-w-0`}>
                <h3 className="mb-2 text-sm font-semibold">{data.titles[k]}</h3>
                <div className="mb-3 flex flex-wrap gap-2">
                  <MultiSelect label="Hours" options={data.options[k].hours} value={v.tables[k].hours} onChange={(x) => canEditView && setFilter(k, "hours", x)} className="min-w-[110px]" />
                </div>
                <DataTable table={data.utilization[k]} dense emptyTitle="No limit data" />
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
