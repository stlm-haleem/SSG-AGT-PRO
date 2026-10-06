from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
import threading
import time
import uuid
from datetime import datetime

import numpy as np
import pandas as pd
import requests
from PIL import Image, ImageDraw, ImageFont

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except Exception:
    service_account = None
    build = None


class IntegrationManager:
    """Google Sheets + Telegram integrations for SSG AGT.

    Secrets are stored locally under data/integrations.json and are never exposed
    in the HTML UI. Operational datasets remain in-memory/current-session data;
    the Wallet Masterlist continues to persist separately through AppData.
    """

    def __init__(self, data_dir: Path, logic, data):
        self.data_dir = Path(data_dir)
        self.logic = logic
        self.data = data
        self.integrations_dir = self.data_dir / "integrations"
        self.integrations_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.data_dir / "integrations.json"
        self._listener_thread = None
        self._listener_running = False
        self._listener_stop = threading.Event()
        self._tg_offset = None
        self._seen_topics = {}
        self._last_listener_error = ""
        if not self.config_path.exists():
            self._save_config(self._default())

    def _default(self):
        return {"google": {"spreadsheet_id": "", "service_account_file": ""},
                "telegram": {
                    "bot_token": "",
                    "chat_id": "",
                    "web_topic_id": "",
                    "web_destination_id": "",
                    "report_destination_ids": [],
                    "destinations": []
                }}

    def _load_config(self):
        try:
            raw=json.loads(self.config_path.read_text(encoding="utf-8"))
            cfg=self._default()
            cfg["google"].update(raw.get("google",{}))
            cfg["telegram"].update(raw.get("telegram",{}))
            tg=cfg["telegram"]
            # Backward compatibility: migrate the former single chat/topic pair
            # into the persistent destination list the first time it is loaded.
            dests=tg.get("destinations")
            if not isinstance(dests, list):
                dests=[]
            if not dests and str(tg.get("chat_id","")).strip():
                dests=[{
                    "id": uuid.uuid4().hex,
                    "name": "Legacy Web Report Topic",
                    "chat_id": str(tg.get("chat_id","")).strip(),
                    "topic_id": str(tg.get("web_topic_id","")).strip(),
                    "chat_title": "",
                    "topic_title": "",
                    "enabled": True,
                }]
                tg["destinations"]=dests
                tg["web_destination_id"]=dests[0]["id"]
                self._save_config(cfg)
            # Remove malformed duplicate ids and ensure fields exist.
            seen=set(); clean=[]
            for d in dests:
                if not isinstance(d, dict): continue
                did=str(d.get("id") or uuid.uuid4().hex)
                if did in seen: continue
                seen.add(did)
                clean.append({
                    "id": did,
                    "name": str(d.get("name") or "Telegram Destination"),
                    "chat_id": str(d.get("chat_id") or "").strip(),
                    "topic_id": str(d.get("topic_id") or "").strip(),
                    "chat_title": str(d.get("chat_title") or ""),
                    "topic_title": str(d.get("topic_title") or ""),
                    "enabled": bool(d.get("enabled", True)),
                })
            tg["destinations"]=clean
            if tg.get("web_destination_id") and not any(d["id"]==tg["web_destination_id"] and d["enabled"] for d in clean):
                tg["web_destination_id"]=clean[0]["id"] if clean else ""
            if not tg.get("web_destination_id") and clean:
                tg["web_destination_id"]=clean[0]["id"]
            # Up to 3 active destinations can receive web-triggered reports.
            selected=[str(x) for x in tg.get("report_destination_ids",[]) if str(x)] if isinstance(tg.get("report_destination_ids",[]), list) else []
            valid_ids={d["id"] for d in clean if d.get("enabled",True)}
            tg["report_destination_ids"]=[x for x in selected if x in valid_ids][:3]
            return cfg
        except Exception:
            return self._default()

    def _save_config(self, cfg):
        self.config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    def config(self):
        cfg = self._load_config()
        google = cfg.get("google", {})
        tg = cfg.get("telegram", {})
        destinations=list(tg.get("destinations", []))
        return {
            "google_spreadsheet_id": google.get("spreadsheet_id", ""),
            "google_service_account": bool(google.get("service_account_file")),
            "google_service_account_email": self._service_account_email(),
            "telegram_configured": bool(tg.get("bot_token") and destinations),
            "telegram_chat_id": tg.get("chat_id", ""),
            "telegram_web_topic_id": tg.get("web_topic_id", ""),
            "telegram_web_destination_id": tg.get("web_destination_id", ""),
            "telegram_destinations": destinations,
            "telegram_report_destination_ids": list(tg.get("report_destination_ids", [])),
            "telegram_listener_running": self._listener_running,
            "telegram_listener_error": self._last_listener_error,
        }

    def google_configured(self):
        cfg=self._load_config().get("google", {})
        return bool(cfg.get("spreadsheet_id") and cfg.get("service_account_file") and Path(cfg["service_account_file"]).exists())

    def telegram_configured(self):
        cfg=self._load_config().get("telegram", {})
        return bool(cfg.get("bot_token") and cfg.get("destinations"))

    async def save_google_config(self, spreadsheet_id: str, service_account_upload):
        cfg=self._load_config()
        cfg["google"]["spreadsheet_id"]=spreadsheet_id
        if service_account_upload is not None and service_account_upload.filename:
            if Path(service_account_upload.filename).suffix.lower() != ".json":
                raise ValueError("Service account credential must be a .json file.")
            target=self.integrations_dir / "google_service_account.json"
            raw=await service_account_upload.read()
            data=json.loads(raw.decode("utf-8"))
            if data.get("type") != "service_account" or not data.get("client_email"):
                raise ValueError("The uploaded JSON does not look like a Google service-account credential.")
            target.write_bytes(raw)
            cfg["google"]["service_account_file"]=str(target)
        self._save_config(cfg)

    def _google_service(self):
        if service_account is None or build is None:
            raise RuntimeError("Google Sheets packages are not installed yet. Restart the server after package installation.")
        cfg=self._load_config().get("google", {})
        path=Path(cfg.get("service_account_file", ""))
        sid=cfg.get("spreadsheet_id", "")
        if not sid or not path.exists():
            raise RuntimeError("Google Sheets is not configured. Add the Spreadsheet ID and service-account JSON first.")
        creds=service_account.Credentials.from_service_account_file(
            str(path), scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return build("sheets", "v4", credentials=creds, cache_discovery=False)

    def _service_account_email(self):
        cfg=self._load_config().get("google", {})
        path=Path(cfg.get("service_account_file", ""))
        if not path.exists(): return ""
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("client_email", "")
        except Exception:
            return ""

    def test_google_connection(self):
        svc=self._google_service()
        sid=self._load_config()["google"]["spreadsheet_id"]
        return svc.spreadsheets().get(spreadsheetId=sid, fields="properties.title").execute()["properties"]["title"]

    def sync_current_account_statuses(self):
        """Sync the SAME generated Active/Locked/Disabled account tables shown in SSG AGT.

        The Google Sheet is not a raw-data mirror. Each tab receives the transformed
        output produced by BusinessLogic.generate_locked_disabled_result(), then is
        split by the generated Status value. This keeps Google Sheets consistent with
        the Active Accounts / Locked Accounts / Disabled Accounts pages in the web app.
        """
        svc=self._google_service()
        sid=self._load_config()["google"]["spreadsheet_id"]
        spreadsheet=svc.spreadsheets().get(spreadsheetId=sid, fields="sheets.properties").execute()
        existing={s["properties"]["title"]:s["properties"]["sheetId"] for s in spreadsheet.get("sheets",[])}
        titles=["Active","Locked","Disabled"]
        missing=[t for t in titles if t not in existing]
        if missing:
            requests_body={"requests":[{"addSheet":{"properties":{"title":t}}} for t in missing]}
            svc.spreadsheets().batchUpdate(spreadsheetId=sid, body=requests_body).execute()
            spreadsheet=svc.spreadsheets().get(spreadsheetId=sid, fields="sheets.properties").execute()
            existing={s["properties"]["title"]:s["properties"]["sheetId"] for s in spreadsheet.get("sheets",[])}

        # Build each tab from its corresponding generated dataset/page. This avoids
        # relying on the source Status cell text (e.g. "Disable" vs "Disabled")
        # and guarantees Google Sheets matches the three web pages exactly.
        dataset_map={
            "Active":"Active Accounts",
            "Locked":"Locked Accounts",
            "Disabled":"Disabled Accounts",
        }
        counts={}
        for tab,dataset_name in dataset_map.items():
            generated=self.logic.generate_locked_disabled_result()
            if generated is None or generated.empty:
                df=pd.DataFrame(columns=["Account Name","Bank Code","Account Number","Stop Date","Status","Remarks"])
            else:
                source_df=self.logic.data.dataframes.get(dataset_name)
                # Regenerate a small dataset-specific view from the same source rows.
                df=generated[generated["Status"].astype(str).str.strip().str.casefold().eq(tab.casefold())].copy()

            # Preserve the exact column order shown by the generated status pages.
            expected=["Account Name","Bank Code","Account Number","Stop Date","Status","Remarks"]
            for col in expected:
                if col not in df.columns:
                    df[col]=""
            df=df[expected].copy()

            values=[list(df.columns)] + [
                ["" if pd.isna(v) else str(v) for v in row]
                for row in df.itertuples(index=False, name=None)
            ]

            svc.spreadsheets().values().clear(
                spreadsheetId=sid, range=f"'{tab}'!A:ZZZ", body={}
            ).execute()
            svc.spreadsheets().values().update(
                spreadsheetId=sid, range=f"'{tab}'!A1",
                valueInputOption="RAW", body={"values":values}
            ).execute()

            # Freeze the generated header and auto-resize the useful columns.
            requests=[{
                "updateSheetProperties":{
                    "properties":{"sheetId":existing[tab],"gridProperties":{"frozenRowCount":1}},
                    "fields":"gridProperties.frozenRowCount"
                }
            }]
            for col_idx in range(len(expected)):
                requests.append({
                    "autoResizeDimensions":{
                        "dimensions":{"sheetId":existing[tab],"dimension":"COLUMNS","startIndex":col_idx,"endIndex":col_idx+1}
                    }
                })
            svc.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests":requests}).execute()
            counts[tab]=len(df)
        return counts

    # ---------------- Telegram ----------------
    def _tg_cfg(self):
        return self._load_config().get("telegram", {})

    def _tg(self, method, data=None, files=None):
        token=self._tg_cfg().get("bot_token", "").strip()
        if not token:
            raise RuntimeError("Telegram bot token is not configured.")
        url=f"https://api.telegram.org/bot{token}/{method}"
        r=requests.post(url, data=data or {}, files=files, timeout=30)
        try: obj=r.json()
        except Exception: raise RuntimeError(f"Telegram returned HTTP {r.status_code}.")
        if not obj.get("ok"):
            raise RuntimeError(obj.get("description", "Telegram API error."))
        return obj

    def telegram_test(self):
        return self._tg("getMe").get("result",{}).get("username","")

    def telegram_delete_webhook(self):
        self._tg("deleteWebhook", {"drop_pending_updates":"false"})
        self._tg_offset = None

    def save_telegram_config(self, bot_token: str, chat_id: str = "", web_topic_id: str = ""):
        cfg=self._load_config()
        tg=cfg["telegram"]
        tg["bot_token"]=bot_token
        web_topic_id=self._validate_topic_id(web_topic_id)
        # Preserve/migrate legacy values when supplied from an older form.
        if chat_id.strip() and not tg.get("destinations"):
            did=uuid.uuid4().hex
            tg["destinations"]=[{"id":did,"name":"Legacy Web Report Topic","chat_id":chat_id.strip(),"topic_id":web_topic_id,"chat_title":"","topic_title":"","enabled":True}]
            tg["web_destination_id"]=did
        elif tg.get("destinations") and not tg.get("web_destination_id"):
            tg["web_destination_id"]=tg["destinations"][0]["id"]
        tg["chat_id"]=chat_id.strip()
        tg["web_topic_id"]=web_topic_id.strip()
        self._save_config(cfg)
        self._tg_offset = None
        if bot_token.strip():
            try:self.telegram_delete_webhook()
            except Exception:pass
            try:self.telegram_set_commands()
            except Exception:pass
            if not (self._listener_thread and self._listener_thread.is_alive()):
                self.start_telegram_listener()

    def telegram_destinations(self):
        return list(self._load_config().get("telegram",{}).get("destinations",[]))

    @staticmethod
    def _validate_topic_id(topic_id: str) -> str:
        """Topic ID must be the numeric thread ID of a forum topic, or blank.
        Rejects non-numeric values early with a clear message instead of
        letting a bad value reach send_report(), which needs int(topic_id)."""
        topic_id = str(topic_id or "").strip()
        if topic_id and not topic_id.lstrip("-").isdigit():
            raise ValueError(
                f"Topic ID must be the numeric thread ID of a forum topic, or left blank — got '{topic_id}'. "
                "Use Detect chats and pick a topic row, rather than typing the chat type (e.g. 'supergroup')."
            )
        return topic_id

    def add_telegram_destination(self, name: str, chat_id: str, topic_id: str = "", chat_title: str = "", topic_title: str = ""):
        chat_id=str(chat_id or "").strip()
        topic_id=self._validate_topic_id(topic_id)
        if not chat_id: raise ValueError("Chat ID is required.")
        cfg=self._load_config(); tg=cfg["telegram"]
        dests=tg.setdefault("destinations",[])
        for d in dests:
            if str(d.get("chat_id",""))==chat_id and str(d.get("topic_id",""))==topic_id:
                raise ValueError("This Chat ID + Topic ID is already registered.")
        did=uuid.uuid4().hex
        dest={"id":did,"name":str(name or "Telegram Destination").strip(),"chat_id":chat_id,"topic_id":topic_id,"chat_title":str(chat_title or "").strip(),"topic_title":str(topic_title or "").strip(),"enabled":True}
        dests.append(dest)
        if not tg.get("web_destination_id"): tg["web_destination_id"]=did
        tg["chat_id"]=chat_id; tg["web_topic_id"]=topic_id
        self._save_config(cfg)
        return dest

    def update_telegram_destination(self, destination_id: str, name: str, chat_id: str, topic_id: str = "", chat_title: str = "", topic_title: str = "", enabled: bool = True):
        cfg=self._load_config(); tg=cfg["telegram"]
        for d in tg.get("destinations",[]):
            if d.get("id")==destination_id:
                chat_id=str(chat_id or "").strip(); topic_id=self._validate_topic_id(topic_id)
                if not chat_id: raise ValueError("Chat ID is required.")
                d.update({"name":str(name or "Telegram Destination").strip(),"chat_id":chat_id,"topic_id":topic_id,"chat_title":str(chat_title or "").strip(),"topic_title":str(topic_title or "").strip(),"enabled":bool(enabled)})
                self._save_config(cfg); return d
        raise ValueError("Telegram destination was not found.")

    def delete_telegram_destination(self, destination_id: str):
        cfg=self._load_config(); tg=cfg["telegram"]
        dests=tg.get("destinations",[])
        remaining=[d for d in dests if d.get("id")!=destination_id]
        if len(remaining)==len(dests): raise ValueError("Telegram destination was not found.")
        tg["destinations"]=remaining
        tg["report_destination_ids"]=[x for x in tg.get("report_destination_ids",[]) if x != destination_id]
        if tg.get("web_destination_id")==destination_id:
            tg["web_destination_id"]=remaining[0]["id"] if remaining else ""
        self._save_config(cfg)

    def set_web_telegram_destination(self, destination_id: str):
        cfg=self._load_config(); tg=cfg["telegram"]
        if not any(d.get("id")==destination_id and d.get("enabled",True) for d in tg.get("destinations",[])):
            raise ValueError("Select an active Telegram destination.")
        tg["web_destination_id"]=destination_id
        self._save_config(cfg)

    def set_report_telegram_destinations(self, destination_ids):
        cfg=self._load_config(); tg=cfg["telegram"]
        requested=[]
        for did in destination_ids or []:
            did=str(did).strip()
            if did and did not in requested:
                requested.append(did)
        if len(requested)>3:
            raise ValueError("Select a maximum of 3 Telegram report destinations.")
        active={str(d.get("id")):d for d in tg.get("destinations",[]) if d.get("enabled",True)}
        invalid=[did for did in requested if did not in active]
        if invalid:
            raise ValueError("One or more selected Telegram destinations are not active.")
        tg["report_destination_ids"]=requested
        self._save_config(cfg)
        return requested

    def _web_telegram_destination(self):
        tg=self._load_config().get("telegram",{})
        did=tg.get("web_destination_id")
        for d in tg.get("destinations",[]):
            if d.get("id")==did and d.get("enabled",True): return d
        for d in tg.get("destinations",[]):
            if d.get("enabled",True): return d
        return None

    def _registered_chat_ids(self):
        tg=self._load_config().get("telegram",{})
        ids={str(d.get("chat_id")).strip() for d in tg.get("destinations",[]) if str(d.get("chat_id")).strip() and d.get("enabled",True)}
        if not ids and str(tg.get("chat_id","")).strip(): ids.add(str(tg.get("chat_id")).strip())
        return ids

    def _parse_int(value):
        try:
            return int(str(value).strip())
        except Exception:
            return None

    def telegram_set_commands(self):
        commands=[
            {"command":"help","description":"Show SSG AGT commands"},
            {"command":"agent","description":"CIH Agent Wallet Balances"},
            {"command":"personal","description":"CIH Personal Wallet Balances"},
            {"command":"limit","description":"CIH Limit Availability"},
            {"command":"utilization","description":"Dashboard Limit Utilization"},
            {"command":"all","description":"Send all SSG AGT reports"},
        ]
        self._tg("setMyCommands", {"commands":json.dumps(commands)})
        return True

    def _record_update_context(self, message):
        chat=message.get("chat") or {}
        cid=chat.get("id")
        if cid is None: return
        cid=str(cid)
        title=chat.get("title") or chat.get("username") or chat.get("first_name") or cid
        entry=self._seen_topics.setdefault(cid, {"id":cid,"title":title,"type":chat.get("type","") ,"topics":{}})
        thread=message.get("message_thread_id")
        # General/root messages may omit message_thread_id.
        if thread is not None:
            topic_title=f"Topic {thread}"
            ft=message.get("forum_topic_created") or message.get("forum_topic_edited")
            if isinstance(ft,dict) and ft.get("name"):
                topic_title=ft["name"]
            entry["topics"][str(thread)]={"id":str(thread),"title":topic_title}

    def telegram_detect_chats(self):
        # The background listener consumes getUpdates, so the UI reads the listener's
        # in-memory cache instead of competing for Telegram's update queue.
        result=[]
        for chat in self._seen_topics.values():
            base={"id":chat["id"],"title":chat["title"],"type":chat["type"]}
            result.append(base)
            for topic in chat["topics"].values():
                result.append({"id":chat["id"],"title":f'{chat["title"]} — {topic["title"]}',"type":f'{chat["type"]} / topic','thread_id':topic["id"]})
        return result

    def _listener_get_updates(self):
        data={"limit":100,"timeout":20}
        if self._tg_offset is not None:
            data["offset"]=self._tg_offset
        return self._tg("getUpdates", data)

    def _telegram_help(self, chat_id, thread_id=None):
        text=("SSG AGT commands:\n"
              "/agent — CIH Agent Wallet Balances\n"
              "/personal — CIH Personal Wallet Balances\n"
              "/limit — CIH Limit Availability\n"
              "/utilization — Dashboard Limit Utilization\n"
              "/all — all four reports")
        self._tg("sendMessage", {"chat_id":chat_id, **({"message_thread_id":thread_id} if thread_id is not None else {}), "text":text})

    def _telegram_command_report(self, command):
        return {
            "/agent":"cih-agent",
            "/personal":"cih-personal",
            "/limit":"limit-availability",
            "/utilization":"limit-utilization",
        }.get(command)

    def _handle_telegram_message(self, message):
        self._record_update_context(message)
        text=str(message.get("text") or "").strip()
        if not text.startswith("/"):
            return
        first=text.split()[0].strip()
        command=first.split("@",1)[0].lower()
        if command not in {"/help","/agent","/personal","/limit","/utilization","/all"}:
            return
        incoming_chat=str((message.get("chat") or {}).get("id","")).strip()
        # Commands are accepted from any topic of any registered Telegram chat.
        # The exact topic is taken from the incoming message_thread_id and the reply
        # is sent back to that same topic.
        if incoming_chat not in self._registered_chat_ids():
            return
        thread_id=message.get("message_thread_id")
        if command=="/help":
            try:self._telegram_help(incoming_chat, thread_id)
            except Exception: pass
            return
        names=[self._telegram_command_report(command)] if command not in {"/all"} else ["limit-utilization","cih-agent","cih-personal","limit-availability"]
        for name in names:
            try:
                self.send_report(name, chat_id=incoming_chat, thread_id=thread_id)
            except Exception as exc:
                try:
                    self._tg("sendMessage", {"chat_id":incoming_chat, **({"message_thread_id":thread_id} if thread_id is not None else {}), "text":f"SSG AGT report failed: {exc}"})
                except Exception: pass

    def _listener_loop(self):
        self._listener_running=True
        try:
            self._last_listener_error=""
            # Wait briefly after startup; app may still be initializing datasets.
            time.sleep(0.5)
            while not self._listener_stop.is_set():
                cfg=self._tg_cfg()
                token=str(cfg.get("bot_token","")).strip()
                if not token:
                    self._tg_offset=None
                    time.sleep(2)
                    continue
                try:
                    # Do not discard updates when starting/resetting the listener.
                    # Priming the queue here could consume a freshly sent command
                    # before the handler sees it, especially after saving Telegram settings.
                    data={"limit":100,"timeout":20,"allowed_updates":json.dumps(["message","my_chat_member"])}
                    if self._tg_offset is not None:data["offset"]=self._tg_offset
                    obj=self._tg("getUpdates", data)
                    for update in obj.get("result",[]):
                        uid=update.get("update_id")
                        if uid is not None:self._tg_offset=int(uid)+1
                        message=update.get("message")
                        if message: self._handle_telegram_message(message)
                    self._last_listener_error=""
                except Exception as exc:
                    self._last_listener_error=str(exc)
                    # A webhook prevents getUpdates. Try removing it automatically so
                    # command polling can recover without requiring a manual button click.
                    if "webhook" in self._last_listener_error.lower() or "conflict" in self._last_listener_error.lower():
                        try:
                            self._tg("deleteWebhook", {"drop_pending_updates":"false"})
                            self._tg_offset = None
                        except Exception:
                            pass
                    time.sleep(5)
        finally:
            self._listener_running=False

    def start_telegram_listener(self):
        if self._listener_thread and self._listener_thread.is_alive(): return
        self._listener_stop.clear()
        self._listener_thread=threading.Thread(target=self._listener_loop, name="SSG-Telegram-Listener", daemon=True)
        self._listener_thread.start()

    def telegram_listener_status(self):
        return {"running":self._listener_running,"error":self._last_listener_error}

    # ---------------- Report snapshots ----------------
    def _font(self, size=18, bold=False):
        paths=[
            Path(r"C:\Windows\Fonts\segoeui.ttf" if not bold else r"C:\Windows\Fonts\segoeuib.ttf"),
            Path(r"C:\Windows\Fonts\arial.ttf" if not bold else r"C:\Windows\Fonts\arialbd.ttf"),
            # Linux fallbacks (same bundled fonts as the OS, no new dependency) in case the
            # server isn't Windows — keeps report images and their — / £ / € glyphs correct.
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        ]
        for p in paths:
            try:
                if p.exists(): return ImageFont.truetype(str(p), size)
            except Exception: pass
        return ImageFont.load_default()

    def _report_df(self, report_name):
        if report_name == "limit-utilization":
            d=self.logic.dashboard_limit_utilization(); return {
                "AGENT ACCOUNTS - UTILIZED LIMIT":d["agent"],
                "PERSONAL EBANKING - UTILIZED LIMIT":d["personal_ebanking"],
                "PERSONAL IBANKING - UTILIZED LIMIT":d["personal_ibanking"],
            }
        if report_name == "cih-agent":
            df=self.logic._cih_wallet_table(False).copy()
            counts_balance=self.logic._cih_count_table(False,False).copy()
            counts_wd=self.logic._cih_count_table(False,True).copy()
            wallets=["BKASH","NAGAD","ROCKET","UPAY"]
            df=df[df["Wallet Name"].isin(wallets)].copy()
            cards=df[["Wallet Name","System Balance"]].copy()
            if not df.empty: df_total=self.logic._cih_total_row(df,"Wallet Name"); df=pd.concat([df,df_total],ignore_index=True)
            if not counts_balance.empty: counts_balance=pd.concat([counts_balance,self.logic._cih_total_row(counts_balance,"Wallets")],ignore_index=True)
            if not counts_wd.empty: counts_wd=pd.concat([counts_wd,self.logic._cih_total_row(counts_wd,"Wallets")],ignore_index=True)
            return {
                "CURRENT AGENT WALLET BALANCES":cards,
                "AGENT WALLET BALANCES":df,
                "COUNTS OF AGENT WALLET BALANCES WITH":counts_balance,
                "COUNTS OF AGENT OPEN IN WITHDRAWAL WITH":counts_wd,
            }
        if report_name == "cih-personal":
            df=self.logic._cih_wallet_table(True).copy()
            counts_balance=self.logic._cih_count_table(True,False).copy()
            counts_wd=self.logic._cih_count_table(True,True).copy()
            wallets=["BKASHC","NAGADC","ROCKETC","UPAYC"]
            df=df[df["Wallet Name"].isin(wallets)].copy()
            cards=df[["Wallet Name","System Balance"]].copy()
            if not df.empty: df_total=self.logic._cih_total_row(df,"Wallet Name"); df=pd.concat([df,df_total],ignore_index=True)
            if not counts_balance.empty: counts_balance=pd.concat([counts_balance,self.logic._cih_total_row(counts_balance,"Wallets")],ignore_index=True)
            if not counts_wd.empty: counts_wd=pd.concat([counts_wd,self.logic._cih_total_row(counts_wd,"Wallets")],ignore_index=True)
            return {
                "CURRENT PERSONAL WALLET BALANCES":cards,
                "PERSONAL WALLET BALANCES":df,
                "COUNTS OF PERSONAL WALLET BALANCES WITH":counts_balance,
                "COUNTS OF PERSONAL OPEN IN WITHDRAWAL WITH":counts_wd,
            }
        if report_name == "limit-availability":
            d=self.logic.cih_limit_availability()
            personal_daily=d["personal_limit"].copy()
            personal_monthly=d["personal_limit"].copy()
            personal_count=d["personal_count"].copy()
            for col in ["EBANKING","IBANKING","TOTAL"]:
                if col in personal_monthly.columns and col in personal_count.columns:
                    personal_monthly[col]=pd.to_numeric(personal_count[col],errors="coerce").fillna(0) * 300000
            return {
                "LIMIT AVAILABILITY - AGENT":d["agent_limit"],
                "LIMIT AVAILABILITY - PERSONAL (DAILY)":personal_daily,
                "LIMIT AVAILABILITY - PERSONAL (MONTHLY)":personal_monthly,
            }
        raise ValueError("Unknown Telegram report.")

    # ---- lightweight chart drawing (pure Pillow — no extra dependencies) ----
    CHART_PALETTE=[(99,102,241),(20,184,166),(245,158,11),(244,63,94),(14,165,233),(168,85,247)]

    def _report_chart(self, report_name):
        """Returns a small chart spec to render above the table(s) in the
        Telegram report image, or None when a chart wouldn't add anything
        (e.g. no data yet). Kept deliberately simple: one chart per report,
        sized to the handful of wallets these reports always have."""
        try:
            if report_name=="limit-utilization":
                df=self.logic.dashboard_limit_utilization()["agent"]
                if df is None or df.empty: return None
                df=df[~df.iloc[:,0].astype(str).str.upper().eq("TOTAL")]
                if df.empty or "LIMIT" not in df.columns or "DEPOSIT" not in df.columns: return None
                cats=[str(v) for v in df.iloc[:,0].tolist()][:8]
                limits=[float(v or 0) for v in df["LIMIT"].tolist()][:8]
                deposits=[float(v or 0) for v in df["DEPOSIT"].tolist()][:8]
                if not any(limits) and not any(deposits): return None
                return {"type":"bar","title":"Agent Limit vs Deposit","categories":cats,
                        "series":[("Limit",self.CHART_PALETTE[0],limits),("Deposit",self.CHART_PALETTE[1],deposits)]}
            if report_name in ("cih-agent","cih-personal"):
                df=self.logic._cih_wallet_table(report_name=="cih-personal").copy()
                wallets=["BKASHC","NAGADC","ROCKETC","UPAYC"] if report_name=="cih-personal" else ["BKASH","NAGAD","ROCKET","UPAY"]
                df=df[df["Wallet Name"].isin(wallets)]
                slices=[(str(r["Wallet Name"]),self.CHART_PALETTE[i%len(self.CHART_PALETTE)],float(r["System Balance"] or 0))
                        for i,(_,r) in enumerate(df.iterrows()) if float(r["System Balance"] or 0)>0]
                if not slices: return None
                kind="Personal" if report_name=="cih-personal" else "Agent"
                return {"type":"donut","title":f"{kind} Wallet Share","slices":slices}
            if report_name=="limit-availability":
                d=self.logic.cih_limit_availability()
                agent=float(d.get("overall_agent") or 0); personal=float(d.get("overall_personal") or 0)
                if agent<=0 and personal<=0: return None
                return {"type":"bar","title":"Overall Availability","categories":["Agent","Personal"],
                        "series":[("Available",self.CHART_PALETTE[0],[agent,personal])]}
        except Exception:
            return None
        return None

    def _chart_block_height(self, chart):
        if not chart: return 0
        if chart["type"]=="bar": return 26+22+6+150+24+28
        if chart["type"]=="donut": return max(170, len(chart["slices"])*24+10)+26+28
        return 0

    def _draw_legend(self, draw, x, y, items, font):
        lx=x
        for label,color in items:
            draw.ellipse([lx,y+3,lx+11,y+14],fill=color)
            draw.text((lx+16,y),label,fill=(60,70,90),font=font)
            lx+=16+int(draw.textlength(label,font=font))+20
        return y+24

    def _draw_chart_block(self, draw, x, y, w, chart, title_font, label_font):
        draw.text((x,y),chart["title"],fill=(18,31,53),font=title_font); y+=30
        if chart["type"]=="bar":
            if len(chart["series"])>1:
                y=self._draw_legend(draw,x,y,[(s[0],s[1]) for s in chart["series"]],label_font)
            else:
                y+=10
            h=150; chart_top=y+6; chart_bottom=chart_top+h
            cats=chart["categories"]; series=chart["series"]
            max_val=max([v for _,_,vals in series for v in vals]+[1]) or 1
            n=max(1,len(cats)); group_w=w/n; bar_w=group_w/(len(series)+1)
            for frac,dash in ((0.0,False),(0.5,True),(1.0,False)):
                gy=chart_bottom-frac*h
                draw.line([x,gy,x+w,gy],fill=(225,229,236))
            for i,cat in enumerate(cats):
                gx=x+i*group_w+bar_w*0.4
                for j,(_,color,vals) in enumerate(series):
                    val=vals[i] if i<len(vals) else 0
                    bh=(val/max_val)*h if max_val else 0
                    bx=gx+j*bar_w
                    draw.rectangle([bx,chart_bottom-bh,bx+bar_w*0.82,chart_bottom],fill=color)
                label=str(cat)[:14]
                tw=int(draw.textlength(label,font=label_font))
                draw.text((x+i*group_w+group_w/2-tw/2,chart_bottom+8),label,fill=(60,70,90),font=label_font)
            return chart_bottom+28
        if chart["type"]=="donut":
            r=78; cx=x+r+10; cy=y+r+6
            total=sum(v for _,_,v in chart["slices"]) or 1
            start=-90.0
            for _,color,val in chart["slices"]:
                extent=360.0*(val/total)
                draw.pieslice([cx-r,cy-r,cx+r,cy+r],start,start+extent,fill=color)
                start+=extent
            inner=int(r*0.56)
            draw.ellipse([cx-inner,cy-inner,cx+inner,cy+inner],fill=(248,250,252))
            lx=x+2*r+40; ly=y+4
            for label,color,val in chart["slices"]:
                pct=val/total*100 if total else 0
                draw.rectangle([lx,ly+3,lx+12,ly+15],fill=color)
                draw.text((lx+18,ly),f"{label} — {pct:.0f}%",fill=(40,48,64),font=label_font)
                ly+=24
            return max(cy+r, ly)+28
        return y

    def build_report_image(self, report_name):
        sections=self._report_df(report_name)
        chart=self._report_chart(report_name)
        font=self._font(18); head=self._font(26,True); section_font=self._font(20,True); label_font=self._font(16)
        row_h=30; section_gap=28; margin=28
        widths={}
        rendered=[]
        for title,df in sections.items():
            df=df.copy()
            if df is None: df=pd.DataFrame()
            cols=list(df.columns)
            str_rows=[]
            for _,row in df.iterrows():
                str_rows.append([self._format_cell(v) for v in row.tolist()])
            if not cols:
                str_rows=[[]]
            # col widths from content
            for i,c in enumerate(cols):
                vals=[str(c)]+[r[i] for r in str_rows if i<len(r)]
                widths[(title,i)]=max(90,min(260,max(70,max(len(str(v)) for v in vals)*9+24)))
            width=sum(widths[(title,i)] for i in range(len(cols)))
            height=52 + row_h*(len(str_rows)+1)
            rendered.append((title,df,cols,str_rows,width,height))
        chart_h=self._chart_block_height(chart)
        chart_min_w=420 if chart and chart["type"]=="donut" else (len(chart["categories"])*90 if chart else 0)
        total_w=max([r[4] for r in rendered]+[chart_min_w] or [500])+margin*2
        total_h=chart_h+sum(r[5]+section_gap for r in rendered)+margin*2
        img=Image.new("RGB",(total_w,total_h),(248,250,252)); draw=ImageDraw.Draw(img)
        y=margin
        if chart:
            y=self._draw_chart_block(draw,margin,y,total_w-margin*2,chart,section_font,label_font)
        for title,df,cols,str_rows,width,height in rendered:
            draw.text((margin,y),title,fill=(18,31,53),font=section_font); y+=34
            x=margin
            for i,c in enumerate(cols):
                w=widths[(title,i)]; draw.rectangle([x,y,x+w,y+row_h],fill=(18,31,53),outline=(150,160,175)); draw.text((x+6,y+6),str(c),fill=(255,255,255),font=font); x+=w
            y+=row_h
            for ridx,row in enumerate(str_rows):
                x=margin
                for i,val in enumerate(row):
                    w=widths[(title,i)]; fill=(255,255,255) if ridx%2==0 else (242,245,248)
                    draw.rectangle([x,y,x+w,y+row_h],fill=fill,outline=(190,196,205))
                    is_neg=str(val).strip().startswith("-") and str(val).strip()!='-'
                    color=(200,40,40) if is_neg else (30,35,45)
                    draw.text((x+6,y+6),val,fill=color,font=font); x+=w
                y+=row_h
            y+=section_gap
        out=self.integrations_dir/f"telegram_{report_name}.png"; img.save(out); return out

    @staticmethod
    def _format_cell(v):
        """Whole-number values (including floats such as 12.0 created by pandas
        concatenation) are shown without a trailing .00; other numbers keep two decimals."""
        if v is None or (isinstance(v,(float,np.floating)) and pd.isna(v)): return "-"
        try:
            if isinstance(v,(int,float,np.integer,np.floating)):
                num=float(v)
                if num==0: return "-"
                if num.is_integer(): return f"{int(num):,}"
                return f"{num:,.2f}"
        except Exception: pass
        s=str(v).strip()
        if s.lower() in {"nan","nat","none","null",""}: return "-"
        return s

    def _report_destinations(self):
        tg=self._load_config().get("telegram",{})
        destinations=tg.get("destinations",[])
        selected=tg.get("report_destination_ids",[])
        by_id={str(d.get("id")):d for d in destinations if d.get("enabled",True) and str(d.get("chat_id","")).strip()}
        chosen=[by_id[x] for x in selected if x in by_id][:3]
        if chosen:
            return chosen
        fallback=self._web_telegram_destination()
        return [fallback] if fallback else []

    def _send_report_to_destination(self, report_name, dest, generated_at=None):
        chat_id=str(dest.get("chat_id","")).strip()
        if not chat_id:
            raise RuntimeError("Telegram destination has no Chat ID.")
        raw_thread=str(dest.get("topic_id","")).strip()
        if raw_thread and not raw_thread.lstrip("-").isdigit():
            raise RuntimeError(
                f"Telegram destination '{dest.get('name','')}' has an invalid Topic ID ('{raw_thread}') — "
                "it must be a numeric forum-topic thread ID. Edit the destination in Admin → Integrations "
                "and clear or fix the Topic ID."
            )
        thread_id=int(raw_thread) if raw_thread else None
        generated_at = generated_at or datetime.now().astimezone()
        path=self.build_report_image(report_name)
        data={"chat_id":chat_id,"caption":self._caption(report_name, generated_at)}
        if thread_id is not None: data["message_thread_id"]=str(thread_id)
        with open(path,"rb") as f:
            self._tg("sendPhoto", data=data, files={"photo":(path.name,f,"image/png")})

    def send_report(self, report_name, chat_id=None, thread_id=None, use_web_topic=False):
        generated_at = datetime.now().astimezone()
        if use_web_topic:
            destinations=self._report_destinations()
            if not destinations:
                raise RuntimeError("No active Telegram report destination is registered.")
            for dest in destinations:
                self._send_report_to_destination(report_name,dest,generated_at=generated_at)
            return len(destinations)
        chat_id=str(chat_id if chat_id is not None else self._tg_cfg().get("chat_id","")).strip()
        if not chat_id:
            raise RuntimeError("Telegram chat ID is not configured.")
        path=self.build_report_image(report_name)
        data={"chat_id":chat_id,"caption":self._caption(report_name, generated_at)}
        if thread_id is not None: data["message_thread_id"]=str(thread_id)
        with open(path,"rb") as f:
            self._tg("sendPhoto", data=data, files={"photo":(path.name,f,"image/png")})
        return 1

    def send_reports(self, reports, use_web_topic=False):
        total=0
        for name in reports:
            total += self.send_report(name, use_web_topic=use_web_topic)
        return total

    @staticmethod
    def _format_report_timestamp(value):
        dt = value if isinstance(value, datetime) else datetime.now().astimezone()
        if dt.tzinfo is None:
            dt = dt.astimezone()
        offset = dt.utcoffset()
        if offset is None:
            zone = ""
        else:
            total_minutes = int(offset.total_seconds() // 60)
            sign = "+" if total_minutes >= 0 else "-"
            total_minutes = abs(total_minutes)
            zone = f" UTC{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"
        return dt.strftime("%d %b %Y, %H:%M:%S") + zone

    @classmethod
    def _caption(cls, name, generated_at=None):
        title = {
            "limit-utilization":"SSG AGT — Limit Utilization",
            "cih-agent":"SSG AGT — CIH Overview: Agent Wallet Balances",
            "cih-personal":"SSG AGT — CIH Overview: Personal Wallet Balances",
            "limit-availability":"SSG AGT — CIH Overview: Limit Availability",
        }.get(name,"SSG AGT Report")
        return f"{title}\nGenerated: {cls._format_report_timestamp(generated_at)}"
