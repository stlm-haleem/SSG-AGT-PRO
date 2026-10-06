import { useState } from "react";
import { Download, FileSpreadsheet, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/common/PageHeader";
import { DataTable } from "@/components/common/DataTable";
import { Pagination } from "@/components/common/Pagination";
import { LoadingBlock, ErrorNote, TableSkeleton } from "@/components/common/States";
import { useToast } from "@/components/common/Toast";
import { usePaged } from "@/hooks/usePaged";
import { apiDownload } from "@/lib/api";
import { cn } from "@/lib/utils";

const TABS: [string, string][] = [["account", "Account Statement"], ["merchant-deposit", "Merchant Deposit"], ["merchant-payout", "Merchant Pay out"], ["deposit-type", "Deposit Type Summary"]];

export function Statements({ token }: { token: string }) {
  const [tab, setTab] = useState("account");
  const { data, loading, error, meta, page, setPage, perPage, setPerPage, reload } = usePaged<any>(`/ssg/statements/${tab}`, token, {});
  const toast = useToast();
  const [exporting, setExporting] = useState(false);

  const doExport = async () => {
    setExporting(true);
    try { await apiDownload(`/ssg/export/statement/${tab}`, token, `${tab}.xlsx`); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Export failed"); }
    finally { setExporting(false); }
  };

  return (
    <div className="space-y-5">
      <PageHeader icon={<FileSpreadsheet className="h-5 w-5" />} title="Generated Statements" subtitle="Output of the last Generate Summary run"
        actions={<>
          <Button variant="outline" size="sm" onClick={() => reload()}><RefreshCw className="h-3.5 w-3.5" /> Refresh</Button>
          <Button variant="outline" size="sm" disabled={exporting} onClick={doExport}><Download className="h-3.5 w-3.5" /> Export</Button>
        </>} />
      <div className="inline-flex rounded-xl border bg-muted/60 p-1">
        {TABS.map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)} className={cn("rounded-lg px-4 py-1.5 text-sm transition-all", tab === k ? "bg-card font-medium shadow-sm" : "text-muted-foreground hover:text-foreground")}>
            {label}
          </button>
        ))}
      </div>
      <div className="surface p-4">
        {error && <ErrorNote message={error} />}
        {loading && !data ? <TableSkeleton cols={6} /> : (
          <>
            <DataTable table={data} emptyTitle="Nothing generated yet" emptyHint="Go to Data → Data Import and click Generate Summary." />
            <Pagination meta={meta} onPage={setPage} onPerPage={setPerPage} />
          </>
        )}
      </div>
    </div>
  );
}
