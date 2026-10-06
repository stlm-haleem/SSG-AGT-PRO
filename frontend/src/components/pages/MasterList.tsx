import { useState } from "react";
import { Download, Pencil, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PageHeader } from "@/components/common/PageHeader";
import { DataTable } from "@/components/common/DataTable";
import { Pagination } from "@/components/common/Pagination";
import { SearchBox } from "@/components/common/SearchBox";
import { MultiSelect } from "@/components/common/MultiSelect";
import { LoadingBlock, ErrorNote, Spinner, TableSkeleton } from "@/components/common/States";
import { Confirm } from "@/components/common/Confirm";
import { useToast } from "@/components/common/Toast";
import { usePaged } from "@/hooks/usePaged";
import { useDebounced } from "@/hooks/useFetch";
import { apiDownload, apiSend, qs } from "@/lib/api";
import { TableProperties } from "lucide-react";

// Only the wallet name, Hours and Method are manual. MRC DP limit, SDP paid, wallet, group code and
// account type are filled in automatically from the current imports (supervisor's Master List rules).
const EMPTY = { WALLETNAME: "", HOURS: "", METHOD: "" };

export function MasterList({ token, can }: { token: string; can: (k: string) => boolean }) {
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 300);
  const [wallet, setWallet] = useState<string[]>([]);
  const [acctType, setAcctType] = useState<string[]>([]);
  const [groupCode, setGroupCode] = useState<string[]>([]);
  const [method, setMethod] = useState<string[]>([]);
  const params = { q: dq, wallet, acct_type: acctType, group_code: groupCode, method };
  const { data, loading, error, meta, page, setPage, perPage, setPerPage, reload } = usePaged<any>("/ssg/master", token, params);
  const toast = useToast();
  const [exporting, setExporting] = useState(false);
  const [editing, setEditing] = useState<typeof EMPTY | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const options = data?.options ?? { wallet: [], acct_type: [], group_code: [], method: [] };

  const canEdit = can("master_edit");
  const canDelete = can("master_delete");

  const startNew = () => { setIsNew(true); setEditing({ ...EMPTY }); };
  const startEdit = (row: Record<string, unknown>) => setEditing({
    WALLETNAME: String(row["WALLETNAME"] ?? ""), HOURS: String(row["HOURS"] ?? ""), METHOD: String(row["METHOD"] ?? ""),
  });
  const [isNew, setIsNew] = useState(false);

  const save = async () => {
    if (!editing?.WALLETNAME.trim()) return;
    setSaving(true);
    try {
      const r = await apiSend<{ message: string }>("/ssg/master", token, "PUT", editing);
      toast.success(r.message); setEditing(null); reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Save failed"); }
    finally { setSaving(false); }
  };

  const doDelete = async (name: string) => {
    try {
      const r = await apiSend<{ message: string }>(`/ssg/master/${encodeURIComponent(name)}`, token, "DELETE");
      toast.success(r.message); reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Delete failed"); }
  };

  const doExport = async () => {
    setExporting(true);
    try { await apiDownload(`/ssg/export/master${qs(params as any)}`, token, "wallet_account_master.xlsx"); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Export failed"); }
    finally { setExporting(false); }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<TableProperties className="h-5 w-5" />}
        title="Wallet Masterlist"
        subtitle="Persistent account directory — wallet, group code, hours, method and SDP per account"
        actions={<>
          <Button variant="outline" size="sm" disabled={exporting} onClick={doExport}><Download className="h-3.5 w-3.5" /> Export</Button>
          {canEdit && <Button size="sm" onClick={startNew}><Plus className="h-3.5 w-3.5" /> Add wallet</Button>}
        </>}
      />
      <div className="surface p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <SearchBox value={q} onChange={setQ} placeholder="Search wallet name…" className="max-w-xs" />
          <MultiSelect label="Wallet" options={options.wallet} value={wallet} onChange={setWallet} />
          <MultiSelect label="Account type" options={options.acct_type} value={acctType} onChange={setAcctType} />
          <MultiSelect label="Group code" options={options.group_code} value={groupCode} onChange={setGroupCode} />
          <MultiSelect label="Method" options={options.method} value={method} onChange={setMethod} />
        </div>
        {error && <ErrorNote message={error} />}
        {loading && !data ? <TableSkeleton cols={8} /> : (
          <>
            <DataTable
              table={data}
              emptyTitle="Masterlist is empty"
              emptyHint="Import a Wallet Account Master List file, or add accounts manually."
              actions={canEdit || canDelete ? (row) => (
                <div className="flex justify-end gap-1">
                  {canEdit && <Button size="icon" variant="ghost" onClick={() => { setIsNew(false); startEdit(row); }}><Pencil className="h-3.5 w-3.5" /></Button>}
                  {canDelete && <Button size="icon" variant="ghost" onClick={() => setConfirmDelete(String(row["WALLETNAME"]))}><Trash2 className="h-3.5 w-3.5 text-destructive" /></Button>}
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
          <DialogHeader><DialogTitle>{isNew ? "Add wallet" : "Edit wallet"}</DialogTitle></DialogHeader>
          {editing && (
            <div className="grid grid-cols-2 gap-3">
              <Field label="Wallet name" value={editing.WALLETNAME} onChange={(v) => setEditing({ ...editing, WALLETNAME: v.toUpperCase() })} full disabled={!isNew} />
              <Field label="Hours" value={editing.HOURS} onChange={(v) => setEditing({ ...editing, HOURS: v })} />
              <Field label="Method" value={editing.METHOD} onChange={(v) => setEditing({ ...editing, METHOD: v })} />
              <div className="col-span-2 rounded-lg border border-dashed bg-muted/40 p-3 text-xs text-muted-foreground">
                <b className="text-foreground">Automatic fields</b> — MRC DP limit, SDP paid, wallet, group code and account type are filled in from the current imports.
                Group code can also set Method (IBANKING / EBANKING) and Hours (14 / 16 / 18 / 24 Hours, 24H-0s Interval); when no rule applies, the Hours / Method you enter here are kept.
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button disabled={saving || !editing?.WALLETNAME.trim()} onClick={save}>{saving && <Spinner />} Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Confirm open={!!confirmDelete} title={`Delete ${confirmDelete}?`} description="This removes it from the persistent Wallet Masterlist." danger
        confirmLabel="Delete" onConfirm={() => confirmDelete && doDelete(confirmDelete)} onClose={() => setConfirmDelete(null)} />
    </div>
  );
}

function Field({ label, value, onChange, full, disabled }: { label: string; value: string; onChange: (v: string) => void; full?: boolean; disabled?: boolean }) {
  return (
    <div className={full ? "col-span-2" : undefined}>
      <Label className="text-xs">{label}</Label>
      <Input className="mt-1" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
