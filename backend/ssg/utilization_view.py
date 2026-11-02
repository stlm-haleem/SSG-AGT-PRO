"""Command Center "utilized limit" tables (Normal / VIP x Agent / eBanking / iBanking).

Fixed rules (Group codes are "contains" rules, case-insensitive; no Group filter in the UI):

  table            keyword     LIMIT (master list)                      REMAINING LIMIT + COUNTS (Limit import)          DEPOSIT (Limit import)
  agent_normal     NORMAL AG   GROUP CODE contains keyword, not "locked"  contains keyword AND "DP", not "locked", Login=Yes, Status=Active  contains keyword, not "locked", sum "Total DP"
  ebanking_normal  NORMAL EB   (same)                                   (same)                                             (same)
  ibanking_normal  NORMAL IB   ...
  agent_vip        VIP AG      ...
  ebanking_vip     VIP EB      ...
  ibanking_vip     VIP IB      ...

  "locked" = any Group code that contains "locked" (e.g. "Account Locked", "Fully Locked-No Transactions").
  LIMIT sums "MRC DP LIMIT" from the master; Remaining Limit sums "Remaining DP"; DEPOSIT sums "Total DP" (both Limit import).

On top of the Group rule (unchanged features):
* Hours filter and working-hours auto filter.  Hours (14 / 16 / 24) come from the group name (master HOURS when the
  name has none).  14H / 16H accounts count only while their window is open in Bangladesh time (UTC+6); 24H always.
* Personal tables skip accounts that reached the monthly limit.
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

from .logic_core import AppData, BusinessLogic, _XML_ESC_RE, clean_group_label

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

# Fixed Group-code rules (see module docstring).  Not user-editable and not shown in the UI.
TABLE_TOKENS = {
    "agent_normal": "NORMAL AG", "ebanking_normal": "NORMAL EB", "ibanking_normal": "NORMAL IB",
    "agent_vip": "VIP AG", "ebanking_vip": "VIP EB", "ibanking_vip": "VIP IB",
}
REMAINING_ALSO = "DP"   # Remaining Limit / Counts: Group code must also contain this
LOCKED = "locked"       # LIMIT: Group code must NOT contain this (any code containing "locked")

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


_DASHES_RE = re.compile("[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]")  # hyphen variants, en/em dash, minus


def norm_group(group) -> str:
    """Comparison key for a Group code: Excel "_x0009_" escapes decoded, dash variants unified,
    whitespace collapsed + trimmed, case-insensitive."""
    text = _XML_ESC_RE.sub(lambda m: chr(int(m.group(1), 16)), str(group if group is not None else ""))
    text = _DASHES_RE.sub("-", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def has(groups: pd.Series, token: str) -> pd.Series:
    """True where the Group code contains the token (case-insensitive, whitespace / dash variants / _x0009_ ignored)."""
    return groups.map(norm_group).str.contains(norm_group(token), regex=False)


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
        return pd.DataFrame(columns=["WALLETNAME", "WALLET", "GROUP CODE", "HOURS", "MRC DP LIMIT", "_H"])
    m = master.copy().fillna("")
    m["WALLET"] = m["WALLET"].astype(str).str.strip().str.upper()
    m["GROUP CODE"] = m["GROUP CODE"].astype(str).str.strip()
    m["HOURS"] = m["HOURS"].astype(str).map(logic._availability_canonical_hours)
    m["MRC DP LIMIT"] = m["MRC DP LIMIT"].apply(logic._number)
    m["_H"] = [hours_of(g, h) for h, g in zip(m["HOURS"], m["GROUP CODE"])]  # hours come from the group name first
    return m


def _prep_raw(logic: BusinessLogic) -> pd.DataFrame:
    """Raw Limit import: Remaining DP (Remaining Limit / Counts) and Total DP (DEPOSIT) per account."""
    cols = ["WALLET", "GROUP", "ACCOUNT", "REMAINING_DP", "TOTAL_DP", "LOGIN", "STATUS", "_H"]
    limit = logic.data.dataframes.get("Limit")
    if limit is None or limit.empty:
        return pd.DataFrame(columns=cols)
    bank, grp = logic._source_col(limit, "Bank", 0), logic._source_col(limit, "Group", 2)
    acct = logic._source_col(limit, "Account", 3)
    tdp = logic._source_col(limit, "Total DP", 7)
    rem, login, status = (logic._source_col(limit, "Remaining DP", 11), logic._source_col(limit, "Login", 13),
                          logic._source_col(limit, "Status", 14))
    if any(c is None for c in (bank, grp, acct, tdp, rem, login, status)):
        return pd.DataFrame(columns=cols)
    raw = pd.DataFrame({
        "WALLET": limit[bank].fillna("").astype(str).str.strip().str.upper(),
        "GROUP": limit[grp].map(clean_group_label),
        "ACCOUNT": limit[acct].map(lambda v: logic.clean_wallet_account(v) or str(v or "").strip()).astype(str).str.strip().str.upper(),
        "REMAINING_DP": limit[rem].apply(logic._number),
        "TOTAL_DP": limit[tdp].apply(logic._number),
        "LOGIN": limit[login].fillna("").astype(str).str.strip().str.upper(),
        "STATUS": limit[status].fillna("").astype(str).str.strip().str.upper(),
    })
    raw["_H"] = raw["GROUP"].map(lambda g: hours_of(g))
    return raw


def _fill_hours_from_master(raw: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """Limit-import rows whose group name carries no 14 / 16 / 24 take the account's hours from the master."""
    if raw.empty or master.empty:
        return raw
    hmap = (master.assign(_K=master["WALLETNAME"].astype(str).str.strip().str.upper())
            .drop_duplicates("_K").set_index("_K")["_H"])
    raw = raw.copy()
    raw["_H"] = raw["_H"].where(raw["_H"].ne(""), raw["ACCOUNT"].map(hmap).fillna(""))
    return raw


def _hours_filter_keys(selected: list[str]) -> set[str]:
    return {hours_of(s) or s for s in selected}


def build(logic: BusinessLogic, state: dict, now: datetime | None = None) -> dict:
    now = now or now_bdt()
    master = _prep_master(logic)
    raw = _fill_hours_from_master(_prep_raw(logic), master)
    # Personal accounts that reached the monthly limit are not monitored against the daily limit at all
    reached = set(logic.data.monthly_reached_names())

    def table(key: str):
        family = key.rsplit("_", 1)[0]
        token = TABLE_TOKENS[key]
        wallets = AGENT_WALLETS if family == "agent" else PERSONAL_WALLETS
        f = state["tables"][key]
        h_sel = _hours_filter_keys(f["hours"])

        def narrow(df, h_col="_H"):
            if h_sel:
                df = df[df[h_col].isin(h_sel)]
            if state["auto_enabled"] and not df.empty:
                df = df[[is_open(h, state, now) for h in df[h_col]]]
            return df

        # ---- LIMIT: master list, Group code contains the token and NOT "locked" ----
        pop = master[has(master["GROUP CODE"], token) & ~has(master["GROUP CODE"], LOCKED)]
        if family != "agent" and reached:
            pop = pop[~pop["WALLETNAME"].astype(str).str.strip().str.upper().isin(reached)]
        # kept for API compatibility only; the UI does not show a Group code filter
        options = {"group_code": sorted({g for g in pop["GROUP CODE"] if g}), "wallet": list(wallets), "hours": HOUR_OPTIONS}
        pop = narrow(pop)

        # ---- REMAINING LIMIT + COUNTS: Limit import, Group contains token AND "DP" and NOT "locked", Login = Yes, Status = Active ----
        in_group = has(raw["GROUP"], token) & ~has(raw["GROUP"], LOCKED)
        r = raw[in_group & has(raw["GROUP"], REMAINING_ALSO) & raw["LOGIN"].eq("YES") & raw["STATUS"].eq("ACTIVE")]
        if family != "agent" and reached:
            r = r[~r["ACCOUNT"].isin(reached)]
        r = narrow(r)

        # ---- DEPOSIT: Limit import, Group contains the token and NOT "locked", amount from "Total DP" ----
        d = raw[in_group]
        if family != "agent" and reached:
            d = d[~d["ACCOUNT"].isin(reached)]
        d = narrow(d)

        rows = []
        for w in wallets:
            rows.append({
                "WALLET": w,
                "LIMIT": float(pop.loc[pop["WALLET"].eq(w), "MRC DP LIMIT"].sum()),
                "Remaining Limit": float(r.loc[r["WALLET"].eq(w), "REMAINING_DP"].sum()),
                "Counts": int(r["WALLET"].eq(w).sum()),
                "DEPOSIT": float(d.loc[d["WALLET"].eq(w), "TOTAL_DP"].sum()),
            })
        df = pd.DataFrame(rows, columns=["WALLET", "LIMIT", "Remaining Limit", "Counts", "DEPOSIT"])
        total = {"WALLET": "TOTAL", "Counts": int(df["Counts"].sum())}
        for c in ("LIMIT", "Remaining Limit", "DEPOSIT"):
            total[c] = float(df[c].sum())
        return pd.concat([df, pd.DataFrame([total])], ignore_index=True), options

    tables, options = {}, {}
    for k in TABLE_KEYS:
        tables[k], options[k] = table(k)

    # chart: agent wallets, Limit and Deposit follow the current tables (Normal + VIP)
    chart = []
    for w in AGENT_WALLETS:
        chart.append({
            "wallet": w,
            "Limit": sum(float(tables[k].loc[tables[k]["WALLET"].eq(w), "LIMIT"].sum()) for k in ("agent_normal", "agent_vip")),
            "Deposit": sum(float(tables[k].loc[tables[k]["WALLET"].eq(w), "DEPOSIT"].sum()) for k in ("agent_normal", "agent_vip")),
        })

    return {"tables": tables, "options": options, "chart": chart, "info": view_info(state, now)}


def audit(logic: BusinessLogic, state: dict | None = None, now: datetime | None = None) -> dict:
    """Read-only diagnostics for the Group rules (no UI; exposed as an API endpoint).

    * unmatched_groups: Group names (Limit import and master) that contain none of the six tokens, flagged when
      they are "locked".  These are not counted anywhere.
    * overlapping_groups: Group names that match more than one table (would be double counted).
    * tables: per table, raw vs master population, so a Remaining Limit above LIMIT can be explained
      (accounts only in the Limit import, duplicate accounts, accounts above their own DP limit).
    """
    master, raw = _prep_master(logic), _prep_raw(logic)
    reached = set(logic.data.monthly_reached_names())

    def membership(groups: pd.Series) -> pd.DataFrame:
        return pd.DataFrame({k: has(groups, t) for k, t in TABLE_TOKENS.items()}, index=groups.index)

    def summarise(df, col, extra):
        if df.empty:
            return []
        mem = membership(df[col])
        n = mem.sum(axis=1)
        out = []
        for flag, sel in (("matches no table", n.eq(0)), ("matches several tables", n.gt(1))):
            bad = df[sel]
            for g, cnt in bad.groupby(col).size().sort_values(ascending=False).items():
                out.append({"issue": flag, "group": g or "(blank)", "rows": int(cnt),
                            "locked": bool(has(pd.Series([g]), LOCKED).iloc[0]), **extra(bad[bad[col].eq(g)])})
        return out

    lim_extra = lambda d: {"login_yes_active": int((d["LOGIN"].eq("YES") & d["STATUS"].eq("ACTIVE")).sum()),
                           "total_dp": float(d["TOTAL_DP"].sum())}
    mas_extra = lambda d: {"mrc_dp_limit": float(d["MRC DP LIMIT"].sum())}
    result = {"groups_to_review": {"limit": summarise(raw, "GROUP", lim_extra),
                                   "master": summarise(master, "GROUP CODE", mas_extra)},
              "tables": {}}
    master_names = set(master["WALLETNAME"].astype(str).str.strip().str.upper()) if not master.empty else set()
    mlimit = (master.assign(_K=master["WALLETNAME"].astype(str).str.strip().str.upper())
              .drop_duplicates("_K").set_index("_K")["MRC DP LIMIT"]) if not master.empty else pd.Series(dtype=float)
    for key, token in TABLE_TOKENS.items():
        family = key.rsplit("_", 1)[0]
        in_g = (has(raw["GROUP"], token) & ~has(raw["GROUP"], LOCKED)) if not raw.empty else pd.Series(dtype=bool)
        r = raw[in_g & has(raw["GROUP"], REMAINING_ALSO) & raw["LOGIN"].eq("YES") & raw["STATUS"].eq("ACTIVE")] if not raw.empty else raw
        p = master[has(master["GROUP CODE"], token) & ~has(master["GROUP CODE"], LOCKED)] if not master.empty else master
        if family != "agent" and reached:
            r, p = r[~r["ACCOUNT"].isin(reached)], p[~p["WALLETNAME"].astype(str).str.strip().str.upper().isin(reached)]
        pnames = set(p["WALLETNAME"].astype(str).str.strip().str.upper())
        dup = r["ACCOUNT"].duplicated(keep=False)
        own = r["ACCOUNT"].map(mlimit)
        over = r[own.notna() & (r["REMAINING_DP"] > own)]
        result["tables"][key] = {
            "token": token,
            "limit_rows_login_active": int(len(r)), "master_rows": int(len(p)),
            "remaining_total": float(r["REMAINING_DP"].sum()), "limit_total": float(p["MRC DP LIMIT"].sum()),
            "deposit_total_dp": float(raw.loc[in_g, "TOTAL_DP"].sum()) if not raw.empty else 0.0,
            "remaining_gt_limit": bool(r["REMAINING_DP"].sum() > p["MRC DP LIMIT"].sum()),
            "limit_accounts_not_in_this_master_group": int((~r["ACCOUNT"].isin(pnames)).sum()),
            "remaining_of_those": float(r.loc[~r["ACCOUNT"].isin(pnames), "REMAINING_DP"].sum()),
            "not_in_master_at_all": int((~r["ACCOUNT"].isin(master_names)).sum()),
            "duplicate_account_rows": int(dup.sum()), "remaining_of_duplicates": float(r.loc[dup, "REMAINING_DP"].sum()),
            "accounts_remaining_above_own_limit": int(len(over)),
            "excess_over_own_limit": float((over["REMAINING_DP"] - own[over.index]).sum()),
        }
    return result


def filter_summary(state: dict, key: str) -> str:
    f = state["tables"][key]
    parts = []
    if f["hours"]:
        parts.append("Hours: " + ", ".join(f["hours"]))
    return "; ".join(parts)
