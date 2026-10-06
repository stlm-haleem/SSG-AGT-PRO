import { useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/common/PageHeader";
import { KpiCard } from "@/components/common/KpiCard";
import { DataTable } from "@/components/common/DataTable";
import { Pagination } from "@/components/common/Pagination";
import { ChipSearch, joinTerms } from "@/components/common/ChipSearch";
import { MultiSelect } from "@/components/common/MultiSelect";
import { LoadingBlock, ErrorNote, TableSkeleton } from "@/components/common/States";
import { useToast } from "@/components/common/Toast";
import { usePaged } from "@/hooks/usePaged";
import { useDebounced } from "@/hooks/useFetch";
import { apiDownload, qs } from "@/lib/api";
import { money, count } from "@/lib/format";
import { Building2, Users, Gem, Activity, Ban } from "lucide-react";

type Slug = "agent" | "personal" | "vip" | "withdrawal" | "permanent-stop";
const ICONS: Record<string, typeof Building2> = { agent: Building2, personal: Users, vip: Gem, withdrawal: Activity, "permanent-stop": Ban };
const TITLES: Record<string, string> = { agent: "Agent Accounts", personal: "Personal Accounts", vip: "VIP Accounts", withdrawal: "Withdrawal Only Accounts", "permanent-stop": "Permanent Stop Accounts" };

interface Kpis { accounts: number; opening: number; deposit: number; withdrawal: number; r_bal: number; a_bal: number; discrep: number }

export function Monitoring({ token, slug }: { token: string; slug: Slug }) {
  // Enter-to-chip multi-account search: committed chips + the text still being typed (OR matching)
  const [terms, setTerms] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const debouncedDraft = useDebounced(draft, 300);
  const q = joinTerms(terms, debouncedDraft);
  const [status, setStatus] = useState<string[]>([]);
  const [code, setCode] = useState<string[]>([]);
  const [wallet, setWallet] = useState<string[]>([]);
  const [limitStatus, setLimitStatus] = useState<string[]>([]);
  const [whrs, setWhrs] = useState<string[]>([]);
  const [sortRbal, setSortRbal] = useState("");
  const toast = useToast();
  const [exporting, setExporting] = useState(false);

  const params = { q, status, code, wallet, limit_status: limitStatus, whrs, sort_rbal: sortRbal };
  const { data, loading, error, meta, page, setPage, perPage, setPerPage, reload } = usePaged<any>(`/ssg/monitoring/${slug}`, token, params);

  const Icon = ICONS[slug];
  const kpis: Kpis | undefined = data?.kpis;
  const options = data?.options ?? { status: [], code: [], wallet: [], limit_status: [], whrs: [] };

  const doExport = async () => {
    setExporting(true);
    try {
      // the export honours every active filter, search chip and the R. BAL sort
      await apiDownload(`/ssg/export/monitoring/${slug}${qs(params as any)}`, token, `monitoring_${slug}.xlsx`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<Icon className="h-5 w-5" />}
        title={TITLES[slug]}
        subtitle={slug === "permanent-stop"
          ? "Permanently stopped accounts from the Permanently Closed list — their Agent / Personal / VIP / Withdrawal classification is unchanged"
          : "Real-time account monitoring — Opening, Deposit, Withdrawal, Running & Actual balance"}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => reload()}><RefreshCw className="h-3.5 w-3.5" /> Refresh</Button>
            <Button variant="outline" size="sm" disabled={exporting} onClick={doExport}><Download className="h-3.5 w-3.5" /> Export</Button>
          </>
        }
      />

      {kpis && (
        <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
          <KpiCard label="Accounts" value={count(kpis.accounts)} numeric={kpis.accounts} format={count} tone="neutral" />
          <KpiCard label="Opening" value={money(kpis.opening, false)} numeric={kpis.opening} format={(n) => money(n, false)} tone="info" />
          <KpiCard label="Deposit" value={money(kpis.deposit, false)} numeric={kpis.deposit} format={(n) => money(n, false)} tone="success" />
          <KpiCard label="Withdrawal" value={money(kpis.withdrawal, false)} numeric={kpis.withdrawal} format={(n) => money(n, false)} tone="danger" />
          <KpiCard label="R. Balance" value={money(kpis.r_bal, false)} numeric={kpis.r_bal} format={(n) => money(n, false)} tone="primary" />
          <KpiCard label="Discrepancy" value={money(kpis.discrep, false)} numeric={kpis.discrep} format={(n) => money(n, false)} tone={kpis.discrep < 0 ? "danger" : "warning"} />
        </div>
      )}

      <div className="surface p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <ChipSearch terms={terms} onTermsChange={setTerms} draft={draft} onDraftChange={setDraft} placeholder="Search accounts — Enter adds a chip" className="max-w-md" />
          <MultiSelect label="Status" options={options.status} value={status} onChange={setStatus} />
          <MultiSelect label="Group code" options={options.code} value={code} onChange={setCode} />
          <MultiSelect label="Wallet" options={options.wallet} value={wallet} onChange={setWallet} />
          <MultiSelect label="Limit status" options={options.limit_status} value={limitStatus} onChange={setLimitStatus} />
          <MultiSelect label="W. HRS" options={options.whrs} value={whrs} onChange={setWhrs} />
          <select value={sortRbal} onChange={(e) => setSortRbal(e.target.value)} title="R. BAL sort" className="h-9 rounded-lg border bg-background px-2 text-sm">
            <option value="">R. BAL: Default (A–Z)</option>
            <option value="asc">R. BAL: Smallest → Largest</option>
            <option value="desc">R. BAL: Largest → Smallest</option>
          </select>
        </div>
        {error && <ErrorNote message={error} />}
        {loading && !data ? <TableSkeleton cols={7} /> : (
          <>
            <DataTable table={data} pillColumns={["STATUS", "LIMIT STATUS"]} emptyTitle="No accounts match these filters" />
            <Pagination meta={meta} onPage={setPage} onPerPage={setPerPage} />
          </>
        )}
      </div>
    </div>
  );
}
