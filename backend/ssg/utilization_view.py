"""Command Center "utilized limit" tables: Normal / VIP split, filters and working-hours auto filter.

Scope (by design): this only changes the LIMIT / Remaining Limit / Counts columns of the six
utilized-limit tables (and the Command Center chart).  The DEPOSIT column is split the same way
(by the receiving account's Normal/VIP tier, filters and working-hours rule) so Limit vs Deposit compare
like-for-like.  Withdrawal, running balance etc. are untouched.

* Tier: GROUP CODE starting with "VIP" -> VIP, everything else ("NORMAL ..." or no prefix) -> Normal.
* Working hours: 14H / 16H accounts count only while their window is open in Bangladesh time (UTC+6).
  24H accounts (and anything without a 14/16 window) always count.
* The saved view (per-table filters, windows, auto-filter on/off) is ONE shared server-side state so the
  Telegram report can send exactly what the dashboard currently shows.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .logic_core import AppData, BusinessLogic

BDT = timezone(timedelta(hours=6))  # Bangladesh has no DST

TABLE_KEYS = ["agent_normal", "ebanking_normal", "ibanking_normal", "agent_vip", "ebanking_vip", "ibanking_vip"]
TABLE_TITLES = {
    "agent_normal": "Agent accounts — utilized limit",
    "ebanking_normal": "Personal eBanking — utilized limit",
    "ibanking_normal": "Personal iBanking — utilized limit",
    "agent_vip": "Agent accounts (VIP) — utilized limit",
    "ebanking_vip": "Personal eBanking (VIP) — utilized limit",
    "ibanking_vip": "Personal iBanking (VIP) — utilized limit",
}
AGENT_WALLETS = ["BKASH", "NAGAD", "ROCKET", "UPAY"]
PERSONAL_WALLETS = ["BKASHC", "NAGADC", "ROCKETC", "UPAYC"]
HOUR_OPTIONS = ["14 Hours", "16 Hours", "24 Hours"]

DEFAULT_STATE = {
    "auto_enabled": True,
    "windows": {"14": {"start": "08:00", "end": "21:58"}, "16": {"start": "08:00", "end": "23:58"}},
    "tables": {k: {"group_code": [], "wallet": [], "hours": []} for k in TABLE_KEYS},
}

_HOURS_RE = re.compile(r"(\d{1,2})\s*-?\s*H")


def hours_of(*texts) -> str:
    """'14' / '16' / '24' ... from a Hours value or a Group code; '' when none is found."""
    for t in texts:
        m = _HOURS_RE.search(str(t or "").upper())
        if m:
            return m.group(1)
    return ""


def tier_of(group) -> str:
    return "VIP" if str(group or "").strip().upper().startswith("VIP") else "Normal"


def _minutes(hhmm: str) -> int:
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


def _valid_time(v) -> str:
    s = str(v or "").strip()
    if not re.fullmatch(r"\d{1,2}:\d{2}", s):
        raise ValueError(f"Invalid time '{v}'. Use HH:MM (24-hour).")
    h, m = s.split(":")
    if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
        raise ValueError(f"Invalid time '{v}'. Use HH:MM (24-hour).")
    return f"{int(h):02d}:{m}"


class UtilizationView:
    """Persisted shared view state (JSON file next to the other app data)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _load_unlocked(self) -> dict:
        state = json.loads(json.dumps(DEFAULT_STATE))
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return state
        if isinstance(saved.get("auto_enabled"), bool):
            state["auto_enabled"] = saved["auto_enabled"]
        for h, w in (saved.get("windows") or {}).items():
            if h in state["windows"] and isinstance(w, dict):
                try:
                    state["windows"][h] = {"start": _valid_time(w.get("start")), "end": _valid_time(w.get("end"))}
                except ValueError:
                    pass
        for k in TABLE_KEYS:
            f = (saved.get("tables") or {}).get(k) or {}
            for fld in ("group_code", "wallet", "hours"):
                if isinstance(f.get(fld), list):
                    state["tables"][k][fld] = [str(x) for x in f[fld]]
        return state

    def get(self) -> dict:
        with self._lock:
            return self._load_unlocked()

    def update(self, tables=None, auto_enabled=None, windows=None) -> dict:
        with self._lock:
            state = self._load_unlocked()
            if auto_enabled is not None:
                state["auto_enabled"] = bool(auto_enabled)
            if windows:
                for h, w in windows.items():
                    if h not in state["windows"]:
                        raise ValueError(f"Unknown working-hours window '{h}'.")
                    state["windows"][h] = {"start": _valid_time(w.get("start")), "end": _valid_time(w.get("end"))}
            if tables:
                for k, f in tables.items():
                    if k not in state["tables"]:
                        raise ValueError(f"Unknown table '{k}'.")
                    for fld in ("group_code", "wallet", "hours"):
                        if fld in f:
                            state["tables"][k][fld] = [str(x) for x in (f[fld] or [])]
            self.path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            return state


# ------------------------------------------------------------------ logic ---

def now_bdt() -> datetime:
    return datetime.now(BDT)


def is_open(hours_key: str, state: dict, now: datetime) -> bool:
    """Is an account with this working-hours value counted right now?"""
    if not state.get("auto_enabled", True):
        return True
    w = state["windows"].get(hours_key)
    if not w:  # 24H and anything else without a configured window is always open
        return True
    cur = now.hour * 60 + now.minute
    start, end = _minutes(w["start"]), _minutes(w["end"])
    return start <= cur <= end if start <= end else (cur >= start or cur <= end)


def view_info(state: dict, now: datetime) -> dict:
    gated = list(state["windows"].keys())
    open_h = [h for h in gated if is_open(h, state, now)]
    closed = [h for h in gated if not is_open(h, state, now)]
    if state["auto_enabled"]:
        counted = [f"{h}H" for h in open_h] + ["24H"]
        summary = f"Auto filter ON — counting {' + '.join(counted)} accounts" + (
            f" ({' / '.join(h + 'H' for h in closed)} closed)" if closed else "")
    else:
        summary = "Auto filter STOPPED — counting all hours"
    return {
        "auto_enabled": state["auto_enabled"],
        "windows": state["windows"],
        "now_bdt": now.strftime("%d %b %Y, %H:%M") + " BDT",
        "open_hours": open_h,
        "closed_hours": closed,
        "summary": summary,
    }


def _prep_master(logic: BusinessLogic) -> pd.DataFrame:
    logic.cih_limit_availability()  # keeps the master in sync, exactly like the CIH Limit Availability page
    master = AppData._normalise_master(logic.data.dataframes.get("Wallet Account Master List"))
    if master is None or master.empty:
        return pd.DataFrame(columns=["WALLET", "GROUP CODE", "ACCOUNT TYPE", "HOURS", "METHOD", "MRC DP LIMIT", "_H", "_TIER"])
    m = master.copy().fillna("")
    m["WALLET"] = m["WALLET"].astype(str).str.strip().str.upper()
    m["GROUP CODE"] = m["GROUP CODE"].astype(str).str.strip()
    m["ACCOUNT TYPE"] = m["ACCOUNT TYPE"].astype(str).str.strip().str.upper()
    m["HOURS"] = m["HOURS"].astype(str).map(logic._availability_canonical_hours)
    m["METHOD"] = m["METHOD"].astype(str).map(logic._availability_canonical_method)
    m["MRC DP LIMIT"] = m["MRC DP LIMIT"].apply(logic._number)
    m = m[~m["GROUP CODE"].map(logic._availability_locked_group)].copy()
    m["_H"] = [hours_of(h, g) for h, g in zip(m["HOURS"], m["GROUP CODE"])]
    m["_TIER"] = m["GROUP CODE"].map(tier_of)
    return m


def _prep_raw(logic: BusinessLogic) -> pd.DataFrame:
    cols = ["WALLET", "GROUP", "REMAINING_DP", "LOGIN", "STATUS", "_H", "_TIER"]
    limit = logic.data.dataframes.get("Limit")
    if limit is None or limit.empty:
        return pd.DataFrame(columns=cols)
    bank, grp = logic._source_col(limit, "Bank", 0), logic._source_col(limit, "Group", 2)
    rem, login, status = (logic._source_col(limit, "Remaining DP", 11), logic._source_col(limit, "Login", 13),
                          logic._source_col(limit, "Status", 14))
    if any(c is None for c in (bank, grp, rem, login, status)):
        return pd.DataFrame(columns=cols)
    raw = pd.DataFrame({
        "WALLET": limit[bank].fillna("").astype(str).str.strip().str.upper(),
        "GROUP": limit[grp].fillna("").astype(str).str.strip(),
        "REMAINING_DP": limit[rem].apply(logic._number),
        "LOGIN": limit[login].fillna("").astype(str).str.strip().str.upper(),
        "STATUS": limit[status].fillna("").astype(str).str.strip().str.upper(),
    })
    raw["_H"] = raw["GROUP"].map(lambda g: hours_of(g))
    raw["_TIER"] = raw["GROUP"].map(tier_of)
    return raw


def _prep_deposits(logic: BusinessLogic, master: pd.DataFrame) -> pd.DataFrame:
    """Successful deposits of the generated summary range, tagged with the receiving account's
    Group code / hours / tier from the master (unknown account -> Normal, hours always open)."""
    cols = ["WALLET", "DTYPE", "AMOUNT", "GROUP", "_H", "_TIER"]
    summary = logic.data.deposit_type_result
    dep = logic.data.dataframes.get("Deposit History")
    if summary is None or summary.empty or dep is None or dep.empty:
        return pd.DataFrame(columns=cols)  # Deposit stays 0 until Generate Summary, same as before
    need = {"Deposit Type", "Bank", "Amount", "Status", "Updated Time", "To Account"}
    if not need.issubset(dep.columns):
        return pd.DataFrame(columns=cols)
    fd, td = getattr(logic.data, "summary_range", (None, None))
    df = logic.filter_by_updated_time(dep.copy(), fd, td, "Updated Time")
    df = df[logic.normalize_status(df["Status"]) == "successful"]
    out = pd.DataFrame({
        "WALLET": logic.normalize_bank(df["Bank"]),
        "DTYPE": df["Deposit Type"].astype(str).str.strip().str.upper(),
        "AMOUNT": pd.to_numeric(df["Amount"], errors="coerce").fillna(0),
        "ACCT": df["To Account"].apply(logic.clean_wallet_account).fillna("").astype(str).str.strip().str.upper(),
    })
    info = master.assign(_K=master["WALLETNAME"].astype(str).str.strip().str.upper()).drop_duplicates("_K").set_index("_K")
    out["GROUP"] = out["ACCT"].map(info["GROUP CODE"]).fillna("")
    out["_H"] = out["ACCT"].map(info["_H"]).fillna("")
    out["_TIER"] = out["GROUP"].map(tier_of)  # no group code -> Normal
    return out


def _hours_filter_keys(selected: list[str]) -> set[str]:
    return {hours_of(s) or s for s in selected}


def build(logic: BusinessLogic, state: dict, now: datetime | None = None) -> dict:
    now = now or now_bdt()
    master, raw = _prep_master(logic), _prep_raw(logic)
    deps = _prep_deposits(logic, master)

    def table(key: str):
        family, tier = key.rsplit("_", 1)
        tier = "VIP" if tier == "vip" else "Normal"
        wallets = AGENT_WALLETS if family == "agent" else PERSONAL_WALLETS
        f = state["tables"][key]
        h_sel = _hours_filter_keys(f["hours"])

        # ---- master population (LIMIT) ----
        if family == "agent":
            # same buckets as the CIH Limit Availability agent table (rows with a non-standard HOURS value are not counted there)
            pop = master[~master["ACCOUNT TYPE"].map(logic._availability_type_is_personal)
                         & master["HOURS"].isin(["14 Hours", "16 Hours", "18 Hours", "24 Hours", "24-H0s INTERVAL"])]
        else:
            pop = master[master["ACCOUNT TYPE"].map(logic._availability_type_is_personal)
                         & master["METHOD"].eq(family.upper())]
        pop = pop[pop["_TIER"].eq(tier)]
        options = {
            "group_code": sorted({g for g in pop["GROUP CODE"] if g}),
            "wallet": list(wallets),
            "hours": HOUR_OPTIONS,
        }

        def narrow(df, group_col, h_col):
            if h_sel:
                df = df[df[h_col].isin(h_sel)]
            if state["auto_enabled"] and not df.empty:
                df = df[[is_open(h, state, now) for h in df[h_col]]]
            return df

        pop = narrow(pop, "GROUP CODE", "_H")

        # ---- raw Limit population (Remaining Limit / Counts) -- same qualifying rules as before ----
        r = raw[raw["_TIER"].eq(tier) & raw["LOGIN"].eq("YES") & raw["STATUS"].eq("ACTIVE")]
        g_up = r["GROUP"].astype(str).str.upper()
        if family == "agent":
            r = r[g_up.str.contains("DP", regex=False, na=False)]
        else:
            wd_only = (r"WD\s*ONLY\s*16\s*HOURS\s*-\s*IBANKING", r"WD\s*ONLY\s*16\s*HOURS\s*-\s*PERSONAL\s*EBANKING",
                       r"WD\s*ONLY\s*24\s*HOURS\s*-\s*IBANKING", r"WD\s*ONLY\s*24\s*HOURS\s*-\s*PERSONAL\s*EBANKING")
            r = r[g_up.str.contains(family.upper(), regex=False, na=False)
                  & ~g_up.str.contains("|".join(wd_only), regex=True, na=False)]
        r = narrow(r, "GROUP", "_H")

        # ---- deposits: same population rules (tier, group code, hours, auto filter) so Limit vs Deposit compare like-for-like ----
        d = deps[deps["_TIER"].eq(tier)]
        if family != "agent":
            d = d[d["DTYPE"].eq(family.upper())]
        d = narrow(d, "GROUP", "_H")

        shown = list(wallets)
        rows = []
        for w in shown:
            rows.append({
                "WALLET": w,
                "LIMIT": float(pop.loc[pop["WALLET"].eq(w), "MRC DP LIMIT"].sum()),
                "Remaining Limit": float(r.loc[r["WALLET"].eq(w), "REMAINING_DP"].sum()),
                "Counts": int(r["WALLET"].eq(w).sum()),
                "DEPOSIT": float(d.loc[d["WALLET"].eq(w), "AMOUNT"].sum()),
            })
        df = pd.DataFrame(rows, columns=["WALLET", "LIMIT", "Remaining Limit", "Counts", "DEPOSIT"])
        total = {"WALLET": "TOTAL", "Counts": int(df["Counts"].sum())}
        for c in ("LIMIT", "Remaining Limit", "DEPOSIT"):
            total[c] = float(df[c].sum())
        return pd.concat([df, pd.DataFrame([total])], ignore_index=True), options

    tables, options = {}, {}
    for k in TABLE_KEYS:
        tables[k], options[k] = table(k)

    # chart: agent wallets, Limit follows the current view (Normal + VIP), Deposit unchanged
    chart = []
    for w in AGENT_WALLETS:
        lim = sum(float(tables[k].loc[tables[k]["WALLET"].eq(w), "LIMIT"].sum()) for k in ("agent_normal", "agent_vip"))
        chart.append({"wallet": w, "Limit": lim, "Deposit": sum(float(tables[k].loc[tables[k]["WALLET"].eq(w), "DEPOSIT"].sum()) for k in ("agent_normal", "agent_vip"))})

    return {"tables": tables, "options": options, "chart": chart, "info": view_info(state, now)}


def filter_summary(state: dict, key: str) -> str:
    f = state["tables"][key]
    parts = []
    if f["hours"]:
        parts.append("Hours: " + ", ".join(f["hours"]))
    return "; ".join(parts)
