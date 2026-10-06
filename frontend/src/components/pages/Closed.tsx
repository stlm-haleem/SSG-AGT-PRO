import { useState } from "react";
import { Archive, Check, Pencil, Plus, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PageHeader } from "@/components/common/PageHeader";
import { DataTable } from "@/components/common/DataTable";
import { Pagination } from "@/components/common/Pagination";
import { SearchBox } from "@/components/common/SearchBox";
import { MultiSelect } from "@/components/common/MultiSelect";
import { ErrorNote, Spinner, TableSkeleton } from "@/components/common/States";
import { Confirm } from "@/components/common/Confirm";
import { useToast } from "@/components/common/Toast";
import { usePaged } from "@/hooks/usePaged";
import { useDebounced } from "@/hooks/useFetch";
import { apiSend } from "@/lib/api";

const STATUSES = ["Permanent Stop", "Closed"];
const EMPTY = { wallet_name: "", status: "Permanent Stop", remarks: "" };
const key = (row: Record<string, unknown>) => String(row["Wallet name"] ?? "");

export function Closed({ token, can }: { token: string; can: (k: string) => boolean }) {
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 300);
  const [wallet, setWallet] = useState<string[]>([]);
  const [acctType, setAcctType] = useState<string[]>([]);
  const [groupCode, setGroupCode] = useState<string[]>([]);
  const [method, setMethod] = useState<string[]>([]);
  const { data, loading, error, meta, setPage, setPerPage, reload } = usePaged<any>("/ssg/closed", token, {
    q: dq, wallet, acct_type: acctType, group_code: groupCode, method,
  });
  const toast = useToast();
  const canEdit = can("closed_edit");
  const canDelete = can("closed_delete");
  const [editing, setEditing] = useState<typeof EMPTY | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [batchOpen, setBatchOpen] = useState(false);
  const [batch, setBatch] = useState({ status: "", remarks: "" });
  const [confirmBatchDelete, setConfirmBatchDelete] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const options = data?.options ?? { wallet: [], acct_type: [], group_code: [], method: [] };

  const startNew = () => { setIsNew(true); setEditing({ ...EMPTY }); };
  const startEdit = (row: Record<string, unknown>) => {
    setIsNew(false);
    setEditing({ wallet_name: key(row), status: String(row["Status"] ?? "") || "Permanent Stop", remarks: String(row["Remarks"] ?? "") });
  };

  const save = async () => {
    if (!editing?.wallet_name.trim()) return;
    setSaving(true);
    try { const r = await apiSend<{ message: string }>("/ssg/closed", token, "PUT", editing); toast.success(r.message); setEditing(null); reload(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Save failed"); }
    finally { setSaving(false); }
  };

  const toggle = (k: string) => setSelected((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const toggleAll = (keys: string[], on: boolean) => setSelected((s) => { const n = new Set(s); keys.forEach((k) => (on ? n.add(k) : n.delete(k))); return n; });

  const saveBatch = async () => {
    setSaving(true);
    try {
      const r = await apiSend<{ message: string }>("/ssg/closed/batch-edit", token, "POST", { selected: [...selected], status: batch.status, remarks: batch.remarks });
      toast.success(r.message); setBatchOpen(false); setBatch({ status: "", remarks: "" }); setSelected(new Set()); reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Update failed"); }
    finally { setSaving(false); }
  };
  const doBatchDelete = async () => {
    try {
      const r = await apiSend<{ message: string }>("/ssg/closed/batch-delete", token, "POST", { selected: [...selected] });
      toast.success(r.message); setSelected(new Set()); reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Delete failed"); }
  };
  const doDelete = async (name: string) => {
    try {
      const r = await apiSend<{ message: string }>(`/ssg/closed/${encodeURIComponent(name)}`, token, "DELETE");
      toast.success(r.message); setSelected((s) => { const n = new Set(s); n.delete(name); return n; }); reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Delete failed"); }
  };

  const showSelect = canEdit || canDelete;
  const n = selected.size;

  return (
    <div className="space-y-5">
      <PageHeader icon={<Archive className="h-5 w-5" />} title="Permanently Closed Accounts"
        subtitle="Permanently stopped accounts — Wallet and Account type follow the Master List automatically"
        actions={<>
          {canEdit && <Button size="sm" onClick={startNew}><Plus className="h-3.5 w-3.5" /> Add account</Button>}
          {canEdit && <Button size="sm" variant="outline" disabled={n === 0} onClick={() => setBatchOpen(true)}><Pencil className="h-3.5 w-3.5" /> Edit selected{n > 0 && ` (${n})`}</Button>}
          {canDelete && <Button size="sm" variant="outline" disabled={n === 0} onClick={() => setConfirmBatchDelete(true)}><Trash2 className="h-3.5 w-3.5 text-destructive" /> Delete selected{n > 0 && ` (${n})`}</Button>}
          {n > 0 && <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}><X className="h-3.5 w-3.5" /> Clear selection</Button>}
        </>} />
      <div className="surface p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <SearchBox value={q} onChange={setQ} placeholder="Search wallet name / account…" className="max-w-xs" />
          <MultiSelect label="Wallet" options={options.wallet} value={wallet} onChange={setWallet} />
          <MultiSelect label="Account type" options={options.acct_type} value={acctType} onChange={setAcctType} />
          <MultiSelect label="Group code" options={options.group_code} value={groupCode} onChange={setGroupCode} />
          <MultiSelect label="Method" options={options.method} value={method} onChange={setMethod} />
        </div>
        {error && <ErrorNote message={error} />}
        {loading && !data ? <TableSkeleton cols={5} /> : (
          <>
            <DataTable table={data} pillColumns={["Status"]} emptyTitle="No permanently closed accounts"
              selection={showSelect ? { rowKey: key, selected, onToggle: toggle, onToggleAll: toggleAll } : undefined}
              actions={(canEdit || canDelete) ? (row) => (
                <div className="flex justify-end gap-1">
                  {canEdit && <Button size="icon" variant="ghost" title="Edit" onClick={() => startEdit(row)}><Pencil className="h-3.5 w-3.5" /></Button>}
                  {canDelete && <Button size="icon" variant="ghost" title="Delete" onClick={() => setConfirmDelete(key(row))}><Trash2 className="h-3.5 w-3.5 text-destructive" /></Button>}
                </div>
              ) : undefined}
              actionsLabel="Actions"
            />
            <Pagination meta={meta} onPage={setPage} onPerPage={setPerPage} />
          </>
        )}
      </div>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{isNew ? "Add" : "Edit"} permanently closed account</DialogTitle></DialogHeader>
          {editing && (
            <div className="grid gap-3">
              <div><Label className="text-xs">Wallet name</Label><Input className="mt-1" value={editing.wallet_name} disabled={!isNew} placeholder="e.g. ARMANI-NG-001" onChange={(e) => setEditing({ ...editing, wallet_name: e.target.value.toUpperCase() })} /></div>
              <div><Label className="text-xs">Status</Label>
                <select value={editing.status} onChange={(e) => setEditing({ ...editing, status: e.target.value })} className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm">
                  {STATUSES.map((s) => <option key={s}>{s}</option>)}
                </select>
              </div>
              <div><Label className="text-xs">Remarks</Label><Input className="mt-1" value={editing.remarks} placeholder="Optional remarks" onChange={(e) => setEditing({ ...editing, remarks: e.target.value })} /></div>
              <div className="rounded-lg border border-dashed bg-muted/40 p-3 text-xs text-muted-foreground"><b className="text-foreground">Automatic fields</b> — Wallet · Account type (from the Master List)</div>
            </div>
          )}
          <DialogFooter><Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button><Button disabled={saving || !editing?.wallet_name.trim()} onClick={save}>{saving ? <Spinner /> : <Check className="h-4 w-4" />} Save</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={batchOpen} onOpenChange={setBatchOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Edit {n} selected account{n === 1 ? "" : "s"}</DialogTitle></DialogHeader>
          <div className="grid gap-3">
            <div><Label className="text-xs">Status</Label>
              <select value={batch.status} onChange={(e) => setBatch({ ...batch, status: e.target.value })} className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm">
                <option value="">Leave existing</option>
                {STATUSES.map((s) => <option key={s}>{s}</option>)}
              </select>
            </div>
            <div><Label className="text-xs">Remarks</Label><Input className="mt-1" value={batch.remarks} placeholder="Leave blank to keep existing" onChange={(e) => setBatch({ ...batch, remarks: e.target.value })} /></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setBatchOpen(false)}>Cancel</Button><Button disabled={saving || (!batch.status && !batch.remarks.trim())} onClick={saveBatch}>{saving ? <Spinner /> : <Check className="h-4 w-4" />} Save changes</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Confirm open={confirmBatchDelete} title={`Delete ${n} selected account${n === 1 ? "" : "s"}?`} danger confirmLabel="Delete"
        description="This removes them from persistent storage and from Permanent Stop tagging." onConfirm={doBatchDelete} onClose={() => setConfirmBatchDelete(false)} />
      <Confirm open={!!confirmDelete} title={`Delete ${confirmDelete}?`} danger confirmLabel="Delete"
        description="Delete this permanently closed account?" onConfirm={() => confirmDelete && doDelete(confirmDelete)} onClose={() => setConfirmDelete(null)} />
    </div>
  );
}
