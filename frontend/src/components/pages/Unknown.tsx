import { useState } from "react";
import { HelpCircle, Plus, CheckCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/common/PageHeader";
import { DataTable } from "@/components/common/DataTable";
import { Pagination } from "@/components/common/Pagination";
import { SearchBox } from "@/components/common/SearchBox";
import { LoadingBlock, ErrorNote, TableSkeleton } from "@/components/common/States";
import { useToast } from "@/components/common/Toast";
import { usePaged } from "@/hooks/usePaged";
import { useDebounced } from "@/hooks/useFetch";
import { apiSend } from "@/lib/api";

export function Unknown({ token, can }: { token: string; can: (k: string) => boolean }) {
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 300);
  const { data, loading, error, meta, page, setPage, perPage, setPerPage, reload } = usePaged<any>("/ssg/unknown", token, { q: dq });
  const toast = useToast();
  const canEdit = can("unknown_edit");

  const add = async (wallet: string) => {
    try { const r = await apiSend<{ message: string }>("/ssg/unknown/update", token, "POST", { wallet }); toast.success(r.message); reload(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
  };
  const addAll = async () => {
    try { const r = await apiSend<{ message: string }>("/ssg/unknown/update-all", token, "POST"); toast.success(r.message); reload(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
  };

  return (
    <div className="space-y-5">
      <PageHeader icon={<HelpCircle className="h-5 w-5" />} title="Unknown Accounts"
        subtitle="Wallet accounts seen in Deposit/Pay Out History that aren't in the Masterlist yet"
        actions={canEdit ? <Button variant="outline" size="sm" onClick={addAll}><CheckCheck className="h-3.5 w-3.5" /> Add all to Masterlist</Button> : undefined}
      />
      <div className="surface p-4">
        <div className="mb-3"><SearchBox value={q} onChange={setQ} placeholder="Search…" className="max-w-xs" /></div>
        {error && <ErrorNote message={error} />}
        {loading && !data ? <TableSkeleton cols={4} /> : (
          <>
            <DataTable table={data} emptyTitle="No unknown accounts" emptyHint="Every deposit/payout account is already on the Masterlist."
              actions={canEdit ? (row) => (
                <Button size="sm" variant="outline" onClick={() => add(String(row["Wallet Account"]))}><Plus className="h-3.5 w-3.5" /> Add</Button>
              ) : undefined}
              actionsLabel="Action"
            />
            <Pagination meta={meta} onPage={setPage} onPerPage={setPerPage} />
          </>
        )}
      </div>
    </div>
  );
}
