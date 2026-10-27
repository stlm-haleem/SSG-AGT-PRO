import { useState } from "react";
import { ArchiveX, Download, Trash2, Undo2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/common/PageHeader";
import { DataTable } from "@/components/common/DataTable";
import { Pagination } from "@/components/common/Pagination";
import { SearchBox } from "@/components/common/SearchBox";
import { MultiSelect } from "@/components/common/MultiSelect";
import { ErrorNote, TableSkeleton } from "@/components/common/States";
import { Confirm } from "@/components/common/Confirm";
import { useToast } from "@/components/common/Toast";
import { usePaged } from "@/hooks/usePaged";
import { useDebounced } from "@/hooks/useFetch";
import { apiDownload, apiSend, qs } from "@/lib/api";
import { stamp } from "@/lib/format";

/** Accounts deleted from the Pending Accounts tab (removed from the Master List). */
export function Deleted({ token, can }: { token: string; can: (k: string) => boolean }) {
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 300);
  const [wallet, setWallet] = useState<string[]>([]);
  const [acctType, setAcctType] = useState<string[]>([]);
  const [groupCode, setGroupCode] = useState<string[]>([]);
  const [method, setMethod] = useState<string[]>([]);
  const params = { q: dq, wallet, acct_type: acctType, group_code: groupCode, method };
  const { data, loading, error, meta, setPage, setPerPage, reload } = usePaged<any>("/ssg/deleted", token, params);
  const toast = useToast();
  const [exporting, setExporting] = useState(false);
  const canRestore = can("deleted_restore");
  const canRemove = can("deleted_delete");
  const [confirmRemove, setConfirmRemove] = useState<string[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirm, setConfirm] = useState<string[] | null>(null);
  const toggle = (k: string) => setSelected((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const toggleAll = (keys: string[], on: boolean) => setSelected((s) => { const n = new Set(s); keys.forEach((k) => (on ? n.add(k) : n.delete(k))); return n; });
  const remove = async (names: string[]) => {
    try {
      const r = await apiSend<{ message: string }>("/ssg/deleted/remove", token, "POST", { walletnames: names });
      toast.success(r.message);
      setSelected((s) => { const n = new Set(s); names.forEach((x) => n.delete(x)); return n; });
      reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Remove failed"); }
  };
  const restore = async (names: string[]) => {
    try {
      const r = await apiSend<{ message: string }>("/ssg/deleted/restore", token, "POST", { walletnames: names });
      toast.success(r.message);
      setSelected((s) => { const n = new Set(s); names.forEach((x) => n.delete(x)); return n; });
      reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Restore failed"); }
  };
  const options = data?.options ?? { wallet: [], acct_type: [], group_code: [], method: [] };

  // show the stored ISO stamp as "YYYY-MM-DD HH:MM:SS+hh:mm"
  const table = data ? { ...data, rows: (data.rows ?? []).map((r: Record<string, unknown>) => ({ ...r, "DELETED AT": stamp(String(r["DELETED AT"] ?? "")) })) } : data;

  const doExport = async () => {
    setExporting(true);
    try { await apiDownload(`/ssg/export/deleted${qs(params as any)}`, token, "deleted_accounts.xlsx"); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Export failed"); }
    finally { setExporting(false); }
  };

  return (
    <div className="space-y-5">
      <PageHeader icon={<ArchiveX className="h-5 w-5" />} title="Deleted Accounts"
        subtitle="Accounts deleted from Pending Accounts — they were removed from the Master List"
        actions={<>
          {canRestore && <Button size="sm" disabled={selected.size === 0} onClick={() => setConfirm([...selected])}><Undo2 className="h-3.5 w-3.5" /> Restore selected{selected.size > 0 && ` (${selected.size})`}</Button>}
          {canRemove && <Button size="sm" variant="outline" disabled={selected.size === 0} onClick={() => setConfirmRemove([...selected])}><Trash2 className="h-3.5 w-3.5 text-destructive" /> Remove selected{selected.size > 0 && ` (${selected.size})`}</Button>}
          {(canRestore || canRemove) && selected.size > 0 && <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}><X className="h-3.5 w-3.5" /> Clear selection</Button>}
          <Button variant="outline" size="sm" disabled={exporting} onClick={doExport}><Download className="h-3.5 w-3.5" /> Export</Button>
        </>} />
      <div className="surface p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <SearchBox value={q} onChange={setQ} placeholder="Search deleted accounts…" className="max-w-xs" />
          <MultiSelect label="Wallet" options={options.wallet} value={wallet} onChange={setWallet} />
          <MultiSelect label="Account type" options={options.acct_type} value={acctType} onChange={setAcctType} />
          <MultiSelect label="Group code" options={options.group_code} value={groupCode} onChange={setGroupCode} />
          <MultiSelect label="Method" options={options.method} value={method} onChange={setMethod} />
        </div>
        {error && <ErrorNote message={error} />}
        {loading && !data ? <TableSkeleton cols={8} /> : (
          <>
            <DataTable table={table} emptyTitle="No deleted accounts" emptyHint="Accounts you delete from the Pending Accounts tab appear here."
              selection={(canRestore || canRemove) ? { rowKey: (r) => String(r["WALLETNAME"] ?? ""), selected, onToggle: toggle, onToggleAll: toggleAll } : undefined}
              actions={(canRestore || canRemove) ? (row) => (
                <div className="flex justify-end gap-1.5">
                  {canRestore && <Button size="sm" variant="outline" onClick={() => setConfirm([String(row["WALLETNAME"])])}><Undo2 className="h-3.5 w-3.5" /> Restore</Button>}
                  {canRemove && <Button size="icon" variant="ghost" title="Remove from Deleted" onClick={() => setConfirmRemove([String(row["WALLETNAME"])])}><Trash2 className="h-3.5 w-3.5 text-destructive" /></Button>}
                </div>
              ) : undefined}
              actionsLabel="Actions" />
            <Pagination meta={meta} onPage={setPage} onPerPage={setPerPage} />
          </>
        )}
      </div>
      <Confirm open={!!confirm} title={`Restore ${confirm?.length ?? 0} account${confirm?.length === 1 ? "" : "s"}?`} confirmLabel="Restore"
        description="They go back into the Master List. Any that are still missing from the current imports will show in Pending Accounts again."
        onConfirm={() => confirm && restore(confirm)} onClose={() => setConfirm(null)} />
      <Confirm open={!!confirmRemove} danger title={`Remove ${confirmRemove?.length ?? 0} account${confirmRemove?.length === 1 ? "" : "s"} from Deleted?`} confirmLabel="Remove"
        description="They leave this list only — the Master List is not changed. Accounts stay here until you restore or remove them."
        onConfirm={() => confirmRemove && remove(confirmRemove)} onClose={() => setConfirmRemove(null)} />
    </div>
  );
}
