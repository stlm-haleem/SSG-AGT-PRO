import { useEffect, useState } from "react";
import { Bot, CheckCircle2, PlugZap, Plus, Radar, Send, Sheet, Star, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/common/PageHeader";
import { LoadingBlock, ErrorNote, Pill, Spinner } from "@/components/common/States";
import { useToast } from "@/components/common/Toast";
import { useFetch } from "@/hooks/useFetch";
import { apiForm, apiSend } from "@/lib/api";

interface Dest { id: string; name: string; chat_id: string; topic_id: string; chat_title: string; topic_title: string; enabled: boolean }
interface Config {
  google_spreadsheet_id: string; google_service_account: boolean; google_service_account_email: string;
  telegram_configured: boolean; telegram_chat_id: string; telegram_web_topic_id: string; telegram_web_destination_id: string;
  telegram_destinations: Dest[]; telegram_report_destination_ids?: string[]; telegram_listener_running: boolean; telegram_listener_error: string;
}
interface Detected { id: string; title: string; type: string; thread_id?: string }
interface Resp { config: Config; detected: Detected[] }

export function IntegrationsAdmin({ token }: { token: string }) {
  const { data, loading, error, reload } = useFetch<Resp>("/ssg/integrations", token);
  const toast = useToast();
  const [busy, setBusy] = useState("");
  const [spreadsheetId, setSpreadsheetId] = useState("");
  const [saFile, setSaFile] = useState<File | null>(null);
  const [botToken, setBotToken] = useState("");
  const [newDest, setNewDest] = useState({ name: "", chat_id: "", topic_id: "" });
  // Web-triggered reports can go to up to 3 selected active destinations (topic ID optional)
  const [reportIds, setReportIds] = useState<string[]>([]);
  const savedReportIds = data?.config.telegram_report_destination_ids;
  useEffect(() => { setReportIds(savedReportIds ?? []); }, [JSON.stringify(savedReportIds ?? [])]);
  const toggleReport = (id: string) => setReportIds((cur) => {
    if (cur.includes(id)) return cur.filter((x) => x !== id);
    if (cur.length >= 3) { toast.error("Select a maximum of 3 Telegram report destinations."); return cur; }
    return [...cur, id];
  });

  const useDetected = (c: Detected) => {
    setNewDest({ name: c.title, chat_id: c.id, topic_id: c.thread_id ?? "" });
    document.getElementById("dest-name")?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const run = async (key: string, fn: () => Promise<{ message: string }>) => {
    setBusy(key);
    try { const r = await fn(); toast.success(r.message); reload(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Action failed"); }
    finally { setBusy(""); }
  };

  if (loading && !data) return <LoadingBlock />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;
  const cfg = data.config;

  return (
    <div className="space-y-6">
      <PageHeader icon={<PlugZap className="h-5 w-5" />} title="Integrations" subtitle="Google Sheets sync and Telegram reporting for SSG AGT" />

      <section className="surface p-5">
        <div className="mb-3 flex items-center gap-2"><Sheet className="h-4 w-4 text-muted-foreground" /><h2 className="text-sm font-semibold">Google Sheets</h2>
          {cfg.google_service_account && <Pill tone="success">Configured</Pill>}
        </div>
        <p className="mb-3 text-xs text-muted-foreground">
          Share the spreadsheet with the service-account email as Editor, then Test the connection.
          {cfg.google_service_account_email && <> Current service account: <code className="rounded bg-muted px-1">{cfg.google_service_account_email}</code></>}
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div><Label className="text-xs">Spreadsheet ID</Label><Input className="mt-1" placeholder={cfg.google_spreadsheet_id || "1AbC…"} value={spreadsheetId} onChange={(e) => setSpreadsheetId(e.target.value)} /></div>
          <div><Label className="text-xs">Service account JSON</Label>
            <input type="file" accept=".json" onChange={(e) => setSaFile(e.target.files?.[0] ?? null)}
              className="mt-1 block w-full text-xs file:mr-2 file:rounded-md file:border-0 file:bg-secondary file:px-2.5 file:py-1.5 file:text-xs" />
          </div>
        </div>
        <div className="mt-3 flex gap-2">
          <Button size="sm" disabled={busy === "gsave"} onClick={() => run("gsave", async () => {
            const fd = new FormData(); fd.append("spreadsheet_id", spreadsheetId); if (saFile) fd.append("service_account", saFile);
            return apiForm("/ssg/integrations/google", token, fd);
          })}>{busy === "gsave" && <Spinner />} Save</Button>
          <Button size="sm" variant="outline" disabled={busy === "gtest"} onClick={() => run("gtest", () => apiSend("/ssg/integrations/google/test", token, "POST"))}>
            {busy === "gtest" && <Spinner />} Test connection
          </Button>
          <Button size="sm" variant="outline" disabled={busy === "gsync"} onClick={() => run("gsync", () => apiSend("/ssg/import/sync-google", token, "POST"))}>
            {busy === "gsync" && <Spinner />} Sync Active / Locked / Disabled now
          </Button>
        </div>
      </section>

      <section className="surface p-5">
        <div className="mb-3 flex items-center gap-2"><Bot className="h-4 w-4 text-muted-foreground" /><h2 className="text-sm font-semibold">Telegram</h2>
          {cfg.telegram_configured && <Pill tone="success">Configured</Pill>}
          {cfg.telegram_listener_running && <Pill tone="info">Listener running</Pill>}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div><Label className="text-xs">Bot token</Label><Input className="mt-1" type="password" placeholder="123456:AA…" value={botToken} onChange={(e) => setBotToken(e.target.value)} /></div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" disabled={busy === "tsave"} onClick={() => run("tsave", () => apiSend("/ssg/integrations/telegram", token, "POST", { bot_token: botToken }))}>
            {busy === "tsave" && <Spinner />} Save token
          </Button>
          <Button size="sm" variant="outline" disabled={busy === "ttest"} onClick={() => run("ttest", () => apiSend("/ssg/integrations/telegram/test", token, "POST"))}>
            {busy === "ttest" && <Spinner />} Test bot
          </Button>
          <Button size="sm" variant="outline" disabled={busy === "tdetect"} onClick={() => run("tdetect", () => apiSend("/ssg/integrations/telegram/detect", token, "POST"))}>
            {busy === "tdetect" && <Spinner />} <Radar className="h-3.5 w-3.5" /> Detect chats
          </Button>
          <Button size="sm" variant="outline" disabled={busy === "tcmd"} onClick={() => run("tcmd", () => apiSend("/ssg/integrations/telegram/install-commands", token, "POST"))}>
            {busy === "tcmd" && <Spinner />} Install commands
          </Button>
        </div>

        {data.detected.length > 0 && (
          <div className="mt-3 space-y-1.5">
            <p className="text-xs text-muted-foreground">Click a detected chat to fill in the destination fields below.</p>
            {data.detected.map((c, i) => (
              <button
                key={c.id + (c.thread_id ?? "") + i}
                onClick={() => useDetected(c)}
                className="flex w-full flex-wrap items-center gap-2 rounded-lg border bg-muted/40 p-2.5 text-left text-xs hover:bg-accent"
              >
                <span className="font-medium text-foreground">{c.title}</span>
                <Pill tone="neutral">{c.type}</Pill>
                <span className="text-muted-foreground">chat ID: {c.id}</span>
                {c.thread_id && <span className="text-muted-foreground">· topic ID: {c.thread_id}</span>}
                <span className="ml-auto text-primary">Use this</span>
              </button>
            ))}
          </div>
        )}

        <div className="mt-5 border-t pt-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Destinations</h3>
          <div className="space-y-2">
            {cfg.telegram_destinations.map((d) => (
              <div key={d.id} className="flex flex-wrap items-center gap-2 rounded-lg border p-2.5 text-sm">
                <span className="font-medium">{d.name || d.chat_title || d.chat_id}</span>
                <span className="text-xs text-muted-foreground">chat {d.chat_id}{d.topic_id ? ` · topic ${d.topic_id}` : ""}</span>
                {cfg.telegram_web_destination_id === d.id && <Pill tone="primary">Default</Pill>}
                <label className={"flex items-center gap-1.5 text-xs " + (d.enabled ? "cursor-pointer" : "opacity-50")}>
                  <input type="checkbox" className="h-3.5 w-3.5 accent-[hsl(var(--primary))]" disabled={!d.enabled}
                    checked={reportIds.includes(d.id)} onChange={() => toggleReport(d.id)} /> Send reports
                </label>
                <Pill tone={d.enabled ? "success" : "neutral"}>{d.enabled ? "Enabled" : "Disabled"}</Pill>
                <div className="ml-auto flex gap-1.5">
                  {cfg.telegram_web_destination_id !== d.id && (
                    <Button size="sm" variant="outline" onClick={() => run("web-" + d.id, () => apiSend(`/ssg/integrations/telegram/destinations/${d.id}/web`, token, "POST"))}>
                      <Star className="h-3.5 w-3.5" /> Make web
                    </Button>
                  )}
                  <Button size="icon" variant="ghost" onClick={() => run("del-" + d.id, () => apiSend(`/ssg/integrations/telegram/destinations/${d.id}`, token, "DELETE"))}>
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                  </Button>
                </div>
              </div>
            ))}
            {!cfg.telegram_destinations.length && <div className="text-xs text-muted-foreground">No destinations registered yet.</div>}
          </div>
          {cfg.telegram_destinations.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Button size="sm" disabled={busy === "rsel"} onClick={() => run("rsel", () => apiSend("/ssg/integrations/telegram/report-destinations", token, "POST", { destination_ids: reportIds }))}>
                {busy === "rsel" && <Spinner />} Save report destinations
              </Button>
              <span className="text-xs text-muted-foreground">Selected: {reportIds.length} / 3 — with none selected, reports go to the default destination.</span>
            </div>
          )}
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <div><Label htmlFor="dest-name" className="text-xs">Name</Label><Input id="dest-name" className="mt-1 h-9 w-32" value={newDest.name} onChange={(e) => setNewDest({ ...newDest, name: e.target.value })} /></div>
            <div><Label className="text-xs">Chat ID</Label><Input className="mt-1 h-9 w-36" value={newDest.chat_id} onChange={(e) => setNewDest({ ...newDest, chat_id: e.target.value })} /></div>
            <div>
              <Label className="text-xs">Topic ID</Label>
              <Input className="mt-1 h-9 w-28" placeholder="numeric, optional" value={newDest.topic_id}
                onChange={(e) => setNewDest({ ...newDest, topic_id: e.target.value })} />
              <p className="mt-1 w-28 text-[10px] leading-tight text-muted-foreground">Numeric thread ID only — leave blank unless targeting one forum topic.</p>
            </div>
            <Button size="sm" disabled={busy === "add" || !newDest.chat_id} onClick={() => run("add", async () => {
              const r = await apiSend<{ message: string }>("/ssg/integrations/telegram/destinations", token, "POST", newDest);
              setNewDest({ name: "", chat_id: "", topic_id: "" }); return r;
            })}>
              {busy === "add" && <Spinner />} <Plus className="h-3.5 w-3.5" /> Register
            </Button>
          </div>
        </div>

        <div className="mt-5 border-t pt-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Send a report now</h3>
          <div className="flex flex-wrap gap-2">
            {[["limit-utilization", "Limit utilization"], ["cih-agent", "CIH agent"], ["cih-personal", "CIH personal"], ["limit-availability", "Limit availability"], ["all", "Send all"]].map(([k, label]) => (
              <Button key={k} size="sm" variant={k === "all" ? "default" : "outline"} disabled={busy === "send-" + k}
                onClick={() => run("send-" + k, () => apiSend(`/ssg/telegram/send/${k}`, token, "POST"))}>
                {busy === "send-" + k ? <Spinner /> : <Send className="h-3.5 w-3.5" />} {label}
              </Button>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
