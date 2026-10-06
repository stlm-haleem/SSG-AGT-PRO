import { useState } from "react";
import { Plus, Trash2, UserCog } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PageHeader } from "@/components/common/PageHeader";
import { LoadingBlock, ErrorNote, Pill, Spinner } from "@/components/common/States";
import { Confirm } from "@/components/common/Confirm";
import { useToast } from "@/components/common/Toast";
import { useFetch } from "@/hooks/useFetch";
import { apiSend } from "@/lib/api";

interface UserRow { id: number; username: string; role: string; active: boolean }
interface RolesResp { roles: { name: string }[] }

export function UsersAdmin({ token, currentUsername }: { token: string; currentUsername: string }) {
  const { data, loading, error, reload } = useFetch<UserRow[]>("/users", token);
  const { data: rolesResp } = useFetch<RolesResp>("/roles", token);
  const toast = useToast();
  const roleNames = rolesResp?.roles.map((r) => r.name) ?? ["ADMIN"];
  const [creating, setCreating] = useState<{ username: string; password: string; role: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [pwFor, setPwFor] = useState<UserRow | null>(null);
  const [newPw, setNewPw] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<UserRow | null>(null);

  const create = async () => {
    if (!creating?.username.trim() || !creating?.password) return;
    setSaving(true);
    try { await apiSend("/users", token, "POST", creating); toast.success(`${creating.username} created.`); setCreating(null); reload(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Could not create user"); }
    finally { setSaving(false); }
  };
  const setRole = async (u: UserRow, role: string) => {
    try { await apiSend(`/users/${u.id}`, token, "PATCH", { role }); toast.success(`${u.username} is now ${role}.`); reload(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Could not update role"); }
  };
  const toggleActive = async (u: UserRow) => {
    try { await apiSend(`/users/${u.id}`, token, "PATCH", { active: !u.active }); reload(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Could not update"); }
  };
  const resetPassword = async () => {
    if (!pwFor || !newPw) return;
    try { await apiSend(`/users/${pwFor.id}`, token, "PATCH", { password: newPw }); toast.success("Password reset."); setPwFor(null); setNewPw(""); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Could not reset password"); }
  };
  const remove = async (u: UserRow) => {
    try { await apiSend(`/users/${u.id}`, token, "DELETE"); toast.success(`${u.username} deleted.`); reload(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Could not delete"); }
  };

  if (loading && !data) return <LoadingBlock />;
  if (error) return <ErrorNote message={error} />;

  return (
    <div className="space-y-5">
      <PageHeader icon={<UserCog className="h-5 w-5" />} title="Users" subtitle="Everyone who can sign in, and which role they hold"
        actions={<Button size="sm" onClick={() => setCreating({ username: "", password: "", role: roleNames.find((r) => r !== "ADMIN") ?? "ADMIN" })}><Plus className="h-3.5 w-3.5" /> Add user</Button>} />
      <div className="surface overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/70 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr><th className="px-4 py-2.5 text-left">Username</th><th className="px-4 py-2.5 text-left">Role</th><th className="px-4 py-2.5 text-left">Status</th><th className="px-4 py-2.5 text-right">Actions</th></tr>
          </thead>
          <tbody>
            {(data ?? []).map((u) => (
              <tr key={u.id} className="border-t hover:bg-accent/40">
                <td className="px-4 py-2.5 font-medium">{u.username}{u.username === currentUsername && <span className="ml-1.5 text-xs text-muted-foreground">(you)</span>}</td>
                <td className="px-4 py-2.5">
                  <select value={u.role} disabled={u.role === "ADMIN" && roleNames.filter((r) => r === "ADMIN").length <= 1}
                    onChange={(e) => setRole(u, e.target.value)} className="h-8 rounded-md border bg-background px-2 text-xs">
                    {roleNames.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
                <td className="px-4 py-2.5"><Pill tone={u.active ? "success" : "danger"}>{u.active ? "Active" : "Disabled"}</Pill></td>
                <td className="px-4 py-2.5">
                  <div className="flex justify-end gap-1.5">
                    <Button size="sm" variant="outline" onClick={() => setPwFor(u)}>Reset password</Button>
                    <Button size="sm" variant="outline" disabled={u.username === currentUsername} onClick={() => toggleActive(u)}>{u.active ? "Disable" : "Enable"}</Button>
                    <Button size="icon" variant="ghost" disabled={u.username === currentUsername} onClick={() => setConfirmDelete(u)}><Trash2 className="h-3.5 w-3.5 text-destructive" /></Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!creating} onOpenChange={(o) => !o && setCreating(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Add user</DialogTitle></DialogHeader>
          {creating && (
            <div className="space-y-3">
              <div><Label className="text-xs">Username</Label><Input className="mt-1" value={creating.username} onChange={(e) => setCreating({ ...creating, username: e.target.value })} /></div>
              <div><Label className="text-xs">Password</Label><Input type="password" className="mt-1" value={creating.password} onChange={(e) => setCreating({ ...creating, password: e.target.value })} /></div>
              <div><Label className="text-xs">Role</Label>
                <select value={creating.role} onChange={(e) => setCreating({ ...creating, role: e.target.value })} className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm">
                  {roleNames.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
            </div>
          )}
          <DialogFooter><Button variant="outline" onClick={() => setCreating(null)}>Cancel</Button><Button disabled={saving} onClick={create}>{saving && <Spinner />} Create</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!pwFor} onOpenChange={(o) => !o && setPwFor(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Reset password — {pwFor?.username}</DialogTitle></DialogHeader>
          <Input type="password" placeholder="New password" value={newPw} onChange={(e) => setNewPw(e.target.value)} />
          <DialogFooter><Button variant="outline" onClick={() => setPwFor(null)}>Cancel</Button><Button disabled={!newPw} onClick={resetPassword}>Reset</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Confirm open={!!confirmDelete} title={`Delete ${confirmDelete?.username}?`} danger confirmLabel="Delete"
        description="This permanently removes their account." onConfirm={() => confirmDelete && remove(confirmDelete)} onClose={() => setConfirmDelete(null)} />
    </div>
  );
}
