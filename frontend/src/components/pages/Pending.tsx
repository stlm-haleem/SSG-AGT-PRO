import { useState } from "react";
import { CheckCheck, Hourglass, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/common/PageHeader";
import { DataTable } from "@/components/common/DataTable";
import { Pagination } from "@/components/common/Pagination";
import { SearchBox } from "@/components/common/SearchBox";
import { MultiSelect } from "@/components/common/MultiSelect";
import { LoadingBlock, ErrorNote, TableSkeleton } from "@/components/common/States";
import { Confirm } from "@/components/common/Confirm";
import { useToast } from "@/components/common/Toast";
import { usePaged } from "@/hooks/usePaged";
import { useDebounced } from "@/hooks/useFetch";
import { apiSend } from "@/lib/api";

export function Pending({ token, can }: { token: string; can: (k: string) => boolean }) {
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 300);
  const [wallet, setWallet] = useState<string[]>([]);
  const { data, loading, error, meta, page, setPage, perPage, setPerPage, reload } = usePaged<any>("/ssg/pending", token, { q: dq, wallet });
  const toast = useToast();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false);
  const canEdit = can("pending_edit");
  const canDelete = can("pending_delete");
  const options = data?.options ?? { wallet: [] };

  const update = async (walletname: string) => {
    const wallet_ = drafts[walletname] ?? "";
    try {
      const r = await apiSend<{ message: string }>("/ssg/pending/update-wallet", token, "POST", { walletname, wallet: wallet_ });
      toast.success(r.message); reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Update failed"); }
  };
  const del = async (walletname: string) => {
    try {
      const r = await apiSend<{ message: string }>("/ssg/pending/delete", token, "POST", { walletname });
      toast.success(r.message); reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Delete failed"); }
  };
  const updateAll = async () => {
    try {
      const r = await apiSend<{ message: string }>("/ssg/pending/update-all", token, "POST", { q: dq, wallet });
      toast.success(r.message); reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Update failed"); }
  };
  const deleteAll = async () => {
    try {
      const r = await apiSend<{ message: string }>("/ssg/pending/delete-all", token, "POST", { q: dq, wallet });
      toast.success(r.message); reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Delete failed"); }
  };

  return (
    <div className="space-y-5">
      <PageHeader icon={<Hourglass className="h-5 w-5" />} title="Pending Accounts"
        subtitle="Masterlist accounts absent from every current import (Limit, Active, Locked, Disabled)"
        actions={canEdit ? <>
          <Button variant="outline" size="sm" onClick={updateAll}><CheckCheck className="h-3.5 w-3.5" /> Confirm all wallets</Button>
          {canDelete && <Button variant="outline" size="sm" onClick={() => setConfirmBulkDelete(true)}><Trash2 className="h-3.5 w-3.5 text-destructive" /> Delete all</Button>}
        </> : undefined}
      />
      <div className="surface p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <SearchBox value={q} onChange={setQ} placeholder="Search…" className="max-w-xs" />
          <MultiSelect label="Wallet" options={options.wallet} value={wallet} onChange={setWallet} />
        </div>
        {error && <ErrorNote message={error} />}
        {loading && !data ? <TableSkeleton cols={5} /> : (
          <>
            <DataTable
              table={data}
              emptyTitle="Nothing pending"
              emptyHint="Every Masterlist account is accounted for in the current imports."
              actions={(canEdit || canDelete) ? (row) => {
                const name = String(row["WALLETNAME"]);
                return (
                  <div className="flex items-center justify-end gap-1.5">
                    {canEdit && (
                      <>
                        <Input className="h-8 w-24 text-xs" placeholder={String(row["WALLET"] ?? "")}
                          value={drafts[name] ?? ""} onChange={(e) => setDrafts((d) => ({ ...d, [name]: e.target.value.toUpperCase() }))} />
                        <Button size="sm" variant="outline" onClick={() => update(name)}>Confirm</Button>
                      </>
                    )}
                    {canDelete && <Button size="icon" variant="ghost" onClick={() => del(name)}><Trash2 className="h-3.5 w-3.5 text-destructive" /></Button>}
                  </div>
                );
              } : undefined}
              actionsLabel="Resolve"
            />
            <Pagination meta={meta} onPage={setPage} onPerPage={setPerPage} />
          </>
        )}
      </div>
      <Confirm open={confirmBulkDelete} title="Delete all filtered pending accounts?" danger confirmLabel="Delete all"
        description="Removes them from the Masterlist and marks them Deleted." onConfirm={deleteAll} onClose={() => setConfirmBulkDelete(false)} />
    </div>
  );
}
