import { useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/common/PageHeader";
import { DataTable } from "@/components/common/DataTable";
import { Pagination } from "@/components/common/Pagination";
import { ChipSearch, joinTerms } from "@/components/common/ChipSearch";
import { MultiSelect } from "@/components/common/MultiSelect";
import { LoadingBlock, ErrorNote, TableSkeleton } from "@/components/common/States";
import { useToast } from "@/components/common/Toast";
import { usePaged } from "@/hooks/usePaged";
import { useDebounced } from "@/hooks/useFetch";
import { apiDownload, qs } from "@/lib/api";
import { LineChart, AlertOctagon, ShieldAlert } from "lucide-react";

const ICONS: Record<string, typeof LineChart> = { agent: LineChart, personal: LineChart, "high-discrepancy": AlertOctagon, "limit-reached": ShieldAlert };

export function Overview({ token, slug }: { token: string; slug: "agent" | "personal" | "high-discrepancy" | "limit-reached" }) {
  // Enter-to-chip multi-account search (same behaviour as Account Monitoring)
  const [terms, setTerms] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const debouncedDraft = useDebounced(draft, 300);
  const q = joinTerms(terms, debouncedDraft);
  const [sortRbal, setSortRbal] = useState("");
  const [threshold, setThreshold] = useState("0");
  const debouncedThreshold = useDebounced(threshold, 400);
  const [status, setStatus] = useState<string[]>([]);
  const [category, setCategory] = useState("ALL");
  const [limitType, setLimitType] = useState("ALL");
  const toast = useToast();
  const [exporting, setExporting] = useState(false);

  const isHighDiscrepancy = slug === "high-discrepancy";
  const isLimitReached = slug === "limit-reached";
  const params: Record<string, any> = { q, sort_rbal: sortRbal };
  if (isHighDiscrepancy) { params.threshold = debouncedThreshold; params.category = category; params.status = status; }
  else if (isLimitReached) { params.limit_type = limitType; }
  else { params.threshold = debouncedThreshold; }

  const { data, loading, error, meta, page, setPage, perPage, setPerPage, reload } = usePaged<any>(`/ssg/overview/${slug}`, token, params);
  const Icon = ICONS[slug];
  const options = data?.options ?? { status: [] };

  const doExport = async () => {
    setExporting(true);
    try {
      await apiDownload(`/ssg/export/overview/${slug}${qs(params as any)}`, token, `overview_${slug}.xlsx`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    } finally { setExporting(false); }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<Icon className="h-5 w-5" />}
        title={data?.heading ?? "Account Overview"}
        subtitle={isHighDiscrepancy ? "Accounts whose discrepancy meets or exceeds a threshold" : isLimitReached
          ? "Personal accounts that reached their daily or monthly DP limit" : "Accounts filtered by remaining limit threshold"}
        actions={<>
          <Button variant="outline" size="sm" onClick={() => reload()}><RefreshCw className="h-3.5 w-3.5" /> Refresh</Button>
          <Button variant="outline" size="sm" disabled={exporting} onClick={doExport}><Download className="h-3.5 w-3.5" /> Export</Button>
        </>}
      />
      <div className="surface p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <ChipSearch terms={terms} onTermsChange={setTerms} draft={draft} onDraftChange={setDraft} placeholder="Search accounts — Enter adds a chip" className="max-w-md" />
          {!isLimitReached && (
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              Threshold
              <Input value={threshold} onChange={(e) => setThreshold(e.target.value)} placeholder="e.g. 25k" className="h-9 w-28" />
            </label>
          )}
          {isHighDiscrepancy && (
            <>
              <select value={category} onChange={(e) => setCategory(e.target.value)} className="h-9 rounded-lg border bg-background px-2 text-sm">
                {["ALL", "AGENT", "PERSONAL"].map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <MultiSelect label="Status" options={options.status} value={status} onChange={setStatus} />
            </>
          )}
          <select value={sortRbal} onChange={(e) => setSortRbal(e.target.value)} title="R. BAL sort" className="h-9 rounded-lg border bg-background px-2 text-sm">
            <option value="">R. BAL: Default</option>
            <option value="asc">R. BAL: Smallest → Largest</option>
            <option value="desc">R. BAL: Largest → Smallest</option>
          </select>
          {isLimitReached && (
            <select value={limitType} onChange={(e) => setLimitType(e.target.value)} className="h-9 rounded-lg border bg-background px-2 text-sm">
              <option value="ALL">Daily + Monthly</option>
              <option value="daily">Daily reach limit</option>
              <option value="monthly">Monthly reach limit</option>
            </select>
          )}
        </div>
        {error && <ErrorNote message={error} />}
        {loading && !data ? <TableSkeleton cols={7} /> : (
          <>
            <DataTable table={data} pillColumns={["STATUS", "LIMIT STATUS"]} emptyTitle="No accounts match" emptyHint={!isLimitReached ? "Try a lower threshold." : undefined} />
            <Pagination meta={meta} onPage={setPage} onPerPage={setPerPage} />
          </>
        )}
      </div>
    </div>
  );
}
