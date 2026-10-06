import { useState } from "react";
import { Check, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PageHeader } from "@/components/common/PageHeader";
import { LoadingBlock, ErrorNote, Pill, Spinner } from "@/components/common/States";
import { Confirm } from "@/components/common/Confirm";
import { useToast } from "@/components/common/Toast";
import { useFetch } from "@/hooks/useFetch";
import { apiSend } from "@/lib/api";
import { cn } from "@/lib/utils";

interface CatalogItem { key: string; label: string }
interface CatalogGroup { key: string; label: string; items: CatalogItem[] }
interface RoleRow { id: number; name: string; permissions: string[]; locked: boolean; users: number }
interface Resp { roles: RoleRow[]; catalog: CatalogGroup[] }

export function RolesAdmin({ token }: { token: string }) {
  const { data, loading, error, reload } = useFetch<Resp>("/roles", token);
  const toast = useToast();
  const [active, setActive] = useState<number | null>(null);
  const [draft, setDraft] = useState<Set<string>>(new Set());
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<RoleRow | null>(null);

  const roles = data?.roles ?? [];
  const role = roles.find((r) => r.id === active) ?? roles[0] ?? null;

  const openRole = (r: RoleRow) => { setActive(r.id); setDraft(new Set(r.permissions)); setDirty(false); };
  if (role && active === null) openRole(role);

  const toggle = (key: string) => {
    if (role?.locked) return;
    setDraft((d) => { const n = new Set(d); n.has(key) ? n.delete(key) : n.add(key); return n; });
    setDirty(true);
  };
  const toggleGroup = (items: CatalogItem[], on: boolean) => {
    setDraft((d) => { const n = new Set(d); items.forEach((i) => (on ? n.add(i.key) : n.delete(i.key))); return n; });
    setDirty(true);
  };

  const save = async () => {
    if (!role) return;
    setSaving(true);
    try {
      await apiSend(`/roles/${role.id}`, token, "PATCH", { permissions: Array.from(draft) });
      toast.success(`${role.name} permissions updated.`);
      setDirty(false); reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Save failed"); }
    finally { setSaving(false); }
  };

  const createRole = async () => {
    if (!newName.trim()) return;
    try {
      await apiSend("/roles", token, "POST", { name: newName.trim(), permissions: [] });
      toast.success(`${newName} created.`); setCreating(false); setNewName(""); reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Could not create role"); }
  };
  const deleteRole = async (r: RoleRow) => {
    try { await apiSend(`/roles/${r.id}`, token, "DELETE"); toast.success(`${r.name} deleted.`); setActive(null); reload(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Could not delete role — reassign its users first."); }
  };

  if (loading && !data) return <LoadingBlock />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  return (
    <div className="space-y-5">
      <PageHeader icon={<ShieldCheck className="h-5 w-5" />} title="Roles & Permissions" subtitle="Fine-grained page and action access, same model across Wallet Monitor and SSG AGT"
        actions={<Button size="sm" onClick={() => setCreating(true)}><Plus className="h-3.5 w-3.5" /> New role</Button>} />

      <div className="grid gap-5 lg:grid-cols-[220px_1fr]">
        <div className="surface space-y-1 p-2">
          {roles.map((r) => (
            <button key={r.id} onClick={() => openRole(r)}
              className={cn("flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm", role?.id === r.id ? "bg-primary/10 font-medium text-primary" : "hover:bg-accent")}>
              <span>{r.name}</span>
              <span className="text-[11px] text-muted-foreground">{r.users}</span>
            </button>
          ))}
        </div>

        {role && (
          <div className="surface p-5">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold">{role.name}</h2>
                <p className="text-xs text-muted-foreground">{role.locked ? "Always has full access — can't be edited." : `${role.users} user(s) · ${draft.size} permission(s) granted`}</p>
              </div>
              <div className="flex gap-2">
                {!role.locked && role.users === 0 && (
                  <Button variant="outline" size="sm" onClick={() => setConfirmDelete(role)}><Trash2 className="h-3.5 w-3.5 text-destructive" /> Delete role</Button>
                )}
                {!role.locked && <Button size="sm" disabled={!dirty || saving} onClick={save}>{saving && <Spinner />} Save changes</Button>}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {data.catalog.map((g) => {
                const allOn = g.items.every((i) => draft.has(i.key));
                return (
                  <div key={g.key} className="rounded-xl border p-3.5">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{g.label}</span>
                      {!role.locked && (
                        <button className="text-[11px] text-primary hover:underline" onClick={() => toggleGroup(g.items, !allOn)}>
                          {allOn ? "Clear" : "All"}
                        </button>
                      )}
                    </div>
                    <div className="space-y-1.5">
                      {g.items.map((it) => {
                        const on = role.locked || draft.has(it.key);
                        return (
                          <label key={it.key} className={cn("flex items-center gap-2 rounded-md px-1.5 py-1 text-sm", !role.locked && "cursor-pointer hover:bg-accent/60")}>
                            <span onClick={() => toggle(it.key)} className={cn("flex h-4 w-4 shrink-0 items-center justify-center rounded border", on ? "border-primary bg-primary text-primary-foreground" : "border-input")}>
                              {on && <Check className="h-3 w-3" />}
                            </span>
                            {it.label}
                          </label>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>New role</DialogTitle></DialogHeader>
          <Input placeholder="Role name" value={newName} onChange={(e) => setNewName(e.target.value)} />
          <DialogFooter><Button variant="outline" onClick={() => setCreating(false)}>Cancel</Button><Button disabled={!newName.trim()} onClick={createRole}>Create</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Confirm open={!!confirmDelete} title={`Delete role ${confirmDelete?.name}?`} danger confirmLabel="Delete"
        onConfirm={() => confirmDelete && deleteRole(confirmDelete)} onClose={() => setConfirmDelete(null)} />
    </div>
  );
}
