"""SSG AGT features exposed as a JSON API (mounted under /api/ssg).

The business logic (``ssg/logic_core.py``) is the Team Lead's calculation
engine (kept in step with his V1.84 build -- his calculations always win).  This module only:
  * owns the in-memory ``AppData`` / ``BusinessLogic`` singletons,
  * turns DataFrames into JSON tables the React UI can render,
  * enforces the unified role/permission model on every endpoint.
"""
import io
import json
import math
import shutil
import tempfile
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import perm, get_current_user
from database import get_db
from models import User
from ssg.logic_core import AppData, BusinessLogic, DATA_DIR, MONITOR_COLUMNS
from ssg.integrations import IntegrationManager
from ssg import filters as F

EXPORTS = DATA_DIR / "exports"
EXPORTS.mkdir(parents=True, exist_ok=True)
UPLOAD_TMP = DATA_DIR / "uploads"
UPLOAD_TMP.mkdir(parents=True, exist_ok=True)

DATA = AppData()
LOGIC = BusinessLogic(DATA)
INTEGRATIONS = IntegrationManager(DATA_DIR, LOGIC, DATA)

DATASETS = ["Deposit History", "Pay Out History", "Account Statement", "Active Accounts", "Locked Accounts",
            "Disabled Accounts", "Opening", "Limit", "Settlement / Top up"]
DATASET_LABELS = {d: d for d in DATASETS}
DATASET_LABELS["Settlement / Top up"] = "Settlement / Top Up"
# upload form field -> dataset name (same field names the original app used)
UPLOAD_FIELDS = {
    "deposit_history": "Deposit History", "pay_out_history": "Pay Out History",
    "account_statement": "Account Statement", "active_accounts": "Active Accounts",
    "locked_accounts": "Locked Accounts", "disabled_accounts": "Disabled Accounts",
    "opening": "Opening", "limit_file": "Limit", "settlement_topup": "Settlement / Top up",
    "wallet_master": "Wallet Account Master List", "permanently_closed": "Permanently Closed Accounts",
}
CLEAR_PERM = {"Active Accounts": "imports_active", "Locked Accounts": "imports_locked", "Disabled Accounts": "imports_disabled"}

router = APIRouter(prefix="/api/ssg", tags=["ssg"])


# ----------------------------------------------------------------- helpers ---

FIN_FRAGMENTS = (
    "MRC LMT", "MRC DP LIMIT", "SDP PAID", "ACT SDP", "OPENING", "DEPOSIT", "WITHDRAWAL", "ADJUSTMENT", "R. BAL",
    "A. BAL", "DISCREP", "BALANCE", "PAYOUT", "STLM", "TOP UP", "SETTLEMENT", "SPECIAL PAYMENT", "INTERNAL TRANSFER",
    "COMMISSION", "ENDING", "RUNNING", "LIMIT", "FEE", "AMOUNT", "SYSTEM BAL", "CLOSING", "PROCESS",
)
NON_FIN = {"ACCOUNT NUMBER", "WALLET ACCOUNT", "ACCOUNTS", "WALLETNAME", "WALLET NAME", "CODE", "BANK CODE", "STATUS",
           "GROUP CODE", "HOURS", "W. HRS", "<25K", "25K+", "50K+", "100K+"}


def is_financial(col) -> bool:
    n = str(col or "").strip().upper()
    return n not in NON_FIN and any(f in n for f in FIN_FRAGMENTS)


def _clean(v):
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return str(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def pack(df: Optional[pd.DataFrame], financial=None, hide=("_TYPE",)) -> dict:
    """DataFrame -> {columns, financial, rows} with NaN -> null."""
    if df is None or df.empty:
        cols = [c for c in (df.columns if df is not None else []) if c not in hide]
        return {"columns": cols, "financial": [], "rows": []}
    part = df.drop(columns=[c for c in hide if c in df.columns])
    cols = [str(c) for c in part.columns]
    fin = [c for c in cols if is_financial(c)] if financial is None else list(financial)
    rows = [{str(k): _clean(v) for k, v in r.items()} for r in part.to_dict(orient="records")]
    return {"columns": cols, "financial": fin, "rows": rows}


def with_total(df: pd.DataFrame, label_col: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    return pd.concat([df, LOGIC._cih_total_row(df, label_col)], ignore_index=True)


def paginate(df: Optional[pd.DataFrame], page: int, per_page: int):
    per_page = per_page if per_page in (25, 50, 100, 250) else 25
    total = 0 if df is None else len(df)
    pages = max(1, math.ceil(total / per_page))
    page = min(max(1, int(page or 1)), pages)
    part = df.iloc[(page - 1) * per_page: page * per_page] if df is not None and total else df
    return part, {"page": page, "per_page": per_page, "total": total, "pages": pages}


def options_of(df: pd.DataFrame, col: str) -> list[str]:
    if df is None or df.empty or col not in df.columns:
        return []
    return sorted(set(df[col].astype(str).str.strip()) - {"", "nan"})


def export_xlsx(df: pd.DataFrame, name: str) -> FileResponse:
    df = (df if df is not None else pd.DataFrame()).drop(columns=["_TYPE", "_PERMANENT_STOP"], errors="ignore")
    path = EXPORTS / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df.to_excel(path, index=False, engine="openpyxl")
    return FileResponse(path, filename=path.name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _contains_any(df: pd.DataFrame, q: str) -> pd.DataFrame:
    if not q or df is None or df.empty:
        return df
    return df[df.astype(str).apply(lambda c: c.str.contains(q, case=False, na=False, regex=False)).any(axis=1)]


def _in_filter(df: pd.DataFrame, field: str, values: list[str]) -> pd.DataFrame:
    if values and df is not None and not df.empty and field in df.columns:
        allowed = {str(v).strip().casefold() for v in values if str(v).strip()}
        if allowed:
            return df[df[field].astype(str).str.strip().str.casefold().isin(allowed)]
    return df


def _master_df() -> pd.DataFrame:
    return DATA.dataframes.get("Wallet Account Master List", pd.DataFrame(columns=AppData.MASTER_COLUMNS)).copy()


# ------------------------------------------------------------------ status ---

@router.get("/status")
def ssg_status(user: User = Depends(get_current_user)):
    counts = {k: int(len(DATA.dataframes.get(k, []))) for k in DATASETS}
    counts["Wallet Account Master List"] = int(len(DATA.dataframes.get("Wallet Account Master List", [])))
    counts["Permanently Closed Accounts"] = int(len(DATA.dataframes.get("Permanently Closed Accounts", [])))
    return {
        "counts": counts,
        "extended_opening_active": bool(DATA.extended_opening_active),
        "extended_accounts": len(DATA.extended_opening_map or {}),
        "google_configured": INTEGRATIONS.google_configured(),
        "telegram_configured": INTEGRATIONS.telegram_configured(),
        "summary_generated": not DATA.summary_result.empty,
    }


# --------------------------------------------------------- command center ---

@router.get("/dashboard")
def command_center(user: User = Depends(perm("dashboard"))):
    util = LOGIC.dashboard_limit_utilization()
    fin = ["LIMIT", "Remaining Limit", "DEPOSIT"]
    return {
        "totals": {k: float(v) for k, v in LOGIC.dashboard_totals().items()},
        "utilization": {
            "agent": pack(util["agent"], fin),
            "personal_ebanking": pack(util["personal_ebanking"], fin),
            "personal_ibanking": pack(util["personal_ibanking"], fin),
        },
        "telegram_configured": INTEGRATIONS.telegram_configured(),
    }


# --------------------------------------------------------------------- CIH ---

@router.get("/cih/summary")
def cih_summary(user: User = Depends(perm("cih_summary"))):
    tabs = []
    for name, df in [("Deposit Type Summary", DATA.deposit_type_result), ("Merchant Deposit", DATA.merchant_deposit_result),
                     ("Merchant Pay out", DATA.merchant_payout_result)]:
        prepared = F.summary_table_with_row_total(df)
        if prepared is not None and not prepared.empty:
            fin = list(prepared.columns[1:])
            tabs.append({"name": name, "table": pack(with_total(prepared, prepared.columns[0]), fin)})
        else:
            tabs.append({"name": name, "table": pack(None)})
    return {"tabs": tabs}


def _cih_wallet_payload(personal: bool):
    wallets = ["BKASHC", "NAGADC", "ROCKETC", "UPAYC"] if personal else ["BKASH", "NAGAD", "ROCKET", "UPAY"]
    df = LOGIC._cih_wallet_table(personal)
    df = df[df["Wallet Name"].isin(wallets)].copy()
    counts = [LOGIC._cih_count_table(personal, False), LOGIC._cih_count_table(personal, True)]
    kind = "PERSONAL" if personal else "AGENT"
    cards = [{"wallet": r["Wallet Name"], "system_balance": _clean(r["System Balance"])} for r in df.to_dict("records")]
    table = pack(with_total(df, "Wallet Name"), list(df.columns[1:]))
    count_tables = []
    titles = [f"COUNTS OF {kind} WALLET BALANCES WITH", f"COUNTS OF {kind} OPEN IN WITHDRAWAL WITH"]
    for title, cdf in zip(titles, counts):
        cols = list(cdf.columns[1:]) if cdf is not None and not cdf.empty else []
        count_tables.append({"title": title, "table": {**pack(with_total(cdf, "Wallets") if cdf is not None else cdf, []),
                                                       "counts": cols}})
    return {"kind": kind, "wallets": wallets, "cards": cards, "table": table, "counts": count_tables}


@router.get("/cih/agent")
def cih_agent(user: User = Depends(perm("cih_agent"))):
    return _cih_wallet_payload(False)


@router.get("/cih/personal")
def cih_personal(user: User = Depends(perm("cih_personal"))):
    return _cih_wallet_payload(True)


@router.get("/cih/limit-availability")
def cih_limit_availability(personal_mode: str = "daily", user: User = Depends(perm("cih_limit_availability"))):
    d = LOGIC.cih_limit_availability()
    # Personal accounts: Daily (default, current logic) or Monthly = eligible account count x 300,000
    # for Ebanking / Ibanking (supervisor's V1.58 logic).
    mode = "monthly" if str(personal_mode).strip().lower() == "monthly" else "daily"
    personal_limit_df = d["personal_limit"].copy()
    personal_total_df = d["personal_limit_total"].copy()
    if mode == "monthly":
        count_df = d["personal_count"].copy()
        monthly = personal_limit_df.copy()
        for col in ["EBANKING", "IBANKING", "TOTAL"]:
            if col in monthly.columns and col in count_df.columns:
                monthly[col] = pd.to_numeric(count_df[col], errors="coerce").fillna(0) * 300000
        personal_limit_df = monthly
        personal_total_df = d["personal_count_total"].copy()
        for col in ["EBANKING", "IBANKING", "TOTAL"]:
            if col in personal_total_df.columns:
                personal_total_df[col] = pd.to_numeric(personal_total_df[col], errors="coerce").fillna(0) * 300000

    def t(df):
        return pack(df, [c for c in df.columns if c != "Wallet"] if df is not None and not df.empty else [])

    overall_personal = personal_total_df.iloc[0]["TOTAL"] if personal_total_df is not None and not personal_total_df.empty \
        and "TOTAL" in personal_total_df.columns else 0
    return {
        "personal_mode": mode,
        "agent_limit": t(d["agent_limit"]), "agent_limit_total": t(d["agent_limit_total"]),
        "agent_count": t(d["agent_count"]), "agent_count_total": t(d["agent_count_total"]),
        "personal_limit": t(personal_limit_df), "personal_limit_total": t(personal_total_df),
        "personal_count": t(d["personal_count"]), "personal_count_total": t(d["personal_count_total"]),
        "overall_agent": _clean(d["overall_agent"]), "overall_personal": _clean(overall_personal),
    }


# ---------------------------------------------------- monitoring / overview ---

def _monitoring_frame():
    return LOGIC.build_account_monitoring_dataframe()


def _monitor_type_perm(slug: str):
    typ = F.MONITOR_SLUGS.get(slug)
    if not typ:
        raise HTTPException(404, "Unknown monitoring view")
    return typ, F.MONITOR_PERMS[typ]


def _require(user: User, db: Session, key: str):
    from auth import user_permissions
    if key not in user_permissions(db, user):
        raise HTTPException(403, "You don't have permission to do this")


@router.get("/monitoring/{slug}")
def monitoring(slug: str, q: str = "", status: list[str] = Query(default=[]), code: list[str] = Query(default=[]),
               wallet: list[str] = Query(default=[]), limit_status: list[str] = Query(default=[]),
               whrs: list[str] = Query(default=[]), sort_rbal: str = "",
               page: int = 1, per_page: int = 25, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    typ, key = _monitor_type_perm(slug)
    _require(user, db, key)
    df = _monitoring_frame()
    part = F.filter_monitoring_dataframe(df, slug, q, status, code, wallet, limit_status, whrs, sort_rbal)
    page_df, meta = paginate(part, page, per_page)
    tbl = pack(page_df[MONITOR_COLUMNS] if page_df is not None and not page_df.empty else page_df, hide=("_TYPE", "_PERMANENT_STOP"))
    if not tbl["columns"]:
        tbl["columns"] = MONITOR_COLUMNS
    # headline numbers for the *filtered* set (all pages), used by the KPI strip
    def total(col):
        return float(pd.to_numeric(part[col], errors="coerce").fillna(0).sum()) if part is not None and not part.empty and col in part.columns else 0.0
    return {
        **tbl, **meta, "type": typ,
        "options": {"status": options_of(df, "STATUS"), "code": options_of(df, "CODE"),
                    "wallet": options_of(df, "WALLET"), "limit_status": options_of(df, "LIMIT STATUS"),
                    "whrs": options_of(df, "W. HRS")},
        "kpis": {"accounts": meta["total"], "opening": total("OPENING"), "deposit": total("DEPOSIT"),
                 "withdrawal": total("WITHDRAWAL"), "r_bal": total("R. BAL"), "a_bal": total("A. BAL"),
                 "discrep": total("DISCREP")},
    }


@router.get("/export/monitoring/{slug}")
def export_monitoring(slug: str, q: str = "", status: list[str] = Query(default=[]), code: list[str] = Query(default=[]),
                      wallet: list[str] = Query(default=[]), limit_status: list[str] = Query(default=[]),
                      whrs: list[str] = Query(default=[]), sort_rbal: str = "",
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    typ, key = _monitor_type_perm(slug)
    _require(user, db, key)
    part = F.filter_monitoring_dataframe(_monitoring_frame(), slug, q, status, code, wallet, limit_status, whrs, sort_rbal)
    return export_xlsx(part, f"monitoring_{slug}")


def _overview_type_perm(slug: str):
    typ = F.OVERVIEW_SLUGS.get(slug)
    if not typ:
        raise HTTPException(404, "Unknown overview view")
    return typ, F.OVERVIEW_PERMS[typ]


@router.get("/overview/{slug}")
def account_overview(slug: str, threshold: str = "", code: str = "", acct_type: str = "", wallet: str = "",
                     category: str = "ALL", q: str = "", limit_type: str = "ALL",
                     status: list[str] = Query(default=[]), status_code: list[str] = Query(default=[]),
                     sort_rbal: str = "", page: int = 1, per_page: int = 25,
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    typ, key = _overview_type_perm(slug)
    _require(user, db, key)
    df = _monitoring_frame()
    part = F.filter_overview_dataframe(df, slug, threshold, code, acct_type, wallet, category, q, limit_type, status, status_code, sort_rbal)
    page_df, meta = paginate(part, page, per_page)
    tbl = pack(page_df[MONITOR_COLUMNS] if page_df is not None and not page_df.empty else page_df)
    if not tbl["columns"]:
        tbl["columns"] = MONITOR_COLUMNS
    heading = {"Agent Accounts": "Agent Account Overview", "Personal Accounts": "Personal Account Overview",
               "High Discrepancy": "High Discrepancy", "Limit Reached": "Limit Reached"}[typ]
    return {
        **tbl, **meta, "type": typ, "heading": heading,
        "needs_threshold": typ in ("Agent Accounts", "Personal Accounts", "High Discrepancy"),
        "options": {"code": options_of(df, "CODE"), "acct_type": options_of(df, "ACCT TYPE"),
                    "wallet": options_of(df, "WALLET"), "status": options_of(df, "STATUS")},
    }


@router.get("/export/overview/{slug}")
def export_overview(slug: str, threshold: str = "", code: str = "", acct_type: str = "", wallet: str = "",
                    category: str = "ALL", q: str = "", limit_type: str = "ALL",
                    status: list[str] = Query(default=[]), status_code: list[str] = Query(default=[]),
                    sort_rbal: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    typ, key = _overview_type_perm(slug)
    _require(user, db, key)
    part = F.filter_overview_dataframe(_monitoring_frame(), slug, threshold, code, acct_type, wallet, category, q,
                                       limit_type, status, status_code, sort_rbal)
    return export_xlsx(part, f"overview_{slug}")


# ------------------------------------------------------------- data import ---

@router.post("/import")
async def import_files(
    deposit_history: UploadFile | None = File(None), pay_out_history: UploadFile | None = File(None),
    account_statement: UploadFile | None = File(None), active_accounts: UploadFile | None = File(None),
    locked_accounts: UploadFile | None = File(None), disabled_accounts: UploadFile | None = File(None),
    opening: UploadFile | None = File(None), limit_file: UploadFile | None = File(None),
    settlement_topup: UploadFile | None = File(None), wallet_master: UploadFile | None = File(None),
    permanently_closed: UploadFile | None = File(None),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    from auth import user_permissions
    granted = user_permissions(db, user)
    # Supervisor's rules: any import page permission opens the endpoint; whoever holds
    # "Import Data" also needs the "Import / Generate" action permission.
    if not any(k in granted for k in ("imports_data", "imports_master", "imports_closed")):
        raise HTTPException(403, "You don't have permission to do this")
    if "imports_data" in granted and "imports_edit" not in granted:
        raise HTTPException(403, "You don't have permission to do this")
    given = {"deposit_history": deposit_history, "pay_out_history": pay_out_history,
             "account_statement": account_statement, "active_accounts": active_accounts,
             "locked_accounts": locked_accounts, "disabled_accounts": disabled_accounts, "opening": opening,
             "limit_file": limit_file, "settlement_topup": settlement_topup, "wallet_master": wallet_master,
             "permanently_closed": permanently_closed}
    imported, errors = [], []
    any_file = False
    for field, up in given.items():
        if up is None or not up.filename:
            continue
        any_file = True
        dataset = UPLOAD_FIELDS[field]
        label = DATASET_LABELS.get(dataset, dataset)
        if dataset == "Wallet Account Master List" and "imports_master" not in granted:
            errors.append(f"{label}: permission denied"); continue
        if dataset == "Permanently Closed Accounts" and "imports_closed" not in granted:
            errors.append(f"{label}: permission denied"); continue
        if dataset not in ("Wallet Account Master List", "Permanently Closed Accounts") and "imports_data" not in granted:
            errors.append(f"{label}: permission denied"); continue
        ext = Path(up.filename).suffix.lower()
        if ext not in {".csv", ".xlsx", ".xls"}:
            errors.append(f"{label}: unsupported file type"); continue
        tmp = UPLOAD_TMP / f"_tmp_{field}{ext}"
        try:
            with tmp.open("wb") as fh:
                shutil.copyfileobj(up.file, fh)
            if dataset == "Permanently Closed Accounts":
                cdf = pd.read_csv(tmp, dtype=str, keep_default_na=False) if ext == ".csv" else pd.read_excel(
                    tmp, engine="openpyxl" if ext == ".xlsx" else "xlrd", dtype=str)
                msg, ok = DATA.merge_closed_dataframe(cdf), True
            else:
                ok, msg = DATA.load_file(dataset, str(tmp))
            (imported if ok else errors).append(f"{label} ({msg} rows)" if ok else f"{label}: {msg}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {exc}")
        finally:
            tmp.unlink(missing_ok=True)
    # Refresh the persistent Master List's automatic fields right after imports.
    # HOURS / METHOD only change when a GROUP CODE rule applies.
    if any_file:
        try:
            LOGIC.sync_master_from_imports()
        except Exception:  # noqa: BLE001
            pass
    if not any_file:
        raise HTTPException(400, "No files selected. Choose the new daily/current files, then click Import & Save All.")
    return {"imported": imported, "errors": errors}


class ClearIn(BaseModel):
    dataset: str


@router.post("/import/clear")
def clear_import(payload: ClearIn, user: User = Depends(perm("imports_data", "imports_delete")), db: Session = Depends(get_db)):
    ds = payload.dataset
    if ds not in DATASETS:
        raise HTTPException(400, f"Invalid dataset: {ds}")
    if ds in CLEAR_PERM:
        _require(user, db, CLEAR_PERM[ds])
    before = len(DATA.dataframes.get(ds, []))
    DATA.clear_dataset(ds)
    if ds in ("Active Accounts", "Locked Accounts", "Disabled Accounts"):
        DATA.locked_disabled_result = pd.DataFrame()
    after = len(DATA.dataframes.get(ds, []))
    return {"message": f"{DATASET_LABELS.get(ds, ds)} cleared: {before:,} row(s) removed. Current rows: {after:,}."}


@router.post("/import/extend-opening")
def extend_opening(user: User = Depends(perm("imports_data", "imports_edit"))):
    count = LOGIC.extend_opening_balance()
    if not count:
        raise HTTPException(400, "Extended Opening Balance could not be applied. Import data and generate Account Monitoring first.")
    return {"message": f"Extended Opening Balance applied to {count:,} account(s) using current R. BAL. Imported Opening data was not changed."}


@router.post("/import/revert-opening")
def revert_opening(user: User = Depends(perm("imports_data", "imports_edit"))):
    was = LOGIC.revert_opening_balance()
    return {"message": "Extended Opening Balance reverted. The imported Opening data is being used again." if was
            else "Extended Opening Balance is already using the imported Opening data."}


class GenerateIn(BaseModel):
    from_date: str = ""
    to_date: str = ""
    client_timestamp: str = ""


def _record_generate(db: Session, user: User, client_timestamp: str = "") -> str:
    """Per-user 'Last Generate' stamp: the generating PC's local time + UTC offset
    (the browser sends it); the server's local time is the fallback."""
    stamp = str(client_timestamp or "").strip() or datetime.now().astimezone().isoformat(timespec="seconds")
    user.last_generate_at = stamp
    db.add(user)
    db.commit()
    return stamp


def _run_generate(payload: GenerateIn):
    try:
        fd = pd.to_datetime(payload.from_date).date() if payload.from_date else None
        td = pd.to_datetime(payload.to_date).date() if payload.to_date else None
        LOGIC.generate_summary(fd, td)
        LOGIC.find_unknown_accounts(fd, td)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Could not generate summary: {exc}")


@router.post("/import/generate")
def generate(payload: GenerateIn, user: User = Depends(perm("imports_data", "imports_edit")), db: Session = Depends(get_db)):
    _run_generate(payload)
    stamp = _record_generate(db, user, payload.client_timestamp)
    return {"message": "Summary generated successfully.", "last_generate_at": stamp}


@router.post("/generate")
def generate_from_dashboard(payload: GenerateIn, user: User = Depends(perm("dashboard", "dashboard_generate")),
                            db: Session = Depends(get_db)):
    """Dedicated 'Generate Dashboard' permission (kept from the supervisor's role model)."""
    _run_generate(payload)
    stamp = _record_generate(db, user, payload.client_timestamp)
    return {"message": "Summary generated successfully.", "last_generate_at": stamp}


@router.post("/import/sync-google")
def sync_google(user: User = Depends(perm("imports_google_sync"))):
    try:
        r = INTEGRATIONS.sync_current_account_statuses()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Google Sheets sync failed: {exc}")
    return {"message": f"Google Sheets synced: Active {r['Active']} rows, Locked {r['Locked']} rows, Disabled {r['Disabled']} rows."}


TEMPLATES = {"master": ("Wallet_Account_Master_Template.xlsx", lambda p: DATA.export_master_template(p)),
             "opening": ("Opening_Template.xlsx", lambda p: DATA.export_opening_template(p)),
             "settlement-topup": ("Settlement_Top_Up_Template.xlsx", lambda p: DATA.export_settlement_topup_template(p)),
             "closed": ("Permanently_Closed_Accounts_Template.xlsx",
                        lambda p: pd.DataFrame(columns=AppData.CLOSED_COLUMNS).to_excel(p, index=False, engine="openpyxl"))}
TEMPLATE_PERMS = {"master": "imports_master", "opening": "imports_data", "settlement-topup": "imports_data",
                  "closed": "imports_closed"}


@router.get("/template/{name}")
def template(name: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if name not in TEMPLATES:
        raise HTTPException(404, "Unknown template")
    _require(user, db, TEMPLATE_PERMS[name])
    fname, make = TEMPLATES[name]
    path = EXPORTS / fname
    make(str(path))
    return FileResponse(path, filename=fname)


# ---------------------------------------------- active / locked / disabled ---

STATUS_CFG = {"active": ("Active Accounts", "ACTIVE", "imports_active"),
              "locked": ("Locked Accounts", "LOCKED", "imports_locked"),
              "disabled": ("Disabled Accounts", "DISABLED", "imports_disabled")}


def _status_frame(slug: str, q: str):
    df = LOGIC.generate_locked_disabled_result()
    heading, status, _ = STATUS_CFG[slug]
    if df is None:
        df = pd.DataFrame()
    if "Status" in df.columns:
        df = df[df["Status"].astype(str).str.strip().str.casefold().eq(status.casefold())]
    return heading, _contains_any(df, q)


@router.get("/accounts-status/{slug}")
def accounts_by_status(slug: str, q: str = "", page: int = 1, per_page: int = 25,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if slug not in STATUS_CFG:
        raise HTTPException(404, "Unknown view")
    _require(user, db, STATUS_CFG[slug][2])
    heading, df = _status_frame(slug, q)
    page_df, meta = paginate(df, page, per_page)
    return {**pack(page_df, []), **meta, "heading": heading}


@router.get("/export/accounts-status")
def export_accounts_status(user: User = Depends(perm(("imports_active", "imports_locked", "imports_disabled")))):
    return export_xlsx(LOGIC.generate_locked_disabled_result(), "Active_Locked_Disabled")


# -------------------------------------------------------- generated statements ---

STATEMENTS = {
    "account": ("Account Statement", lambda: DATA.summary_result),
    "merchant-deposit": ("Merchant Deposit", lambda: DATA.merchant_deposit_result),
    "merchant-payout": ("Merchant Pay out", lambda: DATA.merchant_payout_result),
    "deposit-type": ("Deposit type Summary", lambda: DATA.deposit_type_result),
}


@router.get("/statements")
def statements_overview(user: User = Depends(perm("imports_statement"))):
    return {"tabs": [{"key": k, "name": n, "rows": int(len(getter()) if getter() is not None else 0)}
                     for k, (n, getter) in STATEMENTS.items()]}


@router.get("/statements/{key}")
def statement_tab(key: str, page: int = 1, per_page: int = 25, user: User = Depends(perm("imports_statement"))):
    if key not in STATEMENTS:
        raise HTTPException(404, "Unknown statement")
    name, getter = STATEMENTS[key]
    df = getter()
    page_df, meta = paginate(df, page, per_page)
    return {**pack(page_df), **meta, "name": name}


@router.get("/export/statement/{key}")
def export_statement(key: str, user: User = Depends(perm("imports_statement"))):
    if key not in STATEMENTS:
        raise HTTPException(404, "Unknown statement")
    return export_xlsx(STATEMENTS[key][1](), key.replace("-", "_"))


# ------------------------------------------------------------- master list ---

class MasterRow(BaseModel):
    """Only WALLETNAME / HOURS / METHOD are manual. Every other Master List column is automatic
    (supervisor V1.73-V1.79): MRC DP LIMIT, SDP PAID, WALLET, GROUP CODE, ACCOUNT TYPE."""
    WALLETNAME: str
    HOURS: str = ""
    METHOD: str = ""


def _master_synced() -> pd.DataFrame:
    """Always refresh the auto-populated Master List fields from the current imports first.
    Method / Hours follow GROUP CODE rules when one applies; otherwise saved/manual values are kept."""
    try:
        return LOGIC.sync_master_from_imports().copy()
    except Exception:  # noqa: BLE001
        return _master_df()


def _master_filtered(q, wallet, acct_type, group_code, method, df: Optional[pd.DataFrame] = None):
    df = _master_synced() if df is None else df
    for field, vals in [("WALLET", wallet), ("ACCOUNT TYPE", acct_type), ("GROUP CODE", group_code), ("METHOD", method)]:
        df = _in_filter(df, field, vals)
    if q:
        df = df[df["WALLETNAME"].astype(str).str.contains(q, case=False, na=False, regex=False)]
    return df.sort_values("WALLETNAME", kind="stable")


@router.get("/master")
def master_list(q: str = "", wallet: list[str] = Query(default=[]), acct_type: list[str] = Query(default=[]),
                group_code: list[str] = Query(default=[]), method: list[str] = Query(default=[]),
                page: int = 1, per_page: int = 25, user: User = Depends(perm("master_list"))):
    raw = _master_synced()
    df = _master_filtered(q, wallet, acct_type, group_code, method, raw)
    page_df, meta = paginate(df, page, per_page)
    return {**pack(page_df, ["MRC DP LIMIT", "SDP PAID"]), **meta,
            "options": {"wallet": options_of(raw, "WALLET"), "acct_type": options_of(raw, "ACCOUNT TYPE"),
                        "group_code": options_of(raw, "GROUP CODE"), "method": options_of(raw, "METHOD")}}


@router.put("/master")
def master_upsert(row: MasterRow, user: User = Depends(perm("master_list", "master_edit"))):
    name = row.WALLETNAME.strip().upper()
    if not name:
        raise HTTPException(400, "WALLETNAME is required")
    df = _master_df()
    if df.empty:
        df = pd.DataFrame(columns=AppData.MASTER_COLUMNS)
    for c in AppData.MASTER_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    mask = df["WALLETNAME"].astype(str).str.strip().str.upper().eq(name)
    if mask.any():
        idx = df.index[mask][0]
        df.at[idx, "HOURS"] = row.HOURS.strip()
        df.at[idx, "METHOD"] = row.METHOD.strip()
    else:
        rec = {c: "" for c in AppData.MASTER_COLUMNS}
        rec["WALLETNAME"] = name
        rec["HOURS"] = row.HOURS.strip()
        rec["METHOD"] = row.METHOD.strip()
        df = pd.concat([df, pd.DataFrame([rec])], ignore_index=True)
    DATA.save_master(AppData._normalise_master(df))
    try:
        LOGIC.sync_master_from_imports()
    except Exception:  # noqa: BLE001
        pass
    return {"message": f"{name} saved to Wallet Masterlist."}


@router.delete("/master/{walletname}")
def master_delete(walletname: str, user: User = Depends(perm("master_list", "master_delete"))):
    name = walletname.strip().upper()
    df = _master_df()
    DATA.save_master(df[df["WALLETNAME"].astype(str).str.upper().ne(name)].copy())
    return {"message": f"{name} deleted from Wallet Masterlist."}


@router.get("/export/master")
def export_master(q: str = "", wallet: list[str] = Query(default=[]), acct_type: list[str] = Query(default=[]),
                  group_code: list[str] = Query(default=[]), method: list[str] = Query(default=[]),
                  user: User = Depends(perm("master_list"))):
    return export_xlsx(_master_filtered(q, wallet, acct_type, group_code, method), "Wallet_Account_Master")


# ---------------------------------------------------------------- pending ---

def _pending_filtered(q, wallet):
    df = LOGIC.pending_accounts_dataframe()
    df = _contains_any(df, q)
    return _in_filter(df, "WALLET", wallet)


@router.get("/pending")
def pending_list(q: str = "", wallet: list[str] = Query(default=[]), page: int = 1, per_page: int = 25,
                 user: User = Depends(perm("pending"))):
    all_df = LOGIC.pending_accounts_dataframe()
    df = _pending_filtered(q, wallet)
    page_df, meta = paginate(df, page, per_page)
    return {**pack(page_df, []), **meta, "options": {"wallet": options_of(all_df, "WALLET")}}


class WalletIn(BaseModel):
    walletname: str = ""
    wallet: str = ""


class BulkIn(BaseModel):
    q: str = ""
    wallet: list[str] = []


@router.post("/pending/update-wallet")
def pending_update(p: WalletIn, user: User = Depends(perm("pending", "pending_edit"))):
    if not LOGIC.pending_update_wallet(p.walletname, p.wallet):
        raise HTTPException(400, "Nothing to update.")
    return {"message": f"{p.walletname.upper()} confirmed as {p.wallet.upper()} from Wallet Master List."}


@router.post("/pending/delete")
def pending_delete(p: WalletIn, user: User = Depends(perm("pending", "pending_delete"))):
    if not LOGIC.pending_delete_account(p.walletname):
        raise HTTPException(400, "Nothing to delete.")
    return {"message": f"{p.walletname.upper()} marked as Deleted and removed from Wallet Master List."}


@router.post("/pending/update-all")
def pending_update_all(p: BulkIn, user: User = Depends(perm("pending", "pending_edit"))):
    df = _pending_filtered(p.q, p.wallet)
    count = 0
    if df is not None and not df.empty:
        for _, r in df.iterrows():
            count += int(bool(LOGIC.pending_update_wallet(r.get("WALLETNAME", ""), r.get("WALLET", ""))))
    return {"message": f"{count} Pending Account(s) updated using the Wallet Master List." if count else "No Pending Accounts to update."}


@router.post("/pending/delete-all")
def pending_delete_all(p: BulkIn, user: User = Depends(perm("pending", "pending_delete"))):
    df = _pending_filtered(p.q, p.wallet)
    if df is None or df.empty:
        return {"message": "No Pending Accounts to mark as Deleted."}
    names = [str(x).strip().upper() for x in df["WALLETNAME"].tolist() if str(x).strip()]
    master = _master_df()
    DATA.save_master(master[~master["WALLETNAME"].astype(str).str.upper().isin(names)].copy())
    add = pd.DataFrame([{"WALLETNAME": n, "DECISION": "DELETED", "WALLET": ""} for n in names])
    DATA.save_pending_decisions(pd.concat([DATA.pending_decisions.copy(), add], ignore_index=True))
    return {"message": f"{len(names)} Pending Account(s) marked as Deleted."}


# ---------------------------------------------------------------- unknown ---

@router.get("/unknown")
def unknown_list(q: str = "", page: int = 1, per_page: int = 25, user: User = Depends(perm("unknown"))):
    df = LOGIC.find_unknown_accounts()
    if q and not df.empty:
        df = df[df["Wallet Account"].astype(str).str.contains(q, case=False, na=False, regex=False)]
    page_df, meta = paginate(df, page, per_page)
    return {**pack(page_df, []), **meta}


@router.post("/unknown/update")
def unknown_update(p: WalletIn, user: User = Depends(perm("unknown", "unknown_edit"))):
    w = p.wallet.strip().upper()
    if not w or not LOGIC.is_valid_wallet_identifier(w):
        raise HTTPException(400, "Not a valid wallet identifier.")
    DATA.merge_master_accounts([w])
    try:
        LOGIC.sync_master_from_imports()
    except Exception:  # noqa: BLE001
        pass
    return {"message": f"{w} added to Wallet Masterlist."}


@router.post("/unknown/update-all")
def unknown_update_all(user: User = Depends(perm("unknown", "unknown_edit"))):
    df = LOGIC.find_unknown_accounts()
    wallets = [] if df is None or df.empty else [w for w in df["Wallet Account"].astype(str).str.strip().str.upper().tolist()
                                                 if LOGIC.is_valid_wallet_identifier(w)]
    if not wallets:
        return {"message": "No unknown accounts to update."}
    DATA.merge_master_accounts(wallets)
    try:
        LOGIC.sync_master_from_imports()
    except Exception:  # noqa: BLE001
        pass
    return {"message": f"{len(wallets)} unknown account(s) added to Wallet Masterlist."}


# ----------------------------------------------------------------- closed ---

def _closed_synced() -> pd.DataFrame:
    """Wallet and Account type are always taken from the Master List (supervisor V1.62+);
    corrected values are written back to the persistent store."""
    current = DATA.dataframes.get("Permanently Closed Accounts", pd.DataFrame(columns=AppData.CLOSED_COLUMNS))
    df = DATA._autocorrect_closed_from_master(current).copy()
    if not df.equals(current):
        DATA.save_closed(df)
    return df


@router.get("/closed")
def closed_list(q: str = "", wallet: list[str] = Query(default=[]), acct_type: list[str] = Query(default=[]),
                group_code: list[str] = Query(default=[]), method: list[str] = Query(default=[]),
                page: int = 1, per_page: int = 25, user: User = Depends(perm("closed"))):
    df = _closed_synced()
    raw = df.copy()
    # Group Code / Method are resolved from the Wallet Master List by account name.
    master = AppData._normalise_master(DATA.dataframes.get("Wallet Account Master List")).copy()
    master_map = {}
    if not master.empty:
        for _, mr in master.iterrows():
            name = str(mr.get("WALLETNAME", "")).strip().upper()
            if name:
                master_map[name] = {"GROUP CODE": str(mr.get("GROUP CODE", "")).strip(),
                                    "METHOD": str(mr.get("METHOD", "")).strip()}
    keys = df["Wallet name"].astype(str).str.strip().str.upper() if not df.empty else pd.Series(dtype=str)
    df["_GROUP CODE"] = keys.map(lambda x: master_map.get(x, {}).get("GROUP CODE", "")) if not df.empty else pd.Series(dtype=str)
    df["_METHOD"] = keys.map(lambda x: master_map.get(x, {}).get("METHOD", "")) if not df.empty else pd.Series(dtype=str)
    for field, values in [("Wallet", wallet), ("Account type", acct_type), ("_GROUP CODE", group_code), ("_METHOD", method)]:
        df = _in_filter(df, field, values)
    df = _contains_any(df, q)
    if not df.empty:
        df = df.sort_values("Wallet name")
    display_df = df.drop(columns=["_GROUP CODE", "_METHOD"], errors="ignore")
    page_df, meta = paginate(display_df, page, per_page)
    return {**pack(page_df, []), **meta,
            "options": {"wallet": options_of(raw, "Wallet"), "acct_type": options_of(raw, "Account type"),
                        "group_code": sorted({v["GROUP CODE"] for v in master_map.values() if v["GROUP CODE"]}),
                        "method": sorted({v["METHOD"] for v in master_map.values() if v["METHOD"]})}}


class ClosedRow(BaseModel):
    """Add / edit: only Wallet name, Status and Remarks are manual -- Wallet and Account type
    follow the Master List."""
    wallet_name: str
    status: str = "Permanent Stop"
    remarks: str = ""


@router.put("/closed")
def closed_upsert(row: ClosedRow, user: User = Depends(perm("closed", "closed_edit"))):
    cols = AppData.CLOSED_COLUMNS
    name = row.wallet_name.strip().upper()
    if not name:
        raise HTTPException(400, "Wallet name is required")
    current = DATA.dataframes.get("Permanently Closed Accounts", pd.DataFrame(columns=cols)).copy()
    if current.empty:
        current = pd.DataFrame(columns=cols)
    for c in cols:
        if c not in current.columns:
            current[c] = ""
    current = current[cols].fillna("").copy()
    rec = {"Wallet name": name, "Wallet": "", "Status": row.status.strip() or "Permanent Stop", "Account type": "",
           "Remarks": row.remarks.strip()}
    mask = current["Wallet name"].astype(str).str.strip().str.upper().eq(name)
    if mask.any():
        idx = current.index[mask][0]
        current.at[idx, "Status"] = rec["Status"] or current.at[idx, "Status"]
        current.at[idx, "Remarks"] = rec["Remarks"]
    else:
        current = pd.concat([current, pd.DataFrame([rec])], ignore_index=True)
    DATA.save_closed(current)
    return {"message": "Permanently Closed Account saved."}


class ClosedBatchEdit(BaseModel):
    selected: list[str] = []
    status: str = ""
    account_type: str = ""
    remarks: str = ""


@router.post("/closed/batch-edit")
def closed_batch_edit(p: ClosedBatchEdit, user: User = Depends(perm("closed", "closed_edit"))):
    selected = {str(v).strip().upper() for v in p.selected if str(v).strip()}
    if not selected:
        raise HTTPException(400, "Select at least one permanently closed account.")
    current = AppData._normalise_closed(DATA.dataframes.get("Permanently Closed Accounts"))
    status, acct_type, remarks = p.status.strip(), p.account_type.strip(), p.remarks.strip()
    for idx, row in current.iterrows():
        if str(row["Wallet name"]).strip().upper() not in selected:
            continue
        if status:
            current.at[idx, "Status"] = status
        if acct_type:
            current.at[idx, "Account type"] = acct_type
        if remarks:
            current.at[idx, "Remarks"] = remarks
    DATA.save_closed(current)
    return {"message": f"{len(selected)} permanently closed account(s) updated."}


class ClosedBatchDelete(BaseModel):
    selected: list[str] = []


@router.post("/closed/batch-delete")
def closed_batch_delete(p: ClosedBatchDelete, user: User = Depends(perm("closed", "closed_delete"))):
    selected = {str(v).strip().upper() for v in p.selected if str(v).strip()}
    if not selected:
        raise HTTPException(400, "Select at least one permanently closed account.")
    current = AppData._normalise_closed(DATA.dataframes.get("Permanently Closed Accounts"))
    before = len(current)
    current = current[~current["Wallet name"].astype(str).str.strip().str.upper().isin(selected)].copy()
    DATA.save_closed(current)
    return {"message": f"{before - len(current)} permanently closed account(s) deleted."}


@router.delete("/closed/{walletname}")
def closed_delete(walletname: str, user: User = Depends(perm("closed", "closed_delete"))):
    name = walletname.strip().upper()
    current = AppData._normalise_closed(DATA.dataframes.get("Permanently Closed Accounts"))
    before = len(current)
    current = current[current["Wallet name"].astype(str).str.upper().ne(name)].copy()
    if len(current) == before:
        raise HTTPException(404, f"{name} was not found in Permanently Closed Accounts.")
    DATA.save_closed(current)
    return {"message": f"{name} deleted from Permanently Closed Accounts."}


# ----------------------------------------------------------- integrations ---

@router.get("/integrations")
def integrations_get(user: User = Depends(perm("admin_integrations"))):
    try:
        detected = INTEGRATIONS.telegram_detect_chats()
    except Exception:  # noqa: BLE001
        detected = []
    return {"config": INTEGRATIONS.config(), "detected": detected}


def _run(fn, ok_msg: str, err_prefix: str):
    try:
        res = fn()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"{err_prefix}: {exc}")
    return {"message": ok_msg.format(res=res), "result": res if isinstance(res, (str, int, list, dict)) else None}


@router.post("/integrations/google")
async def google_save(spreadsheet_id: str = Form(""), service_account: UploadFile | None = File(None),
                      user: User = Depends(perm("admin_integrations", "admin_integrations_edit"))):
    try:
        await INTEGRATIONS.save_google_config(spreadsheet_id.strip(), service_account)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Google Sheets settings error: {exc}")
    return {"message": "Google Sheets settings saved."}


@router.post("/integrations/google/test")
def google_test(user: User = Depends(perm("admin_integrations", "admin_integrations_edit"))):
    return _run(INTEGRATIONS.test_google_connection, "Google Sheets connection successful: {res}", "Google Sheets connection failed")


class TelegramIn(BaseModel):
    bot_token: str = ""
    chat_id: str = ""
    web_topic_id: str = ""


@router.post("/integrations/telegram")
def telegram_save(p: TelegramIn, user: User = Depends(perm("admin_integrations", "admin_integrations_edit"))):
    return _run(lambda: INTEGRATIONS.save_telegram_config(p.bot_token.strip(), p.chat_id.strip(), p.web_topic_id.strip()),
                "Telegram settings saved.", "Telegram settings error")


@router.post("/integrations/telegram/test")
def telegram_test(user: User = Depends(perm("admin_integrations", "admin_integrations_edit"))):
    return _run(INTEGRATIONS.telegram_test, "Telegram bot connected: {res}", "Telegram connection failed")


@router.post("/integrations/telegram/delete-webhook")
def telegram_delete_webhook(user: User = Depends(perm("admin_integrations", "admin_integrations_delete"))):
    return _run(INTEGRATIONS.telegram_delete_webhook, "Telegram webhook removed.", "Could not remove Telegram webhook")


@router.post("/integrations/telegram/detect")
def telegram_detect(user: User = Depends(perm("admin_integrations", "admin_integrations_edit"))):
    try:
        chats = INTEGRATIONS.telegram_detect_chats()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Telegram chat detection failed: {exc}")
    return {"message": f"Detected {len(chats)} chat(s)." if chats else
            "No chats detected. Send a message to the bot or add it to your group/channel, then try again.", "chats": chats}


@router.post("/integrations/telegram/install-commands")
def telegram_commands(user: User = Depends(perm("admin_integrations", "admin_integrations_edit"))):
    return _run(INTEGRATIONS.telegram_set_commands, "Telegram commands installed/refreshed.", "Telegram commands error")


class DestIn(BaseModel):
    name: str = ""
    chat_id: str = ""
    topic_id: str = ""
    chat_title: str = ""
    topic_title: str = ""
    enabled: bool = True


@router.post("/integrations/telegram/destinations")
def dest_add(p: DestIn, user: User = Depends(perm("admin_integrations", "admin_integrations_edit"))):
    return _run(lambda: INTEGRATIONS.add_telegram_destination(p.name, p.chat_id, p.topic_id, p.chat_title, p.topic_title),
                "Telegram destination registered.", "Telegram destination error")


@router.put("/integrations/telegram/destinations/{dest_id}")
def dest_edit(dest_id: str, p: DestIn, user: User = Depends(perm("admin_integrations", "admin_integrations_edit"))):
    return _run(lambda: INTEGRATIONS.update_telegram_destination(dest_id, p.name, p.chat_id, p.topic_id, p.chat_title,
                                                                 p.topic_title, p.enabled),
                "Telegram destination updated.", "Telegram destination error")


@router.delete("/integrations/telegram/destinations/{dest_id}")
def dest_delete(dest_id: str, user: User = Depends(perm("admin_integrations", "admin_integrations_delete"))):
    return _run(lambda: INTEGRATIONS.delete_telegram_destination(dest_id), "Telegram destination deleted.", "Telegram destination error")


class ReportDestIn(BaseModel):
    destination_ids: list[str] = []


@router.post("/integrations/telegram/report-destinations")
def report_destinations(p: ReportDestIn, user: User = Depends(perm("admin_integrations", "admin_integrations_edit"))):
    """Web-triggered reports go to up to 3 selected active destinations (topic ID optional)."""
    try:
        selected = INTEGRATIONS.set_report_telegram_destinations(p.destination_ids)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Telegram report destination error: {exc}")
    return {"message": f"Telegram report destinations saved: {len(selected)}/3 selected."}


@router.post("/integrations/telegram/destinations/{dest_id}/web")
def dest_web(dest_id: str, user: User = Depends(perm("admin_integrations", "admin_integrations_edit"))):
    return _run(lambda: INTEGRATIONS.set_web_telegram_destination(dest_id), "Web report Telegram destination updated.",
                "Telegram destination error")


ALLOWED_REPORTS = {"limit-utilization", "cih-agent", "cih-personal", "limit-availability", "all"}


@router.post("/telegram/send/{report_name}")
def telegram_send(report_name: str, user: User = Depends(perm("imports_telegram_reports"))):
    if report_name not in ALLOWED_REPORTS:
        raise HTTPException(404, "Unknown report")
    reports = [report_name] if report_name != "all" else ["limit-utilization", "cih-agent", "cih-personal", "limit-availability"]
    try:
        sent = INTEGRATIONS.send_reports(reports, use_web_topic=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Telegram send failed: {exc}")
    return {"message": f"Telegram sent: {sent} report(s)."}
