import { useRef, useState } from "react";
import { Database, FileSpreadsheet, RefreshCw, Send, Sparkles, Trash2, Upload, UploadCloud, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/common/PageHeader";
import { LoadingBlock, ErrorNote, Pill, Spinner } from "@/components/common/States";
import { Confirm } from "@/components/common/Confirm";
import { useToast } from "@/components/common/Toast";
import { useFetch } from "@/hooks/useFetch";
import { apiForm, apiSend, apiDownload } from "@/lib/api";
import { localIsoStamp } from "@/lib/format";

interface StatusResp {
  counts: Record<string, number>;
  extended_opening_active: boolean;
  extended_accounts: number;
  google_configured: boolean;
  telegram_configured: boolean;
  summary_generated: boolean;
}

const SLOTS: { field: string; label: string; dataset: string; hint: string; perm?: string; operational?: boolean }[] = [
  { field: "deposit_history", label: "Deposit History", dataset: "Deposit History", hint: "Merchant Deposit History export (.xlsx/.xls/.csv)" },
  { field: "pay_out_history", label: "Pay Out History", dataset: "Pay Out History", hint: "Merchant Pay Out History export" },
  { field: "account_statement", label: "Account Statement", dataset: "Account Statement", hint: "Wallet account statement export" },
  { field: "opening", label: "Opening", dataset: "Opening", hint: "Workbook with Morning Balance / Merchant Balance / Wallet Balances sheets" },
  { field: "limit_file", label: "Limit", dataset: "Limit", hint: "Agent-portal Limit export" },
  { field: "settlement_topup", label: "Settlement / Top Up", dataset: "Settlement / Top up", hint: "Workbook with Settlement + Top up sheets" },
  { field: "active_accounts", label: "Active Accounts", dataset: "Active Accounts", hint: "Active accounts export" },
  { field: "locked_accounts", label: "Locked Accounts", dataset: "Locked Accounts", hint: "Locked accounts export" },
  { field: "disabled_accounts", label: "Disabled Accounts", dataset: "Disabled Accounts", hint: "Disabled accounts export" },
  { field: "wallet_master", label: "Wallet Account Master List", dataset: "Wallet Account Master List", hint: "Persistent masterlist upload", perm: "imports_master" },
  { field: "permanently_closed", label: "Permanently Closed Accounts", dataset: "Permanently Closed Accounts", hint: "Permanently closed accounts sheet", perm: "imports_closed" },
];

const REPORTS: [string, string][] = [
  ["limit-utilization", "Limit Utilization"], ["cih-agent", "CIH Agent"], ["cih-personal", "CIH Personal"],
  ["limit-availability", "Limit Availability"], ["all", "Send All Reports"],
];

export function DataImport({ token, can, onGenerated }: { token: string; can: (k: string) => boolean; onGenerated?: (stamp: string) => void }) {
  const { data, loading, error, reload } = useFetch<StatusResp>("/ssg/status", token);
  const toast = useToast();
  const fileRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const [selected, setSelected] = useState<Record<string, File | null>>({});
  const [importing, setImporting] = useState(false);
  const [clearing, setClearing] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [sending, setSending] = useState("");
  const [extending, setExtending] = useState(false);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [confirmClear, setConfirmClear] = useState<string | null>(null);

  const pick = (field: string, f: File | null) => setSelected((s) => ({ ...s, [field]: f }));
  const anySelected = Object.values(selected).some(Boolean);

  const doImport = async () => {
    setImporting(true);
    try {
      const fd = new FormData();
      Object.entries(selected).forEach(([k, f]) => { if (f) fd.append(k, f); });
      const r = await apiForm<{ imported: string[]; errors: string[] }>("/ssg/import", token, fd);
      if (r.imported.length) toast.success(`Imported: ${r.imported.join(", ")}`);
      if (r.errors.length) toast.error(`Errors: ${r.errors.join(" | ")}`);
      setSelected({});
      Object.values(fileRefs.current).forEach((el) => { if (el) el.value = ""; });
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Import failed");
    } finally { setImporting(false); }
  };

  const doClear = async (dataset: string) => {
    setClearing(dataset);
    try {
      const r = await apiSend<{ message: string }>("/ssg/import/clear", token, "POST", { dataset });
      toast.success(r.message);
      reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Clear failed"); }
    finally { setClearing(null); }
  };

  const doGenerate = async () => {
    setGenerating(true);
    try {
      // the browser sends this PC's local time + UTC offset for the per-user "Last Generate" stamp
      const r = await apiSend<{ message: string; last_generate_at?: string }>("/ssg/import/generate", token, "POST", { from_date: fromDate, to_date: toDate, client_timestamp: localIsoStamp() });
      if (r.last_generate_at) onGenerated?.(r.last_generate_at);
      toast.success(r.message); reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Generate failed"); }
    finally { setGenerating(false); }
  };

  const doSyncGoogle = async () => {
    setSyncing(true);
    try {
      const r = await apiSend<{ message: string }>("/ssg/import/sync-google", token, "POST");
      toast.success(r.message); reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Sync failed"); }
    finally { setSyncing(false); }
  };

  const doSendReport = async (name: string) => {
    setSending(name);
    try {
      const r = await apiSend<{ message: string }>(`/ssg/telegram/send/${name}`, token, "POST");
      toast.success(r.message);
    } catch (e) { toast.error(e instanceof Error ? e.message : "Send failed"); }
    finally { setSending(""); }
  };

  const doExtend = async () => {
    setExtending(true);
    try {
      const r = await apiSend<{ message: string }>("/ssg/import/extend-opening", token, "POST");
      toast.success(r.message); reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Could not extend opening balance"); }
    finally { setExtending(false); }
  };

  const doRevert = async () => {
    setExtending(true);
    try {
      const r = await apiSend<{ message: string }>("/ssg/import/revert-opening", token, "POST");
      toast.success(r.message); reload();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Could not revert"); }
    finally { setExtending(false); }
  };

  if (loading && !data) return <LoadingBlock />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  // Operational files need "Import Data"; the Master List / Permanently Closed uploads have their own permissions.
  const visibleSlots = SLOTS.filter((s) => (s.perm ? can(s.perm) : can("imports_data")));
  const canData = can("imports_data");
  const canEditImports = can("imports_edit");
  const canClear = can("imports_delete");

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Database className="h-5 w-5" />}
        title="Data Import"
        subtitle="Upload today's files, then generate the summary. Operational data is in-memory only; the Masterlist persists."
        actions={
          <>
            {data.extended_opening_active && <Pill tone="warning">Extended Opening active — {data.extended_accounts.toLocaleString()} accounts</Pill>}
            {can("imports_google_sync") && (
              <Button variant="outline" size="sm" disabled={syncing || !data.google_configured} onClick={doSyncGoogle}
                title={data.google_configured ? undefined : "Configure Google Sheets under Admin → Integrations first"}>
                {syncing ? <Spinner /> : <RefreshCw className="h-3.5 w-3.5" />} Sync Google Sheets
              </Button>
            )}
          </>
        }
      />

      <section className="surface p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Current files</h2>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {Object.entries(data.counts).map(([k, v]) => (
              <span key={k} className="rounded-full bg-muted px-2 py-0.5">{k}: <b className="text-foreground">{v.toLocaleString()}</b></span>
            ))}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {visibleSlots.map((s) => {
            const rows = data.counts[s.dataset] ?? 0;
            const chosen = selected[s.field];
            return (
              <div key={s.field} className="rounded-xl border p-3.5">
                <div className="mb-1 flex items-center justify-between">
                  <div className="text-sm font-medium">{s.label}</div>
                  <span className="text-[11px] text-muted-foreground num">{rows.toLocaleString()} rows</span>
                </div>
                <p className="mb-2 text-[11px] text-muted-foreground">{s.hint}</p>
                <div className="flex items-center gap-2">
                  <input
                    ref={(el) => { fileRefs.current[s.field] = el; }}
                    type="file" accept=".csv,.xlsx,.xls"
                    onChange={(e) => pick(s.field, e.target.files?.[0] ?? null)}
                    className="block w-full text-xs file:mr-2 file:rounded-md file:border-0 file:bg-secondary file:px-2.5 file:py-1.5 file:text-xs file:font-medium hover:file:bg-secondary/80"
                  />
                  {canClear && rows > 0 && (s.dataset !== "Wallet Account Master List" && s.dataset !== "Permanently Closed Accounts") && (
                    <Button size="icon" variant="ghost" title="Clear" onClick={() => setConfirmClear(s.dataset)}>
                      {clearing === s.dataset ? <Spinner /> : <Trash2 className="h-4 w-4 text-destructive" />}
                    </Button>
                  )}
                </div>
                {chosen && <div className="mt-1.5 truncate text-[11px] text-primary">Selected: {chosen.name}</div>}
              </div>
            );
          })}
        </div>

        <div className="mt-4 flex justify-end">
          <Button disabled={!anySelected || importing || (canData && !canEditImports)} onClick={doImport}>
            {importing ? <Spinner /> : <UploadCloud className="h-4 w-4" />} Import &amp; Save All
          </Button>
        </div>
      </section>

      {canData && (
      <section className="surface flex flex-wrap items-end gap-3 p-5">
        <div>
          <h2 className="text-sm font-semibold">Generate summary</h2>
          <p className="text-xs text-muted-foreground">Recomputes Account Monitoring, CIH tables and unknown accounts from current data.</p>
        </div>
        <div className="ml-auto flex flex-wrap items-end gap-2">
          <label className="text-xs text-muted-foreground">From<Input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} className="mt-1 h-9 w-40" /></label>
          <label className="text-xs text-muted-foreground">To<Input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} className="mt-1 h-9 w-40" /></label>
          <Button disabled={generating || !canEditImports} onClick={doGenerate}>{generating ? <Spinner /> : <Sparkles className="h-4 w-4" />} Generate Summary</Button>
        </div>
      </section>
      )}

      {can("imports_telegram_reports") && (
        <section className="surface flex flex-wrap items-center gap-2 p-5">
          <Send className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">Telegram reports:</span>
          {REPORTS.map(([k, label]) => (
            <Button key={k} size="sm" variant={k === "all" ? "default" : "outline"} disabled={!!sending || !data.telegram_configured}
              title={data.telegram_configured ? undefined : "Configure Telegram under Admin → Integrations first"} onClick={() => doSendReport(k)}>
              {sending === k ? <Spinner /> : <Send className="h-3.5 w-3.5" />} {label}
            </Button>
          ))}
        </section>
      )}

      {canData && (
      <section className="surface flex flex-wrap items-center justify-between gap-3 p-5">
        <div>
          <h2 className="text-sm font-semibold">Extended Opening Balance</h2>
          <p className="max-w-xl text-xs text-muted-foreground">
            Uses each account's current Running Balance as tomorrow's Opening, without touching the imported Opening workbook. Revert restores the imported data.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" disabled={extending || !canEditImports} onClick={doExtend}><Sparkles className="h-4 w-4" /> Extend from R. BAL</Button>
          <Button variant="outline" disabled={extending || !canEditImports} onClick={doRevert}><RotateCcw className="h-4 w-4" /> Revert</Button>
        </div>
      </section>
      )}

      <TemplatesRow token={token} toast={toast} can={can} />

      <Confirm
        open={!!confirmClear}
        title={`Clear ${confirmClear}?`}
        description="This removes the current in-memory data for this dataset. The Wallet Masterlist is never affected."
        confirmLabel="Clear"
        danger
        onConfirm={() => confirmClear && doClear(confirmClear)}
        onClose={() => setConfirmClear(null)}
      />
    </div>
  );
}

function TemplatesRow({ token, toast, can }: { token: string; toast: ReturnType<typeof useToast>; can: (k: string) => boolean }) {
  const all: [string, string, string][] = [["master", "Master List", "imports_master"], ["opening", "Opening", "imports_data"], ["settlement-topup", "Settlement / Top Up", "imports_data"], ["closed", "Permanently Closed", "imports_closed"]];
  const tpls: [string, string][] = all.filter(([, , p]) => can(p)).map(([k, l]) => [k, l]);
  const [busy, setBusy] = useState("");
  const dl = async (key: string) => {
    setBusy(key);
    try { await apiDownload(`/ssg/template/${key}`, token, `${key}_template.xlsx`); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Download failed"); }
    finally { setBusy(""); }
  };
  if (!tpls.length) return null;
  return (
    <section className="surface flex flex-wrap items-center gap-2 p-5">
      <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />
      <span className="text-sm font-medium">Blank templates:</span>
      {tpls.map(([k, label]) => (
        <Button key={k} size="sm" variant="outline" disabled={busy === k} onClick={() => dl(k)}>
          {busy === k ? <Spinner /> : <Upload className="h-3.5 w-3.5" />} {label}
        </Button>
      ))}
    </section>
  );
}
