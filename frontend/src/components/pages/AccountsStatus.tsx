import { useState } from "react";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/common/PageHeader";
import { DataTable } from "@/components/common/DataTable";
import { Pagination } from "@/components/common/Pagination";
import { SearchBox } from "@/components/common/SearchBox";
import { LoadingBlock, ErrorNote, TableSkeleton } from "@/components/common/States";
import { useToast } from "@/components/common/Toast";
import { usePaged } from "@/hooks/usePaged";
import { useDebounced } from "@/hooks/useFetch";
import { apiDownload } from "@/lib/api";
import { BadgeCheck, Lock, ShieldAlert } from "lucide-react";

const ICONS = { active: BadgeCheck, locked: Lock, disabled: ShieldAlert } as const;

export function AccountsStatus({ token, slug }: { token: string; slug: "active" | "locked" | "disabled" }) {
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 300);
  const { data, loading, error, meta, page, setPage, perPage, setPerPage } = usePaged<any>(`/ssg/accounts-status/${slug}`, token, { q: dq });
  const toast = useToast();
  const [exporting, setExporting] = useState(false);
  const Icon = ICONS[slug];

  const doExport = async () => {
    setExporting(true);
    try { await apiDownload(`/ssg/export/accounts-status`, token, `${slug}_accounts.xlsx`); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Export failed"); }
    finally { setExporting(false); }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<Icon className="h-5 w-5" />}
        title={data?.heading ?? "Accounts"}
        subtitle="Generated from the most recent Limit + Active/Locked/Disabled imports"
        actions={<Button variant="outline" size="sm" disabled={exporting} onClick={doExport}><Download className="h-3.5 w-3.5" /> Export all</Button>}
      />
      <div className="surface p-4">
        <div className="mb-3"><SearchBox value={q} onChange={setQ} placeholder="Search…" className="max-w-xs" /></div>
        {error && <ErrorNote message={error} />}
        {loading && !data ? <TableSkeleton cols={5} /> : (
          <>
            <DataTable table={data} emptyTitle="No accounts" emptyHint="Import Active/Locked/Disabled Accounts and generate the summary." />
            <Pagination meta={meta} onPage={setPage} onPerPage={setPerPage} />
          </>
        )}
      </div>
    </div>
  );
}
