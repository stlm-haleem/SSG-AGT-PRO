import os
import re
import sys
from pathlib import Path
from datetime import date, timedelta
import pandas as pd
import warnings
warnings.filterwarnings("ignore", message="Workbook contains no default style, apply openpyxl's default")

APP_NAME = "SSG AGT"
APP_SUBTITLE = "Account Monitoring"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
WALLET_MASTER_STORE = DATA_DIR / "wallet_account_master.csv"
PERMANENTLY_CLOSED_STORE = DATA_DIR / "permanently_closed_accounts.csv"
PENDING_ACCOUNTS_STORE = DATA_DIR / "pending_accounts.csv"
MONITOR_COLUMNS = ["ACT SDP","MRC LMT","DP Bal Limit","ACCOUNTS","OPENING","DEPOSIT","WITHDRAWAL","ADJUSTMENT","R. BAL","A. BAL","DISCREP","STATUS","CODE","W. HRS","WALLET","LIMIT STATUS","ACCT TYPE","TAGS","REMARKS"]

class AppData:
    """Stores imported datasets and the persistent Wallet Account Master List."""

    MASTER_COLUMNS = [
        "WALLETNAME",
        "MRC DP LIMIT",
        "SDP PAID",
        "HOURS",
        "WALLET",
        "GROUP CODE",
        "ACCOUNT TYPE",
        "METHOD",
    ]
    CLOSED_COLUMNS = ["Wallet name", "Wallet", "Status", "Account type", "Remarks"]

    def __init__(self):
        self.files = {}
        self.dataframes = {}
        self.summary_result = pd.DataFrame()
        self.merchant_deposit_result = pd.DataFrame()
        self.merchant_payout_result = pd.DataFrame()
        self.deposit_type_result = pd.DataFrame()
        self.locked_disabled_result = pd.DataFrame()
        self.unknown_accounts = pd.DataFrame()
        self.pending_decisions = pd.DataFrame(columns=['WALLETNAME','DECISION','WALLET'])
        self.opening_sheets = {}
        self.settlement_topup_sheets = {}
        self.processing_complete = False
        # Extended Opening Balance mode is temporary and session/runtime scoped.
        # It replaces the imported Morning Balance RUNNING BALANCE with the
        # currently calculated Account Monitoring R. BAL until Revert is used.
        self.extended_opening_active = False
        self.extended_opening_map = {}
        # Revisions let the web layer cache expensive calculations and only rebuild
        # them after data actually changes.
        self.data_revision = 0
        self.master_revision = 0
        self.summary_revision = 0
        self._load_persistent_master()
        self._load_persistent_closed()
        self._load_pending_decisions()

    def _touch_data(self):
        self.data_revision += 1

    def _touch_summary(self):
        self.summary_revision += 1

    @classmethod
    def _normalise_master(cls, df):
        if df is None or df.empty:
            return pd.DataFrame(columns=cls.MASTER_COLUMNS)
        result = df.copy()
        # Backward compatibility with previous template/header.
        if "WALLETNAME" not in result.columns and "Wallet Account" in result.columns:
            result = result.rename(columns={"Wallet Account": "WALLETNAME"})
        if "SDP PAID" not in result.columns and "SDP Paid" in result.columns:
            result = result.rename(columns={"SDP Paid": "SDP PAID"})
        if "WALLETNAME" not in result.columns:
            return pd.DataFrame(columns=cls.MASTER_COLUMNS)
        for col in cls.MASTER_COLUMNS:
            if col not in result.columns:
                result[col] = ""
        result = result[cls.MASTER_COLUMNS].copy().fillna("")
        result["WALLETNAME"] = result["WALLETNAME"].astype(str).str.strip().str.upper()

        # Canonicalize Method values so case/format variants do not create
        # duplicate filter options (e.g. IBANKING / Ibanking / ibanking).
        # Known banking methods use the application's ALL-CAPS standard;
        # unknown/manual values are also stored in uppercase for consistency.
        def _normalise_method(value):
            text = str(value or "").strip()
            key = re.sub(r"[^a-z0-9]", "", text.casefold())
            if key in {"ibanking", "ibank"}:
                return "IBANKING"
            if key in {"ebanking", "ebank"}:
                return "EBANKING"
            return text.upper() if text else ""
        result["METHOD"] = result["METHOD"].map(_normalise_method)
        result = result[(result["WALLETNAME"] != "") & (result["WALLETNAME"] != "NAN")]
        result = result.drop_duplicates(subset=["WALLETNAME"], keep="last").reset_index(drop=True)
        return result

    def _load_persistent_master(self):
        # Current store plus legacy filenames used by earlier SSG AGT versions.
        # This prevents an existing master list from appearing empty after an update.
        candidates = [
            WALLET_MASTER_STORE,
            WALLET_MASTER_STORE.parent / "agent_wallet_master.csv",
            WALLET_MASTER_STORE.parent / "wallet_master.csv",
        ]
        for store in candidates:
            if not store.exists():
                continue
            try:
                raw_df = pd.read_csv(store, dtype=str, keep_default_na=False)
                df = self._normalise_master(raw_df)
                if not df.empty:
                    self.dataframes["Wallet Account Master List"] = df
                    self.files["Wallet Account Master List"] = str(store)
                    # Persist canonical Method formatting and migrate legacy stores.
                    if store != WALLET_MASTER_STORE or not raw_df.equals(df):
                        df.to_csv(WALLET_MASTER_STORE, index=False, encoding="utf-8-sig")
                    return
            except Exception:
                continue
        self.dataframes.setdefault("Wallet Account Master List", pd.DataFrame(columns=self.MASTER_COLUMNS))

    def save_master(self, df):
        df = self._normalise_master(df)
        df.to_csv(WALLET_MASTER_STORE, index=False, encoding="utf-8-sig")
        self.dataframes["Wallet Account Master List"] = df
        self.files["Wallet Account Master List"] = str(WALLET_MASTER_STORE)
        # Keep permanently closed Wallet and Account Type fields synchronized with
        # the Master List whenever the source-of-truth master is changed.
        if "Permanently Closed Accounts" in self.dataframes:
            corrected=self._autocorrect_closed_from_master(self.dataframes.get("Permanently Closed Accounts"))
            self.dataframes["Permanently Closed Accounts"]=corrected
            corrected.to_csv(PERMANENTLY_CLOSED_STORE,index=False,encoding="utf-8-sig")
        self.master_revision += 1
        return len(df)

    def merge_master_dataframe(self, incoming):
        """Merge master rows by WALLETNAME without duplicating or blanking existing details."""
        incoming = self._normalise_master(incoming)
        current = self._normalise_master(self.dataframes.get("Wallet Account Master List"))
        if current.empty:
            return self.save_master(incoming)
        existing = {row["WALLETNAME"]: row.to_dict() for _, row in current.iterrows()}
        order = current["WALLETNAME"].tolist()
        for _, row in incoming.iterrows():
            wallet = row["WALLETNAME"]
            if wallet not in existing:
                existing[wallet] = row.to_dict()
                order.append(wallet)
            else:
                # Only non-empty imported fields update the saved record.
                for col in self.MASTER_COLUMNS[1:]:
                    value = str(row[col]).strip()
                    if value and value.upper() != "NAN":
                        existing[wallet][col] = value
        merged = pd.DataFrame([existing[w] for w in order], columns=self.MASTER_COLUMNS)
        self.save_master(merged)
        return len(merged)

    def merge_master_accounts(self, wallet_accounts, sdp_paid=""):
        rows = pd.DataFrame({
            "WALLETNAME": [str(x).strip().upper() for x in wallet_accounts if str(x).strip()],
        })
        for col in self.MASTER_COLUMNS[1:]:
            rows[col] = ""
        if sdp_paid:
            rows["SDP PAID"] = sdp_paid
        self.merge_master_dataframe(rows)
        return self.dataframes.get("Wallet Account Master List", pd.DataFrame(columns=self.MASTER_COLUMNS))

    def _load_persistent_closed(self):
        if not PERMANENTLY_CLOSED_STORE.exists():
            self.dataframes.setdefault("Permanently Closed Accounts", pd.DataFrame(columns=self.CLOSED_COLUMNS))
            return
        try:
            df=pd.read_csv(PERMANENTLY_CLOSED_STORE,dtype=str,keep_default_na=False)
            corrected=self._autocorrect_closed_from_master(self._normalise_closed(df))
            self.dataframes["Permanently Closed Accounts"]=corrected
            self.files["Permanently Closed Accounts"]=str(PERMANENTLY_CLOSED_STORE)
            if not corrected.equals(self._normalise_closed(df)):
                corrected.to_csv(PERMANENTLY_CLOSED_STORE,index=False,encoding="utf-8-sig")
        except Exception:
            self.dataframes.setdefault("Permanently Closed Accounts", pd.DataFrame(columns=self.CLOSED_COLUMNS))

    @classmethod
    def _normalise_closed(cls, df):
        if df is None or df.empty:
            return pd.DataFrame(columns=cls.CLOSED_COLUMNS)
        result=df.copy().fillna("")
        aliases={"WALLETNAME":"Wallet name","WALLET NAME":"Wallet name","Wallet Account":"Wallet name","ACCOUNT TYPE":"Account type","REMARKS":"Remarks"}
        result=result.rename(columns={k:v for k,v in aliases.items() if k in result.columns and v not in result.columns})
        for c in cls.CLOSED_COLUMNS:
            if c not in result.columns: result[c]=""
        result=result[cls.CLOSED_COLUMNS].astype(str).fillna("")
        result["Wallet name"]=result["Wallet name"].str.strip().str.upper()
        result["Wallet"]=result["Wallet"].str.strip().str.upper()
        result["Status"]=result["Status"].str.strip()
        result["Account type"]=result["Account type"].str.strip()
        result["Remarks"]=result["Remarks"].str.strip()
        result=result[(result["Wallet name"]!="") & (result["Wallet name"]!="NAN")]
        return result.drop_duplicates(subset=["Wallet name"],keep="last").sort_values("Wallet name").reset_index(drop=True)

    def _autocorrect_closed_from_master(self, df):
        """Use the persistent Wallet Master List as source of truth for Wallet and Account Type.

        This path is called during page generation, so keep it vectorized. The
        previous row-by-row implementation rebuilt tens of thousands of pandas
        Series objects when the master list was large.
        """
        closed=self._normalise_closed(df)
        master=self._normalise_master(self.dataframes.get("Wallet Account Master List"))
        if closed.empty or master.empty:
            return closed

        master_lookup = master.set_index("WALLETNAME")[["WALLET", "ACCOUNT TYPE"]].copy()
        master_lookup["WALLET"] = master_lookup["WALLET"].astype(str).str.strip().str.upper()
        master_lookup["ACCOUNT TYPE"] = master_lookup["ACCOUNT TYPE"].astype(str).str.strip()

        keys = closed["Wallet name"].astype(str).str.strip().str.upper()
        mapped_wallet = keys.map(master_lookup["WALLET"])
        mapped_type = keys.map(master_lookup["ACCOUNT TYPE"])

        current_wallet = closed["Wallet"].astype(str).str.strip().str.upper()
        current_type = closed["Account type"].astype(str).str.strip()
        wallet_mask = mapped_wallet.notna() & mapped_wallet.ne("") & current_wallet.ne(mapped_wallet)
        type_mask = mapped_type.notna() & mapped_type.ne("") & current_type.ne(mapped_type)

        if not wallet_mask.any() and not type_mask.any():
            return closed

        out=closed.copy()
        out.loc[wallet_mask, "Wallet"] = mapped_wallet.loc[wallet_mask]
        out.loc[type_mask, "Account type"] = mapped_type.loc[type_mask]
        return self._normalise_closed(out)

    def save_closed(self, df):
        df=self._autocorrect_closed_from_master(self._normalise_closed(df))
        df.to_csv(PERMANENTLY_CLOSED_STORE,index=False,encoding="utf-8-sig")
        self.dataframes["Permanently Closed Accounts"]=df
        self.files["Permanently Closed Accounts"]=str(PERMANENTLY_CLOSED_STORE)
        self.master_revision += 1
        self._invalidate_cache() if hasattr(self,'_invalidate_cache') else None
        return len(df)

    def merge_closed_dataframe(self, incoming):
        incoming=self._normalise_closed(incoming)
        current=self._normalise_closed(self.dataframes.get("Permanently Closed Accounts"))
        if current.empty:
            return self.save_closed(incoming)
        existing={row["Wallet name"]: row.to_dict() for _,row in current.iterrows()}
        order=current["Wallet name"].tolist()
        for _,row in incoming.iterrows():
            wallet=row["Wallet name"]
            if wallet not in existing:
                existing[wallet]=row.to_dict(); order.append(wallet)
            else:
                for col in self.CLOSED_COLUMNS[1:]:
                    value=str(row[col]).strip()
                    if value and value.upper()!="NAN": existing[wallet][col]=value
        return self.save_closed(pd.DataFrame([existing[w] for w in order],columns=self.CLOSED_COLUMNS))

    def _load_pending_decisions(self):
        if not PENDING_ACCOUNTS_STORE.exists():
            return
        try:
            df=pd.read_csv(PENDING_ACCOUNTS_STORE,dtype=str,keep_default_na=False)
            for c in ['WALLETNAME','DECISION','WALLET']:
                if c not in df.columns: df[c]=''
            df=df[['WALLETNAME','DECISION','WALLET']].fillna('')
            df['WALLETNAME']=df['WALLETNAME'].astype(str).str.strip().str.upper()
            df['DECISION']=df['DECISION'].astype(str).str.strip().str.upper()
            df['WALLET']=df['WALLET'].astype(str).str.strip().str.upper()
            self.pending_decisions=df[df['WALLETNAME'].ne('')].drop_duplicates('WALLETNAME',keep='last').reset_index(drop=True)
        except Exception:
            self.pending_decisions=pd.DataFrame(columns=['WALLETNAME','DECISION','WALLET'])

    def save_pending_decisions(self, df):
        df=df.copy() if df is not None else pd.DataFrame(columns=['WALLETNAME','DECISION','WALLET'])
        for c in ['WALLETNAME','DECISION','WALLET']:
            if c not in df.columns: df[c]=''
        df=df[['WALLETNAME','DECISION','WALLET']].fillna('')
        df['WALLETNAME']=df['WALLETNAME'].astype(str).str.strip().str.upper()
        df['DECISION']=df['DECISION'].astype(str).str.strip().str.upper()
        df['WALLET']=df['WALLET'].astype(str).str.strip().str.upper()
        df=df[df['WALLETNAME'].ne('')].drop_duplicates('WALLETNAME',keep='last').reset_index(drop=True)
        df.to_csv(PENDING_ACCOUNTS_STORE,index=False,encoding='utf-8-sig')
        self.pending_decisions=df
        self.master_revision += 1
        return len(df)

    def set_pending_decision(self, walletname, decision, wallet=''):
        walletname=str(walletname or '').strip().upper()
        if not walletname: return
        current=self.pending_decisions.copy()
        current=current[current['WALLETNAME'].ne(walletname)]
        current=pd.concat([current,pd.DataFrame([{'WALLETNAME':walletname,'DECISION':decision,'WALLET':wallet}])],ignore_index=True)
        self.save_pending_decisions(current)

    def reset_extended_opening(self):
        """Return Opening calculations to the imported Morning Balance data."""
        self.extended_opening_active = False
        self.extended_opening_map = {}

    def clear_dataset(self, dataset_name):
        self.reset_extended_opening()
        if dataset_name == "Wallet Account Master List":
            self._load_persistent_master()
            return
        self.files.pop(dataset_name, None)
        self.dataframes.pop(dataset_name, None)
        if dataset_name == "Opening":
            self.opening_sheets = {}
        if dataset_name == "Settlement / Top up":
            self.settlement_topup_sheets = {}
        self._touch_data()

    def load_file(self, dataset_name, file_path):
        # New imports represent the new current data; any prior extension is stale.
        self.reset_extended_opening()
        extension = Path(file_path).suffix.lower()
        try:
            if dataset_name == "Settlement / Top up":
                if extension == ".csv":
                    raise ValueError("Settlement / Top up requires an Excel workbook (.xlsx or .xls) because it contains two sheets.")
                if extension == ".xls":
                    sheets = pd.read_excel(file_path, sheet_name=None, engine="xlrd", dtype=str)
                elif extension == ".xlsx":
                    sheets = pd.read_excel(file_path, sheet_name=None, engine="openpyxl", dtype=str)
                else:
                    raise ValueError("Unsupported file format. Settlement / Top up requires Excel (.xlsx/.xls).")
                required = ["Settlement", "Top up"]
                missing = [name for name in required if name not in sheets]
                if missing:
                    raise ValueError("Settlement / Top up workbook is missing sheet(s): " + ", ".join(missing))
                self.settlement_topup_sheets = {name: sheets[name].fillna("") for name in required}
                self.files[dataset_name] = file_path
                self.dataframes[dataset_name] = self.settlement_topup_sheets["Settlement"]
                self._touch_data()
                return True, sum(len(df) for df in self.settlement_topup_sheets.values())

            if dataset_name == "Opening":
                if extension == ".csv":
                    raise ValueError("Opening requires an Excel workbook (.xlsx or .xls) because it contains three sheets.")
                if extension == ".xls":
                    sheets = pd.read_excel(file_path, sheet_name=None, engine="xlrd", dtype=str)
                elif extension == ".xlsx":
                    sheets = pd.read_excel(file_path, sheet_name=None, engine="openpyxl", dtype=str)
                else:
                    raise ValueError("Unsupported file format. Opening requires Excel (.xlsx/.xls).")
                required = ["Morning Balance", "Merchant Balance", "Wallet Balances"]
                missing = [name for name in required if name not in sheets]
                if missing:
                    raise ValueError("Opening workbook is missing sheet(s): " + ", ".join(missing))
                self.opening_sheets = {name: sheets[name].fillna("") for name in required}
                # Keep the first sheet in the generic dataframe store for compatibility;
                # all three sheets are available in self.opening_sheets for future logic.
                self.files[dataset_name] = file_path
                self.dataframes[dataset_name] = self.opening_sheets["Morning Balance"]
                self._touch_data()
                return True, sum(len(df) for df in self.opening_sheets.values())

            if extension == ".csv":
                df = pd.read_csv(file_path, dtype=str)
            elif extension == ".xls":
                df = pd.read_excel(file_path, engine="xlrd", dtype=str)
            elif extension == ".xlsx":
                df = pd.read_excel(file_path, engine="openpyxl", dtype=str)
            else:
                raise ValueError("Unsupported file format. Please use CSV or Excel (.xlsx/.xls).")

            if dataset_name == "Wallet Account Master List":
                if "WALLETNAME" not in df.columns and "Wallet Account" not in df.columns:
                    raise ValueError('Wallet Account Master List must contain a "WALLETNAME" column.')
                count = self.merge_master_dataframe(df)
                return True, count

            self.files[dataset_name] = file_path
            self.dataframes[dataset_name] = df
            self._touch_data()
            return True, len(df)
        except Exception as e:
            return False, str(e)

    def export_master_template(self, file_path):
        pd.DataFrame(columns=self.MASTER_COLUMNS).to_excel(file_path, index=False, engine="openpyxl")
        return file_path

    def export_opening_template(self, file_path):
        morning_columns = ["SHOP", "SDP", "RUNNING BALANCE"]
        merchant_columns = [
            "MERCHANT", "OPENING BALANCE", "DEPOSIT", "WITHDRAWAL", "TOP UP",
            "Special Payment", "SETTLEMENT", "INTERNAL TRANSFER IN",
            "INTERNAL TRANSFER OUT", "Company Commission", "Wallet Commission",
            "Adjustment", "ENDING BALANCE"
        ]
        wallet_columns = ["WALLET", "AMOUNT"]
        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            pd.DataFrame(columns=morning_columns).to_excel(writer, sheet_name="Morning Balance", index=False)
            pd.DataFrame(columns=merchant_columns).to_excel(writer, sheet_name="Merchant Balance", index=False)
            pd.DataFrame(columns=wallet_columns).to_excel(writer, sheet_name="Wallet Balances", index=False)
        return file_path

    def export_settlement_topup_template(self, file_path):
        settlement_columns = [
            "Agent", "Brand", "Amount", "Fee", "Remarks", "MC",
            "PURPOSE", "WALLET", "DATE"
        ]
        topup_columns = [
            "DATE", "BRAND", "FROM", "Remarks", "MC", "TYPE",
            "TO AGENT", "BRAND", "WALLET", "AMOUNT PROCESS", "FEE",
            "REMARKS", "UPDATED BY:", "STATUS", "CHECKER"
        ]
        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            pd.DataFrame(columns=settlement_columns).to_excel(
                writer, sheet_name="Settlement", index=False
            )
            pd.DataFrame(columns=topup_columns).to_excel(
                writer, sheet_name="Top up", index=False
            )
        return file_path


class BusinessLogic:
    """
    Business logic for SSG AGT.

    Source files:

    Deposit History
        C = Merchant Code
        H = Bank
        J = To Account
        K = Amount
        P = Updated Time
        R = Status
        B = Deposit Type

    Pay Out History
        B = Merchant
        J = Bank
        K = From Account
        M = Amount
        S = Updated Time
        U = Status

    Account Statement
        D = Amount
        K = Updated Time
        L = Channel
        Account column = Wallet Account source for B2B rows
    """

    DEPOSIT_BANKS = [
        "BKASH",
        "BKASHC",
        "IBBL",
        "NAGAD",
        "NAGADC",
        "ROCKET",
        "ROCKETC",
        "UPAY",
        "UPAYC",
    ]

    PAYOUT_BANKS = [
        "BKASH",
        "BKASHC",
        "NAGAD",
        "NAGADC",
        "ROCKET",
        "ROCKETC",
        "UPAY",
        "UPAYC",
    ]

    B2B_CHANNELS = {
        "B2B",
        "B2B RECEIVE",
        "B2B SEND",
        "B2B_TRANSFER",
        "CI",
        "CO",
    }

    def __init__(self, app_data):
        self.data = app_data
        self._cache = {}

    def _token(self):
        # Operational calculation caches only depend on imported/master data.
        # A Generate Summary action updates summary_revision but does not change
        # the source data, so it should not force expensive monitoring/CIH
        # calculations to rebuild on the next page request.
        return (self.data.data_revision, self.data.master_revision)

    def _cached(self, key):
        item = self._cache.get(key)
        return item[1] if item and item[0] == self._token() else None

    def _store_cache(self, key, value):
        self._cache[key] = (self._token(), value)
        return value

    # ========================================================
    # GENERAL HELPERS
    # ========================================================

    @staticmethod
    def clean_wallet_account(value):
        """
        Extract only a valid wallet identifier.

        Normal source format:
            01318070782 - BNB-NG-013

        Output:
            BNB-NG-013

        If Account Statement already contains the wallet identifier itself,
        that value is also accepted. Ordinary names are rejected.
        """
        if pd.isna(value):
            return None
        value = str(value).strip().upper()

        if BusinessLogic.is_valid_wallet_identifier(value):
            return value

        if " - " not in value:
            return None

        wallet = value.rsplit(" - ", 1)[1].strip()
        if not BusinessLogic.is_valid_wallet_identifier(wallet):
            return None
        return wallet

    @staticmethod
    def extract_statement_wallet_account(value):
        """Extract the wallet name from Account Statement Column B.

        Source format:
            HORSE-NG-040 (01345214060)

        Output:
            HORSE-NG-040
        """
        if pd.isna(value):
            return None
        value = str(value).strip().upper()
        match = re.match(r"^([A-Z0-9]+-[A-Z]{2,}-[0-9]{2,})\s*\(", value)
        if match and BusinessLogic.is_valid_wallet_identifier(match.group(1)):
            return match.group(1)
        return None

    @staticmethod
    def normalize_status(series):
        return (
            series
            .astype(str)
            .str.strip()
            .str.lower()
        )

    @staticmethod
    def normalize_bank(series):
        return (
            series
            .astype(str)
            .str.strip()
            .str.upper()
        )

    @staticmethod
    def normalize_channel(series):
        # Normalize channel names without changing their meaning.
        # This handles values such as "B2B Receive", "b2b_transfer",
        # accidental surrounding spaces, and inconsistent capitalization.
        return (
            series
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            .str.replace(r"\s+", " ", regex=True)
        )

    @staticmethod
    def is_valid_wallet_identifier(value):
        if pd.isna(value):
            return False
        value = str(value).strip().upper()
        return bool(re.fullmatch(r"[A-Z0-9]+-[A-Z]{2,}-[0-9]{2,}", value))

    def filter_by_updated_time(
        self,
        df,
        from_date,
        to_date,
        date_column="Updated Time"
    ):
        """
        Filter using the specified Updated Time column.
        """

        if df is None or df.empty:
            return df

        result = df.copy()

        if date_column not in result.columns:
            return result

        result["_ProcessingDate"] = pd.to_datetime(
            result[date_column],
            errors="coerce"
        ).dt.date

        if from_date is not None:
            result = result[
                result["_ProcessingDate"] >= from_date
            ]

        if to_date is not None:
            result = result[
                result["_ProcessingDate"] <= to_date
            ]

        result = result.drop(
            columns=["_ProcessingDate"],
            errors="ignore"
        )

        return result

    # ========================================================
    # ACCOUNT MONITORING LOGIC
    # ========================================================

    @staticmethod
    def _source_col(df, name, position=None):
        if df is None:
            return None
        if name in df.columns:
            return name
        if position is not None and len(df.columns) > position:
            return df.columns[position]
        return None

    @staticmethod
    def _number(value):
        if value is None or pd.isna(value):
            return 0.0
        text = str(value).strip().replace(",", "")
        if text == "":
            return 0.0
        number = pd.to_numeric(text, errors="coerce")
        if pd.isna(number):
            return 0.0
        return float(number)

    def _limit_dataframe_uncached(self):
        source = self.data.dataframes.get("Limit")
        if source is None or source.empty:
            return pd.DataFrame(columns=["WALLETNAME", "MRC DP LIMIT", "A. BAL", "STATUS", "CODE", "WALLET", "GROUP CODE", "LIMIT STATUS"])
        account_col = self._source_col(source, "Account", 3)
        dp_col = self._source_col(source, "DP Limit", 6)
        balance_col = self._source_col(source, "Balance", 4)
        login_col = self._source_col(source, "Login", 13)
        group_col = self._source_col(source, "Group", 2)
        bank_col = self._source_col(source, "Bank", 0)
        limit_status_col = self._source_col(source, "Status", 14)
        if account_col is None:
            return pd.DataFrame(columns=["WALLETNAME", "MRC DP LIMIT", "A. BAL", "STATUS", "CODE", "WALLET", "GROUP CODE", "LIMIT STATUS"])
        out = pd.DataFrame()
        out["WALLETNAME"] = source[account_col].apply(self.clean_wallet_account)
        out["MRC DP LIMIT"] = source[dp_col].apply(self._number) if dp_col else 0.0
        out["A. BAL"] = source[balance_col].apply(self._number) if balance_col else 0.0
        login = source[login_col].astype(str).str.strip().str.lower() if login_col else pd.Series("", index=source.index)
        out["STATUS"] = login.map({"yes": "🟢 Log In", "no": "🔴 Log Out"}).fillna("")
        out["CODE"] = source[group_col].fillna("").astype(str).str.strip() if group_col else ""
        out["GROUP CODE"] = out["CODE"]
        out["WALLET"] = source[bank_col].fillna("").astype(str).str.strip().str.upper() if bank_col else ""
        out["LIMIT STATUS"] = source[limit_status_col].fillna("").astype(str).str.strip() if limit_status_col else ""
        out["LIMIT STATUS"] = out["LIMIT STATUS"].where(out["LIMIT STATUS"].astype(str).str.strip().ne(""), "Locked")
        out = out[out["WALLETNAME"].notna()].copy()
        out = out[out["WALLETNAME"].astype(str).str.strip().ne("")]
        return out.groupby("WALLETNAME", as_index=False).agg({
            "MRC DP LIMIT": "last", "A. BAL": "last", "STATUS": "last", "CODE": "last", "WALLET": "last", "GROUP CODE": "last", "LIMIT STATUS": "last"
        })

    def _limit_dataframe(self):
        cached = self._cached('limit')
        if cached is not None:
            return cached.copy()
        return self._store_cache('limit', self._limit_dataframe_uncached())

    def _opening_dataframe_uncached(self):
        source = self.data.opening_sheets.get("Morning Balance") if self.data.opening_sheets else None
        if source is None or source.empty:
            out = pd.DataFrame(columns=["WALLETNAME", "OPENING", "SDP PAID"])
        else:
            shop_col = self._source_col(source, "SHOP", 0)
            sdp_col = self._source_col(source, "SDP", 1)
            running_col = self._source_col(source, "RUNNING BALANCE", 2)
            if shop_col is None:
                out = pd.DataFrame(columns=["WALLETNAME", "OPENING", "SDP PAID"])
            else:
                out = pd.DataFrame()
                out["WALLETNAME"] = source[shop_col].apply(self.clean_wallet_account)
                out["OPENING"] = source[running_col].apply(self._number) if running_col else 0.0
                out["SDP PAID"] = source[sdp_col].apply(self._number) if sdp_col else 0.0
                out = out[out["WALLETNAME"].notna()].copy()
                out = out.groupby("WALLETNAME", as_index=False).agg({"OPENING": "last", "SDP PAID": "last"})

        # Extended mode replaces the effective opening with the R. BAL snapshot
        # captured when the user pressed "Extended Running balance".  Do this
        # after importing/normalising the workbook so the snapshot always wins.
        if getattr(self.data, "extended_opening_active", False):
            ext_map = getattr(self.data, "extended_opening_map", {}) or {}
            if ext_map:
                if out.empty:
                    out = pd.DataFrame({
                        "WALLETNAME": list(ext_map.keys()),
                        "OPENING": list(ext_map.values()),
                        "SDP PAID": [0.0] * len(ext_map),
                    })
                else:
                    out["WALLETNAME"] = out["WALLETNAME"].astype(str).str.strip().str.upper()
                    out["OPENING"] = out["WALLETNAME"].map(ext_map).fillna(out["OPENING"])
                    # Include monitored accounts that were not present in the
                    # Morning Balance import, so every account gets its snapshot.
                    existing = set(out["WALLETNAME"].astype(str).str.strip().str.upper())
                    missing = [(acct, value) for acct, value in ext_map.items() if acct not in existing]
                    if missing:
                        out = pd.concat([
                            out,
                            pd.DataFrame({
                                "WALLETNAME": [a for a, _ in missing],
                                "OPENING": [v for _, v in missing],
                                "SDP PAID": [0.0] * len(missing),
                            }),
                        ], ignore_index=True)
        return out

    def extend_opening_balance(self):
        """Use the current R. BAL of every monitored account as its next Opening.

        The snapshot is captured BEFORE enabling extended mode. This is important:
        otherwise R. BAL would be recalculated from the already-replaced Opening.
        The imported Morning Balance workbook is never modified.
        """
        if getattr(self.data, "extended_opening_active", False):
            return len(getattr(self.data, "extended_opening_map", {}) or {})

        self._cache.clear()
        current = self.build_account_monitoring_dataframe_uncached()
        if current is None or current.empty:
            return 0

        mapping = {}
        for _, row in current.iterrows():
            account = str(row.get("ACCOUNTS", "")).strip().upper()
            if not account:
                continue
            value = pd.to_numeric(row.get("R. BAL", 0), errors="coerce")
            if pd.isna(value):
                value = 0.0
            mapping[account] = float(value)

        if not mapping:
            return 0

        self.data.extended_opening_map = mapping
        self.data.extended_opening_active = True
        self._cache.clear()
        self.data._touch_data()
        return len(mapping)

    def revert_opening_balance(self):
        active = bool(getattr(self.data, "extended_opening_active", False))
        self.data.reset_extended_opening()
        self._cache.clear()
        self.data._touch_data()
        return active

    def _opening_dataframe(self):
        cached = self._cached('opening')
        if cached is not None:
            return cached.copy()
        return self._store_cache('opening', self._opening_dataframe_uncached())

    def _adjustment_dataframe(self):
        cached = self._cached('adjustment')
        if cached is not None:
            return cached.copy()

        settlement = self.data.settlement_topup_sheets.get("Settlement") if self.data.settlement_topup_sheets else None
        topup = self.data.settlement_topup_sheets.get("Top up") if self.data.settlement_topup_sheets else None

        settlement_sum = {}
        if settlement is not None and not settlement.empty:
            agent_col = self._source_col(settlement, "Agent", 0)
            amount_col = self._source_col(settlement, "Amount", 2)
            fee_col = self._source_col(settlement, "Fee", 3)
            if agent_col:
                w = settlement[agent_col].map(self.clean_wallet_account)
                amounts = pd.to_numeric(settlement[amount_col].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0) if amount_col else 0.0
                fees = pd.to_numeric(settlement[fee_col].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0) if fee_col else 0.0
                temp = pd.DataFrame({"WALLETNAME": w, "TOTAL": amounts + fees})
                temp = temp[temp["WALLETNAME"].notna()]
                if not temp.empty:
                    settlement_sum = temp.groupby("WALLETNAME")["TOTAL"].sum().to_dict()

        topup_sum = {}
        if topup is not None and not topup.empty:
            from_col = self._source_col(topup, "FROM", 2)
            to_col = self._source_col(topup, "TO AGENT", 6)
            amount_col = self._source_col(topup, "AMOUNT PROCESS", 9)
            fee_col = self._source_col(topup, "FEE", 10)
            total = 0.0
            if amount_col:
                total = pd.to_numeric(topup[amount_col].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0)
            if fee_col:
                total = total + pd.to_numeric(topup[fee_col].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0)
            if not isinstance(total, pd.Series):
                total = pd.Series(total, index=topup.index, dtype=float)
            if to_col:
                to_wallet = topup[to_col].map(self.clean_wallet_account)
                temp = pd.DataFrame({"WALLETNAME": to_wallet, "TOTAL": total})
                temp = temp[temp["WALLETNAME"].notna()]
                if not temp.empty:
                    vals = temp.groupby("WALLETNAME")["TOTAL"].sum()
                    for k, v in vals.items(): topup_sum[k] = topup_sum.get(k, 0.0) + float(v)
            if from_col:
                from_wallet = topup[from_col].map(self.clean_wallet_account)
                temp = pd.DataFrame({"WALLETNAME": from_wallet, "TOTAL": -total})
                temp = temp[temp["WALLETNAME"].notna()]
                if not temp.empty:
                    vals = temp.groupby("WALLETNAME")["TOTAL"].sum()
                    for k, v in vals.items(): topup_sum[k] = topup_sum.get(k, 0.0) + float(v)

        keys = sorted(set(settlement_sum) | set(topup_sum))
        result = pd.DataFrame({"WALLETNAME": keys, "ADJUSTMENT": [topup_sum.get(k, 0.0) - settlement_sum.get(k, 0.0) for k in keys]})
        return self._store_cache('adjustment', result)

    def _permanent_closed_tags(self):
        cached = self._cached('closed_tags')
        if cached is not None:
            return cached
        if not PERMANENTLY_CLOSED_STORE.exists():
            return self._store_cache('closed_tags', {})
            return self._store_cache('closed_tags', {})
        try:
            df = self.data.dataframes.get('Permanently Closed Accounts', pd.DataFrame()).copy()
            if df is None or df.empty:
                df = pd.read_csv(PERMANENTLY_CLOSED_STORE, dtype=str, keep_default_na=False)
            df = self.data._autocorrect_closed_from_master(df)
        except Exception:
            return self._store_cache('closed_tags', {})
        if df.empty or "Wallet name" not in df.columns:
            return self._store_cache('closed_tags', {})
        tags = {}
        for _, row in df.iterrows():
            wallet = str(row.get("Wallet name", "")).strip().upper()
            status = str(row.get("Status", "")).strip()
            if wallet and status:
                tags[wallet] = status
        return self._store_cache('closed_tags', tags)

    def _remarks_map(self):
        """Return monitoring remarks using status-priority order.

        Remarks are now resolved per account using this priority:
        Active -> Disabled -> Locked.  Once an account exists in Active,
        its Active remark is the only remark used even if the same account
        also appears in Disabled or Locked.
        """
        cached = self._cached('remarks')
        if cached is not None:
            return cached

        source = self.data.locked_disabled_result
        if source is None or source.empty:
            try:
                source = self.generate_locked_disabled_result()
            except Exception:
                source = pd.DataFrame()
        if source.empty or "Account Name" not in source.columns:
            return self._store_cache('remarks', {})

        # Build one map per canonical status, then merge in the required
        # priority order. Blank remarks are still considered a valid source
        # when the account is present in that status.
        by_status = {'Active': {}, 'Disabled': {}, 'Locked': {}}
        for _, row in source.iterrows():
            wallet = str(row.get("Account Name", "")).strip().upper()
            if not wallet:
                continue
            status = str(row.get("Status", "")).strip().title()
            if status not in by_status:
                continue
            by_status[status][wallet] = str(row.get("Remarks", "") or "").strip()

        result = {}
        for status in ('Locked', 'Disabled', 'Active'):
            # Lower-priority entries are filled first; higher-priority entries
            # overwrite them. Final priority is therefore Active > Disabled > Locked.
            for wallet, remark in by_status[status].items():
                result[wallet] = remark
        return self._store_cache('remarks', result)

    def _imported_wallet_map(self, dataset_name):
        """Return WALLETNAME -> Bank/Wallet from Limit or account-status imports."""
        source=self.data.dataframes.get(dataset_name)
        if source is None or source.empty:
            return {}, False
        try:
            if dataset_name == 'Limit':
                df=self._limit_dataframe()
                return ({str(r['WALLETNAME']).strip().upper(): str(r['WALLET']).strip().upper()
                         for _,r in df.iterrows()
                         if str(r.get('WALLETNAME','')).strip() and str(r.get('WALLET','')).strip()}, True)
            # Active/Locked/Disabled: Excel E=Bank Code, F=Account Name fallback.
            account_col=self._source_col(source,'Account Name',5)
            bank_col=self._source_col(source,'Bank Code',4)
            if account_col is None or bank_col is None:
                return {}, True
            mapping={}
            for acct,bank in zip(source[account_col],source[bank_col]):
                wallet=self.clean_wallet_account(acct)
                b=str(bank or '').strip().upper()
                if wallet and b:
                    mapping[str(wallet).strip().upper()]=b
            return mapping, True
        except Exception:
            return {}, True

    def _imported_dp_limit_map(self, dataset_name):
        source=self.data.dataframes.get(dataset_name)
        if source is None or source.empty: return {}
        account_col=self._source_col(source,'Account Name',5)
        dp_col=self._source_col(source,'Max DP Daily Limit',None)
        if dp_col is None:
            for c in source.columns:
                norm=re.sub(r'[^a-z0-9]','',str(c).lower())
                if 'maxdpdailylimit' in norm or ('dp' in norm and 'limit' in norm and 'max' in norm): dp_col=c; break
        if account_col is None or dp_col is None: return {}
        out={}
        for acct,val in zip(source[account_col],source[dp_col]):
            w=self.clean_wallet_account(acct); text=str(val).strip().replace(',','') if val is not None else ''
            if w and text and text.upper() not in {'NAN','NONE','NULL'}:
                try: out[str(w).upper()]=float(text)
                except Exception: pass
        return out

    def pending_accounts_dataframe(self):
        """Master accounts not found in any of the four current operational sources.
        The current persistent Master List wallet is presented as the fallback wallet.
        Resolved KEEP/DELETE decisions suppress repeated pending entries.
        """
        master=AppData._normalise_master(self.data.dataframes.get('Wallet Account Master List'))
        if master.empty:
            return pd.DataFrame(columns=['WALLETNAME','WALLET','ACTION'])
        sources=[self._imported_wallet_map('Limit')[1],
                 self._imported_wallet_map('Active Accounts')[1],
                 self._imported_wallet_map('Locked Accounts')[1],
                 self._imported_wallet_map('Disabled Accounts')[1]]
        if not all(sources):
            return pd.DataFrame(columns=['WALLETNAME','WALLET','ACTION'])
        maps=[self._imported_wallet_map(name)[0] for name in ['Limit','Active Accounts','Locked Accounts','Disabled Accounts']]
        found=set()
        for m in maps: found.update(m.keys())
        resolved=set(self.data.pending_decisions.loc[
            self.data.pending_decisions['DECISION'].isin(['KEEP','DELETED']), 'WALLETNAME'
        ].astype(str).str.upper().tolist()) if not self.data.pending_decisions.empty else set()
        rows=[]
        for _,r in master.iterrows():
            name=str(r['WALLETNAME']).strip().upper()
            if name and name not in found and name not in resolved:
                rows.append({'WALLETNAME':name,'WALLET':str(r.get('WALLET','')).strip().upper(),'ACTION':str(r.get('WALLET','')).strip().upper()})
        return pd.DataFrame(rows,columns=['WALLETNAME','WALLET','ACTION']).sort_values('WALLETNAME').reset_index(drop=True) if rows else pd.DataFrame(columns=['WALLETNAME','WALLET','ACTION'])

    def pending_update_wallet(self, walletname, wallet):
        walletname=str(walletname or '').strip().upper(); wallet=str(wallet or '').strip().upper()
        if not walletname: return False
        master=AppData._normalise_master(self.data.dataframes.get('Wallet Account Master List'))
        if master.empty: return False
        mask=master['WALLETNAME'].eq(walletname)
        if not mask.any(): return False
        if wallet:
            master.loc[mask,'WALLET']=wallet
        self.data.save_master(master)
        self.data.set_pending_decision(walletname,'KEEP',wallet)
        return True

    def pending_delete_account(self, walletname):
        walletname=str(walletname or '').strip().upper()
        master=AppData._normalise_master(self.data.dataframes.get('Wallet Account Master List'))
        if master.empty: return False
        master=master[~master['WALLETNAME'].eq(walletname)].copy()
        self.data.save_master(master)
        self.data.set_pending_decision(walletname,'DELETED','')
        return True

    def sync_master_from_imports(self):
        current = AppData._normalise_master(self.data.dataframes.get("Wallet Account Master List"))
        if current.empty:
            return current

        updated = current.copy()
        opening = self._opening_dataframe()
        limits = self._limit_dataframe()
        if not opening.empty:
            sdp_map = opening.set_index("WALLETNAME")["SDP PAID"].to_dict()
            mapped=updated["WALLETNAME"].map(sdp_map)
            updated["SDP PAID"] = mapped.where(mapped.notna(), updated["SDP PAID"])
        # MRC DP LIMIT priority: LIMIT DP Limit -> Active/Disabled/Locked Max DP Daily Limit -> Master List.
        if not limits.empty:
            lim_map = limits.set_index("WALLETNAME")["MRC DP LIMIT"].to_dict()
            mapped=updated["WALLETNAME"].map(lim_map)
            updated["MRC DP LIMIT"] = mapped.where(mapped.notna() & mapped.ne(0), updated["MRC DP LIMIT"])
            group_map = limits.set_index("WALLETNAME")["GROUP CODE"].to_dict()
            g=updated["WALLETNAME"].map(group_map).fillna("").astype(str).str.strip()
            updated["GROUP CODE"] = g.where(g.ne(""), "Locked Account")
        for source_name in ['Active Accounts','Disabled Accounts','Locked Accounts']:
            mp=self._imported_dp_limit_map(source_name)
            if not mp: continue
            for idx,name in updated['WALLETNAME'].items():
                existing=str(updated.at[idx,'MRC DP LIMIT']).strip()
                if existing in {'','nan','None','0','0.0'} and str(name).upper() in mp:
                    updated.at[idx,'MRC DP LIMIT']=mp[str(name).upper()]

        # Wallet priority: LIMIT Bank first, then Active, Disabled, Locked Bank Code,
        # and finally the Wallet value already stored in the imported Master List.
        source_maps=[]
        for name in ['Limit','Active Accounts','Disabled Accounts','Locked Accounts']:
            source_maps.append(self._imported_wallet_map(name)[0])
        def priority_wallet(name, fallback):
            key=str(name).strip().upper()
            for mp in source_maps:
                val=str(mp.get(key,'')).strip().upper()
                if val:
                    return val
            return str(fallback or '').strip().upper()
        updated['WALLET']=[priority_wallet(n,w) for n,w in zip(updated['WALLETNAME'],updated['WALLET'])]

        # ACCOUNT TYPE is automatic for blank records. Keep any existing
        # explicit classification (VIP / Withdrawal only, etc.), while using
        # the wallet family as the fallback: C-suffixed wallets are Personal;
        # standard wallet codes are Agent.
        personal_wallets={'BKASHC','NAGADC','ROCKETC','UPAYC'}
        inferred_types=updated['WALLET'].astype(str).str.strip().str.upper().map(
            lambda w: 'PERSONAL' if w in personal_wallets else ('AGENT' if w else '')
        )
        existing_types=updated['ACCOUNT TYPE'].astype(str).str.strip()
        updated['ACCOUNT TYPE']=existing_types.where(existing_types.ne(''), inferred_types)

        # Method and Hours can be inferred from GROUP CODE. Explicit/manual
        # values are preserved when the group code contains no usable rule.
        def infer_method_from_group(value):
            text=str(value or '').strip().upper()
            if 'IBANKING' in text or 'IBANK' in text:
                return 'IBANKING'
            if 'EBANKING' in text or 'EBANK' in text:
                return 'EBANKING'
            return ''

        def infer_hours_from_group(value):
            text=str(value or '').strip().upper()
            compact=re.sub(r'\s+', '', text)
            if re.search(r'(?<!\d)14(?:H|HOURS)(?![A-Z0-9])', compact):
                return '14 Hours'
            if re.search(r'(?<!\d)16(?:H|HOURS)(?![A-Z0-9])', compact):
                return '16 Hours'
            if re.search(r'(?<!\d)18(?:H|HOURS)(?![A-Z0-9])', compact):
                return '18 Hours'
            if '24H-0S' in compact or '24H0S' in compact or '24H-0' in compact:
                return '24H-0s Interval'
            if re.search(r'(?<!\d)24(?:H|HOURS)(?![A-Z0-9])', compact):
                return '24 Hours'
            return ''

        inferred_methods=updated['GROUP CODE'].map(infer_method_from_group)
        inferred_hours=updated['GROUP CODE'].map(infer_hours_from_group)
        existing_methods=updated['METHOD'].astype(str).str.strip()
        existing_hours=updated['HOURS'].astype(str).str.strip()
        updated['METHOD']=inferred_methods.where(inferred_methods.ne(''), existing_methods)
        updated['HOURS']=inferred_hours.where(inferred_hours.ne(''), existing_hours)

        # Only persist if something actually changed.
        if not updated.equals(current):
            self.data.save_master(updated)
        else:
            self.data.dataframes['Wallet Account Master List']=updated
        return updated

    def build_account_monitoring_dataframe_uncached(self):
        master = self.sync_master_from_imports()
        if master is None or master.empty:
            return pd.DataFrame(columns=MONITOR_COLUMNS + ["_TYPE","_PERMANENT_STOP"])
        master = AppData._normalise_master(master).copy().fillna("")
        limits = self._limit_dataframe()
        opening = self._opening_dataframe()
        adjustment = self._adjustment_dataframe()

        # Account Monitoring must reflect the currently imported Deposit History
        # and Pay Out History directly. Do not require Dashboard -> Generate Summary
        # first, because those operational imports are the current source data.
        # The generated statement remains separately available for exports/CIH.
        deposit_map, withdrawal_map = {}, {}
        try:
            current_statement = self.generate_account_statement()
        except Exception:
            current_statement = pd.DataFrame()
        if current_statement is not None and not current_statement.empty and "Wallet Account" in current_statement.columns:
            for _, row in current_statement.iterrows():
                wallet = str(row.get("Wallet Account", "")).strip().upper()
                if wallet:
                    deposit_map[wallet] = self._number(row.get("Deposit", 0))
                    withdrawal_map[wallet] = self._number(row.get("Withdrawal", 0))

        limit_map = limits.set_index("WALLETNAME").to_dict("index") if not limits.empty else {}
        opening_map = opening.set_index("WALLETNAME").to_dict("index") if not opening.empty else {}
        adj_map = adjustment.set_index("WALLETNAME")["ADJUSTMENT"].to_dict() if not adjustment.empty else {}
        tags = self._permanent_closed_tags()
        remarks = self._remarks_map()

        out = pd.DataFrame(index=master.index)
        out["ACT SDP"] = master["SDP PAID"]
        out["MRC LMT"] = master["MRC DP LIMIT"]

        # DP Bal Limit priority: Active Accounts -> Disabled Accounts -> Locked Accounts.
        # Match by cleaned wallet/account name and read the source column named
        # "DP Balance Limit" (with a tolerant normalized-header fallback).
        dp_bal_limit_map = {}
        for source_name in ["Active Accounts", "Disabled Accounts", "Locked Accounts"]:
            source = self.data.dataframes.get(source_name)
            if source is None or source.empty:
                continue
            account_col = self._source_col(source, "Account Name", 5)
            dp_bal_col = self._source_col(source, "DP Balance Limit", None)
            if dp_bal_col is None:
                for c in source.columns:
                    norm = re.sub(r"[^a-z0-9]", "", str(c).lower())
                    if norm in {"dpbalancelimit", "dpbalancelmt"} or ("dp" in norm and "balance" in norm and "limit" in norm):
                        dp_bal_col = c
                        break
            if account_col is None or dp_bal_col is None:
                continue
            for acct, value in zip(source[account_col], source[dp_bal_col]):
                wallet_name = self.clean_wallet_account(acct)
                if not wallet_name:
                    continue
                raw = str(value).strip().replace(",", "")
                if not raw or raw.upper() in {"NAN", "NONE", "NULL"}:
                    continue
                number = pd.to_numeric(raw, errors="coerce")
                if pd.isna(number):
                    continue
                # first source with a usable value wins: Active -> Disabled -> Locked
                dp_bal_limit_map.setdefault(str(wallet_name).strip().upper(), float(number))

        out["DP Bal Limit"] = master["WALLETNAME"].map(
            lambda x: dp_bal_limit_map.get(str(x).strip().upper(), 0.0)
        )
        out["ACCOUNTS"] = master["WALLETNAME"]
        # In Extended Running Balance mode, the opening for EACH ACCOUNT must
        # come from the R. BAL snapshot captured when the button was pressed.
        # Do not map this through the imported Morning Balance WALLETNAME only;
        # account names can differ from the imported shop/wallet labels.
        ext_map = getattr(self.data, "extended_opening_map", {}) or {}
        if getattr(self.data, "extended_opening_active", False) and ext_map:
            out["OPENING"] = master["WALLETNAME"].map(
                lambda x: ext_map.get(str(x).strip().upper(),
                                      opening_map.get(str(x).strip().upper(), {}).get("OPENING", 0.0))
            )
        else:
            out["OPENING"] = master["WALLETNAME"].map(
                lambda x: opening_map.get(str(x).strip().upper(), {}).get("OPENING", 0.0)
            )
        out["DEPOSIT"] = master["WALLETNAME"].map(lambda x: deposit_map.get(str(x).upper(), 0.0))
        out["WITHDRAWAL"] = master["WALLETNAME"].map(lambda x: withdrawal_map.get(str(x).upper(), 0.0))
        out["ADJUSTMENT"] = master["WALLETNAME"].map(lambda x: adj_map.get(str(x).upper(), 0.0))
        out["R. BAL"] = pd.to_numeric(out["OPENING"], errors="coerce").fillna(0) + pd.to_numeric(out["DEPOSIT"], errors="coerce").fillna(0) - pd.to_numeric(out["WITHDRAWAL"], errors="coerce").fillna(0) + pd.to_numeric(out["ADJUSTMENT"], errors="coerce").fillna(0)
        out["A. BAL"] = master["WALLETNAME"].map(lambda x: limit_map.get(str(x).upper(), {}).get("A. BAL", 0.0))
        out["DISCREP"] = pd.to_numeric(out["R. BAL"], errors="coerce").fillna(0) - pd.to_numeric(out["A. BAL"], errors="coerce").fillna(0)
        out["STATUS"] = master["WALLETNAME"].map(lambda x: limit_map.get(str(x).upper(), {}).get("STATUS", "Locked Account"))
        out["CODE"] = master["WALLETNAME"].map(lambda x: limit_map.get(str(x).upper(), {}).get("CODE", "Locked Account"))
        out["W. HRS"] = master["HOURS"]
        out["WALLET"] = master["WALLETNAME"].map(lambda x: limit_map.get(str(x).upper(), {}).get("WALLET", ""))
        out["WALLET"] = out["WALLET"].where(out["WALLET"].astype(str).str.strip().ne(""), master["WALLET"])
        out["LIMIT STATUS"] = master["WALLETNAME"].map(lambda x: limit_map.get(str(x).upper(), {}).get("LIMIT STATUS", ""))
        locked_mask = out["STATUS"].astype(str).str.strip().str.casefold().eq("Locked Account".casefold()) & out["CODE"].astype(str).str.strip().str.casefold().eq("Locked Account".casefold())
        out.loc[locked_mask, "LIMIT STATUS"] = "Locked Account"
        out["LIMIT STATUS"] = out["LIMIT STATUS"].astype(str).replace({"nan":"", "None":""}).where(lambda s:s.str.strip().ne(""), "Locked")
        out["ACCT TYPE"] = master["ACCOUNT TYPE"]
        out["TAGS"] = master["WALLETNAME"].map(lambda x: tags.get(str(x).upper(), ""))
        out["REMARKS"] = master["WALLETNAME"].map(lambda x: remarks.get(str(x).upper(), ""))

        normalized = out["ACCT TYPE"].astype(str).str.strip().str.upper()
        out["_TYPE"] = "Agent Accounts"
        out.loc[normalized.str.contains("PERSONAL", na=False), "_TYPE"] = "Personal Accounts"
        out.loc[normalized.str.contains("VIP", na=False), "_TYPE"] = "VIP Accounts"
        out.loc[normalized.str.contains("WITHDRAWAL", na=False), "_TYPE"] = "Withdrawal Only"
        out["_PERMANENT_STOP"] = False

        # Permanent Stop is an additional mixed view driven directly by the
        # persistent Permanently Closed Accounts storage. It is a FILTER PAGE,
        # not a replacement for the Agent/Personal/VIP/Withdrawal classifications.
        closed=self.data._autocorrect_closed_from_master(self.data.dataframes.get("Permanently Closed Accounts"))
        if closed is not None and not closed.empty:
            closed_names=set(closed["Wallet name"].astype(str).str.strip().str.upper())
            out.loc[out["ACCOUNTS"].astype(str).str.strip().str.upper().isin(closed_names), "_PERMANENT_STOP"] = True
            existing_names=set(out["ACCOUNTS"].astype(str).str.strip().str.upper())
            missing=closed[~closed["Wallet name"].astype(str).str.strip().str.upper().isin(existing_names)].copy()
            if not missing.empty:
                extra=pd.DataFrame(index=range(len(missing)), columns=MONITOR_COLUMNS + ["_TYPE","_PERMANENT_STOP"])
                for c in MONITOR_COLUMNS: extra[c]=''
                extra["ACCOUNTS"]=missing["Wallet name"].values
                extra["WALLET"]=missing["Wallet"].values
                extra["ACCT TYPE"]=missing["Account type"].values
                extra["TAGS"]=missing["Status"].values
                extra["REMARKS"]=missing["Remarks"].values
                extra["STATUS"]=missing["Status"].values
                extra["CODE"]=missing["Status"].values
                extra["LIMIT STATUS"]=missing["Status"].values
                extra["_PERMANENT_STOP"]=True
                extra_type=[]
                for value in missing["Account type"]:
                    text=str(value).strip().upper()
                    if "PERSONAL" in text: extra_type.append("Personal Accounts")
                    elif "VIP" in text: extra_type.append("VIP Accounts")
                    elif "WITHDRAWAL" in text: extra_type.append("Withdrawal Only")
                    else: extra_type.append("Agent Accounts")
                extra["_TYPE"]=extra_type
                out=pd.concat([out,extra],ignore_index=True)
        return out[MONITOR_COLUMNS + ["_TYPE","_PERMANENT_STOP"]]

    def build_account_monitoring_dataframe(self):
        cached = self._cached('monitoring')
        if cached is not None:
            return cached.copy()
        return self._store_cache('monitoring', self.build_account_monitoring_dataframe_uncached())

    # ========================================================
    # CIH OVERVIEW LOGIC
    # ========================================================

    def _opening_wallet_balances_uncached(self):
        source = self.data.opening_sheets.get("Wallet Balances") if self.data.opening_sheets else None
        if source is None or source.empty:
            return {}
        wallet_col = self._source_col(source, "WALLET", 0)
        amount_col = self._source_col(source, "AMOUNT", 1)
        if wallet_col is None:
            return {}
        out = {}
        for _, row in source.iterrows():
            wallet = str(row.get(wallet_col, "") or "").strip().upper()
            if wallet:
                out[wallet] = self._number(row.get(amount_col, 0)) if amount_col else 0.0
        return out

    def _opening_wallet_balances(self):
        cached = self._cached('opening_wallets')
        if cached is not None:
            return dict(cached)
        return self._store_cache('opening_wallets', self._opening_wallet_balances_uncached())

    @staticmethod
    def _wallet_family(wallet):
        w = str(wallet or "").strip().upper()
        return w

    @staticmethod
    def _wallet_is_personal(wallet):
        return str(wallet or "").strip().upper().endswith("C")

    @staticmethod
    def _wallet_base(wallet):
        w = str(wallet or "").strip().upper()
        return w[:-1] if w.endswith("C") else w

    @staticmethod
    def _is_permanent_stop(value):
        return "PERMANENT STOP" in str(value or "").strip().upper()

    @staticmethod
    def _is_locked_value(*values):
        text = " ".join(str(v or "").strip().upper() for v in values)
        return any(token in text for token in ("LOCKED ACCOUNT", "ACCOUNT LOCKED", "FULLY LOCKED"))

    def _cih_monitor_df(self):
        return self.build_account_monitoring_dataframe().copy()

    def _cih_limit_rows_uncached(self):
        """Return raw LIMIT rows normalized for CIH calculations.

        CIH System Balance, limit-status totals, and account counts use the
        LIMIT import directly so they are not affected by Account Monitoring
        aggregation or master-list state.
        """
        source = self.data.dataframes.get("Limit")
        if source is None or source.empty:
            return pd.DataFrame(columns=["WALLET", "GROUP", "ACCOUNT", "BALANCE", "LOGIN", "STATUS"])
        bank_col = self._source_col(source, "Bank", 0)
        group_col = self._source_col(source, "Group", 2)
        account_col = self._source_col(source, "Account", 3)
        balance_col = self._source_col(source, "Balance", 4)
        login_col = self._source_col(source, "Login", 13)
        status_col = self._source_col(source, "Status", 14)
        if any(c is None for c in (bank_col, group_col, account_col, balance_col, login_col, status_col)):
            return pd.DataFrame(columns=["WALLET", "GROUP", "ACCOUNT", "BALANCE", "LOGIN", "STATUS"])
        out = pd.DataFrame(index=source.index)
        out["WALLET"] = source[bank_col].fillna("").astype(str).str.strip().str.upper()
        out["GROUP"] = source[group_col].fillna("").astype(str).str.strip()
        out["ACCOUNT"] = source[account_col].fillna("").astype(str).str.strip()
        out["BALANCE"] = source[balance_col].apply(self._number)
        out["LOGIN"] = source[login_col].fillna("").astype(str).str.strip().str.upper()
        out["STATUS"] = source[status_col].fillna("").astype(str).str.strip()
        return out

    def _cih_limit_rows(self):
        cached = self._cached('cih_limit')
        if cached is not None:
            return cached.copy()
        return self._store_cache('cih_limit', self._cih_limit_rows_uncached())

    @staticmethod
    def _cih_is_locked_group(series):
        return series.astype(str).str.upper().str.contains(
            r"LOCKED ACCOUNT|ACCOUNT LOCKED|FULLY LOCKED", regex=True, na=False
        )

    def _merchant_wallet_totals(self, df, wallet_columns):
        if df is None or df.empty:
            return {w: 0.0 for w in wallet_columns}
        result = {}
        for w in wallet_columns:
            result[w] = self._number(df[w].sum()) if w in df.columns else 0.0
        return result


    @staticmethod
    def _cih_total_row(df, label_col):
        if df is None or df.empty:
            return pd.DataFrame()
        total = {}
        for c in df.columns:
            if c == label_col:
                total[c] = 'TOTAL'
            else:
                vals = pd.to_numeric(df[c].astype(str).str.replace(',', '', regex=False), errors='coerce')
                total[c] = float(vals.fillna(0).sum())
        return pd.DataFrame([total], columns=df.columns)

    def _cih_wallet_table(self, personal=False):
        # includes the Generate-Summary revision: this table reads merchant_deposit_result / merchant_payout_result
        cache_key = f"{'cih_personal' if personal else 'cih_agent'}:{self.data.summary_revision}"
        cached = self._cached(cache_key)
        if cached is not None:
            return cached.copy()
        wallets = ["BKASHC", "NAGADC", "ROCKETC", "UPAYC"] if personal else ["BKASH", "NAGAD", "ROCKET", "UPAY"]
        monitor = self._cih_monitor_df()
        limit = self._cih_limit_rows()
        opening = self._opening_wallet_balances()
        dep = self._merchant_wallet_totals(self.data.merchant_deposit_result, wallets)
        pay = self._merchant_wallet_totals(self.data.merchant_payout_result, wallets)

        rows = []
        for wallet in wallets:
            part = monitor[monitor["WALLET"].astype(str).str.upper().eq(wallet)] if not monitor.empty else pd.DataFrame()
            if not part.empty:
                tags = part["TAGS"].astype(str).str.upper()
                permanent_mask = tags.str.contains("PERMANENT STOP", regex=False, na=False)
                pl_bal = pd.to_numeric(part.loc[permanent_mask, "R. BAL"], errors="coerce").fillna(0).sum()
                login = part["STATUS"].astype(str).str.contains("LOG IN", case=False, na=False)
                locked_code = self._cih_is_locked_group(part["CODE"])
                locked_mask = (~login) & locked_code & ~permanent_mask
                locked_bal = pd.to_numeric(part.loc[locked_mask, "R. BAL"], errors="coerce").fillna(0).sum()
                adjustment = pd.to_numeric(part["ADJUSTMENT"], errors="coerce").fillna(0).sum()
            else:
                pl_bal = locked_bal = adjustment = 0.0

            # System balance, daily/monthly limits, and counts are sourced
            # directly from LIMIT, not from Account Monitoring.
            if not limit.empty:
                lp = limit[limit["WALLET"].eq(wallet)].copy()
                login_yes = lp["LOGIN"].eq("YES")
                active = lp["STATUS"].str.upper().eq("ACTIVE")
                not_locked = ~self._cih_is_locked_group(lp["GROUP"])
                if personal:
                    system_mask = login_yes & active & not_locked
                    daily_mask = lp["STATUS"].str.upper().eq("DAILY REACH LIMIT")
                    monthly_mask = lp["STATUS"].str.upper().eq("MONTHLY REACH LIMIT")
                    daily_limit = pd.to_numeric(lp.loc[daily_mask, "BALANCE"], errors="coerce").fillna(0).sum()
                    monthly_limit = pd.to_numeric(lp.loc[monthly_mask, "BALANCE"], errors="coerce").fillna(0).sum()
                else:
                    group_upper = lp["GROUP"].str.upper()
                    system_mask = login_yes & active & not_locked & (
                        group_upper.str.contains("DP", regex=False, na=False) |
                        group_upper.str.contains("WD", regex=False, na=False)
                    )
                    daily_limit = monthly_limit = 0.0
                system_bal = pd.to_numeric(lp.loc[system_mask, "BALANCE"].astype(str).str.replace(",","",regex=False), errors="coerce").fillna(0).sum()
                locked_system_mask = (~login_yes) & self._cih_is_locked_group(lp["GROUP"])
                locked_system_bal = pd.to_numeric(lp.loc[locked_system_mask, "BALANCE"].astype(str).str.replace(",","",regex=False), errors="coerce").fillna(0).sum()
            else:
                system_bal = daily_limit = monthly_limit = locked_system_bal = 0.0

            opening_value = opening.get(wallet, 0.0)
            deposit_value = dep.get(wallet, 0.0)
            # Merchant Pay out is displayed/stored as a negative value.
            payout_value = -abs(pay.get(wallet, 0.0))
            # Payout is already negative, therefore ADD it to the running balance.
            active_running = opening_value + deposit_value + payout_value + adjustment - pl_bal - locked_bal
            final_closing = active_running - pl_bal
            rows.append({
                "Wallet Name": wallet,
                "Opening": opening_value,
                "Deposit": deposit_value,
                "Payout": payout_value,
                "STLM/SPC": adjustment,
                "P.L. Acc's": pl_bal,
                "Locked Acc's": locked_bal,
                "System Balance": system_bal,
                "Locked Acc's System Bal.": locked_system_bal,
                "Daily Limit": daily_limit,
                "Monthly Limit": monthly_limit,
                "Active Running bal.": active_running,
                "Final Closing Bal": final_closing,
            })
        return self._store_cache(cache_key, pd.DataFrame(rows))

    def _cih_count_table(self, personal=False, withdrawal=False):
        cache_key = f"cih_count_{'personal' if personal else 'agent'}_{'wd' if withdrawal else 'balance'}"
        cached = self._cached(cache_key)
        if cached is not None:
            return cached.copy()
        wallets = ["BKASHC", "NAGADC", "ROCKETC", "UPAYC"] if personal else ["BKASH", "NAGAD", "ROCKET", "UPAY"]
        limit = self._cih_limit_rows()
        rows = []
        for wallet in wallets:
            if not limit.empty:
                part = limit[limit["WALLET"].eq(wallet)].copy()
                login_yes = part["LOGIN"].astype(str).str.strip().str.upper().eq("YES")
                active = part["STATUS"].astype(str).str.strip().str.upper().eq("ACTIVE")
                group_upper = part["GROUP"].astype(str).str.strip().str.upper()
                if withdrawal:
                    group_mask = (group_upper.str.contains("BANKING", regex=False, na=False) if personal
                                  else group_upper.str.contains("WD", regex=False, na=False))
                    mask = login_yes & active & group_mask
                else:
                    mask = login_yes & active
                vals = pd.to_numeric(part.loc[mask, "BALANCE"].astype(str).str.replace(",","",regex=False), errors="coerce").fillna(0)
            else:
                vals = pd.Series(dtype=float)
            rows.append({
                "Wallets": wallet,
                "<25k": int((vals < 25000).sum()),
                "25k+": int(((vals >= 25000) & (vals < 50000)).sum()),
                "50k+": int(((vals >= 50000) & (vals < 100000)).sum()),
                "100k+": int((vals >= 100000).sum()),
            })
        return self._store_cache(cache_key, pd.DataFrame(rows))


    @staticmethod
    def _availability_locked_group(value):
        """Groups excluded from CIH Limit Availability calculations."""
        text = str(value or "").strip().upper()
        return ("LOCKED ACCOUNT" in text) or ("ACCOUNT LOCKED" in text)

    @staticmethod
    def _availability_type_is_personal(value):
        return "PERSONAL" in str(value or "").strip().upper()

    @staticmethod
    def _availability_canonical_hours(value):
        text = str(value or "").strip().upper()
        compact = re.sub(r"[^A-Z0-9]", "", text)
        if compact in {"14HOURS", "14H"}: return "14 Hours"
        if compact in {"16HOURS", "16H"}: return "16 Hours"
        if compact in {"18HOURS", "18H"}: return "18 Hours"
        if compact in {"24HOURS", "24H"}: return "24 Hours"
        if compact in {"24H0SINTERVAL", "24H0INTERVAL", "24H00SINTERVAL"}: return "24-H0s INTERVAL"
        return str(value or "").strip()

    @staticmethod
    def _availability_canonical_method(value):
        text = str(value or "").strip().upper()
        if "EBANK" in text: return "EBANKING"
        if "IBANK" in text: return "IBANKING"
        return str(value or "").strip().upper()

    def _cih_limit_availability_uncached(self):
        """Build the CIH Limit Availability tables from the persistent Master List.

        Agent tables are split by HOURS; Personal tables are split by METHOD.
        Each eligible row contributes its MRC DP LIMIT and one account count to
        its wallet/bucket. Rows whose GROUP CODE contains 'LOCKED ACCOUNT' or
        'ACCOUNT LOCKED' are excluded.
        """
        cache_key = "cih_limit_availability"
        master = AppData._normalise_master(self.data.dataframes.get("Wallet Account Master List"))
        if master.empty:
            agent_cols=["Wallet","14 Hours","16 Hours","18 Hours","24 Hours","24-H0s INTERVAL","TOTAL"]
            personal_cols=["Wallet","EBANKING","IBANKING","TOTAL"]
            empty_agent=pd.DataFrame(columns=agent_cols)
            empty_personal=pd.DataFrame(columns=personal_cols)
            return {
                "agent_limit": empty_agent.copy(),
                "agent_limit_total": pd.DataFrame([{
                    "Wallet":"TOTAL","14 Hours":0.0,"16 Hours":0.0,"18 Hours":0.0,
                    "24 Hours":0.0,"24-H0s INTERVAL":0.0,"TOTAL":0.0
                }],columns=agent_cols),
                "agent_count": empty_agent.copy(),
                "agent_count_total": pd.DataFrame([{
                    "Wallet":"TOTAL","14 Hours":0,"16 Hours":0,"18 Hours":0,
                    "24 Hours":0,"24-H0s INTERVAL":0,"TOTAL":0
                }],columns=agent_cols),
                "personal_limit": empty_personal.copy(),
                "personal_limit_total": pd.DataFrame([{
                    "Wallet":"TOTAL","EBANKING":0.0,"IBANKING":0.0,"TOTAL":0.0
                }],columns=personal_cols),
                "personal_count": empty_personal.copy(),
                "personal_count_total": pd.DataFrame([{
                    "Wallet":"TOTAL","EBANKING":0,"IBANKING":0,"TOTAL":0
                }],columns=personal_cols),
                "overall_agent": 0.0,
                "overall_personal": 0.0,
            }

        # Keep Master List synchronized with the current operational source priority,
        # but perform the availability totals on the resulting master records.
        try:
            master = self.sync_master_from_imports()
        except Exception:
            master = AppData._normalise_master(master)
        master = AppData._normalise_master(master).copy().fillna("")

        # Normalize strings without changing stored master data.
        master["WALLET"] = master["WALLET"].astype(str).str.strip().str.upper()
        master["GROUP CODE"] = master["GROUP CODE"].astype(str).str.strip()
        master["ACCOUNT TYPE"] = master["ACCOUNT TYPE"].astype(str).str.strip().str.upper()
        master["HOURS"] = master["HOURS"].astype(str).map(self._availability_canonical_hours)
        master["METHOD"] = master["METHOD"].astype(str).map(self._availability_canonical_method)
        master["MRC DP LIMIT"] = master["MRC DP LIMIT"].apply(self._number)
        eligible = ~master["GROUP CODE"].map(self._availability_locked_group)

        agent = master[~master["ACCOUNT TYPE"].map(self._availability_type_is_personal) & eligible].copy()
        personal = master[master["ACCOUNT TYPE"].map(self._availability_type_is_personal) & eligible].copy()

        agent_wallets = ["BKASH", "NAGAD", "ROCKET", "UPAY"]
        personal_wallets = ["BKASHC", "NAGADC", "ROCKETC", "UPAYC"]
        standard_hours = ["14 Hours", "16 Hours", "18 Hours", "24 Hours", "24-H0s INTERVAL"]
        standard_methods = ["EBANKING", "IBANKING"]

        def build_amount_table(src, wallets, buckets, bucket_col):
            rows=[]
            for wallet in wallets:
                row={"Wallet": wallet}
                part=src[src["WALLET"].eq(wallet)]
                total=0.0
                for bucket in buckets:
                    vals=part[part[bucket_col].eq(bucket)]["MRC DP LIMIT"] if not part.empty else pd.Series(dtype=float)
                    amount=float(vals.sum()) if len(vals) else 0.0
                    row[bucket]=amount
                    total += amount
                row["TOTAL"]=total
                rows.append(row)
            out=pd.DataFrame(rows,columns=["Wallet"]+list(buckets)+["TOTAL"])
            total_row={"Wallet":"TOTAL"}
            for bucket in buckets:
                total_row[bucket]=float(pd.to_numeric(out[bucket],errors="coerce").fillna(0).sum())
            total_row["TOTAL"]=float(pd.to_numeric(out["TOTAL"],errors="coerce").fillna(0).sum())
            return out,pd.DataFrame([total_row],columns=out.columns)

        def build_count_table(src, wallets, buckets, bucket_col):
            rows=[]
            for wallet in wallets:
                row={"Wallet":wallet}
                part=src[src["WALLET"].eq(wallet)]
                total=0
                for bucket in buckets:
                    count=int((part[bucket_col].eq(bucket)).sum()) if not part.empty else 0
                    row[bucket]=count
                    total += count
                row["TOTAL"]=total
                rows.append(row)
            out=pd.DataFrame(rows,columns=["Wallet"]+list(buckets)+["TOTAL"])
            total_row={"Wallet":"TOTAL"}
            for bucket in buckets:
                total_row[bucket]=int(pd.to_numeric(out[bucket],errors="coerce").fillna(0).sum())
            total_row["TOTAL"]=int(pd.to_numeric(out["TOTAL"],errors="coerce").fillna(0).sum())
            return out,pd.DataFrame([total_row],columns=out.columns)

        agent_limit,agent_limit_total=build_amount_table(agent,agent_wallets,standard_hours,"HOURS")
        agent_count,agent_count_total=build_count_table(agent,agent_wallets,standard_hours,"HOURS")
        personal_limit,personal_limit_total=build_amount_table(personal,personal_wallets,standard_methods,"METHOD")
        personal_count,personal_count_total=build_count_table(personal,personal_wallets,standard_methods,"METHOD")

        # Return totals separately so the page can present 'Overall Limit' cleanly.
        return self._store_cache(cache_key, {
            "agent_limit": agent_limit,
            "agent_limit_total": agent_limit_total,
            "agent_count": agent_count,
            "agent_count_total": agent_count_total,
            "personal_limit": personal_limit,
            "personal_limit_total": personal_limit_total,
            "personal_count": personal_count,
            "personal_count_total": personal_count_total,
            "overall_agent": float(agent_limit_total.iloc[0]["TOTAL"]) if not agent_limit_total.empty else 0.0,
            "overall_personal": float(personal_limit_total.iloc[0]["TOTAL"]) if not personal_limit_total.empty else 0.0,
        })

    def cih_limit_availability(self):
        cached=self._cached("cih_limit_availability")
        if cached is not None:
            result=dict(cached)
            for k,v in result.items():
                if isinstance(v,pd.DataFrame): result[k]=v.copy()
            return result
        return self._cih_limit_availability_uncached()

    def cih_wallet_balance_cards(self):
        agent = self._cih_wallet_table(False).set_index("Wallet Name")
        personal = self._cih_wallet_table(True).set_index("Wallet Name")
        return pd.concat([agent["System Balance"], personal["System Balance"]]).to_dict()

    def dashboard_totals(self):
        """Return current imported transaction totals for the dashboard.

        Deposit and payout totals are based directly on the current imported
        histories, include all accounts regardless of master/account status,
        and count only Successful transactions. STLM/Top Up is the net
        adjustment (Top Up minus Settlement) across the current workbook.
        """
        deposit_total = 0.0
        payout_total = 0.0
        deposits = self.data.dataframes.get("Deposit History")
        if deposits is not None and not deposits.empty:
            status_col = self._source_col(deposits, "Status", 17)
            amount_col = self._source_col(deposits, "Amount", 10)
            if amount_col is not None:
                mask = pd.Series(True, index=deposits.index)
                if status_col is not None:
                    mask = self.normalize_status(deposits[status_col]).eq("successful")
                vals = pd.to_numeric(deposits.loc[mask, amount_col].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0)
                deposit_total = float(vals.sum())
        payouts = self.data.dataframes.get("Pay Out History")
        if payouts is not None and not payouts.empty:
            status_col = self._source_col(payouts, "Status", 20)
            amount_col = self._source_col(payouts, "Amount", 12)
            if amount_col is not None:
                mask = pd.Series(True, index=payouts.index)
                if status_col is not None:
                    mask = self.normalize_status(payouts[status_col]).eq("successful")
                vals = pd.to_numeric(payouts.loc[mask, amount_col].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0)
                payout_total = float(vals.sum())
        adjustment_df = self._adjustment_dataframe()
        stlm_topup_total = float(pd.to_numeric(adjustment_df.get("ADJUSTMENT", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not adjustment_df.empty else 0.0
        return {
            "Total Deposit": deposit_total,
            "Total Pay out": payout_total,
            "Total STLM / Top Up": stlm_topup_total,
        }

    def dashboard_limit_utilization(self):
        """Build Dashboard limit-left tables from current Limit + generated deposit summary.

        LIMIT (raw import) is the source for Remaining DP and Counts.
        The CIH Limit Availability totals are the source for the headline LIMIT
        values, while Deposit Type Summary is the source for DEPOSIT.
        """
        # includes the Generate-Summary revision: the DEPOSIT column reads deposit_type_result, so a cached
        # result built before Generate Summary must not be reused afterwards
        cache_key = f"dashboard_limit_utilization:{self.data.summary_revision}"
        cached = self._cached(cache_key)
        if cached is not None:
            return {k: v.copy() for k, v in cached.items()}
        availability = self.cih_limit_availability()
        limit = self.data.dataframes.get("Limit")
        if limit is None or limit.empty:
            raw = pd.DataFrame(columns=["WALLET","GROUP","ACCOUNT","REMAINING_DP","LOGIN","STATUS"])
        else:
            bank_col = self._source_col(limit, "Bank", 0)
            group_col = self._source_col(limit, "Group", 2)
            account_col = self._source_col(limit, "Account", 3)
            remaining_dp_col = self._source_col(limit, "Remaining DP", 11)
            login_col = self._source_col(limit, "Login", 13)
            status_col = self._source_col(limit, "Status", 14)
            if any(c is None for c in (bank_col, group_col, account_col, remaining_dp_col, login_col, status_col)):
                raw = pd.DataFrame(columns=["WALLET","GROUP","ACCOUNT","REMAINING_DP","LOGIN","STATUS"])
            else:
                raw = pd.DataFrame({
                    "WALLET": limit[bank_col].fillna("").astype(str).str.strip().str.upper(),
                    "GROUP": limit[group_col].fillna("").astype(str).str.strip(),
                    "ACCOUNT": limit[account_col].fillna("").astype(str).str.strip(),
                    "REMAINING_DP": limit[remaining_dp_col].apply(self._number),
                    "LOGIN": limit[login_col].fillna("").astype(str).str.strip().str.upper(),
                    "STATUS": limit[status_col].fillna("").astype(str).str.strip().str.upper(),
                })

        # ---- Deposit totals from Deposit Type Summary ----
        dep_summary = self.data.deposit_type_result
        dep_all = {w: 0.0 for w in ["BKASH","NAGAD","ROCKET","UPAY","BKASHC","NAGADC","ROCKETC","UPAYC"]}
        dep_by_method = {
            "EBANKING": {w: 0.0 for w in ["BKASHC","NAGADC","ROCKETC","UPAYC"]},
            "IBANKING": {w: 0.0 for w in ["BKASHC","NAGADC","ROCKETC","UPAYC"]},
        }
        if dep_summary is not None and not dep_summary.empty and "Deposit Type" in dep_summary.columns:
            for wallet in dep_all:
                if wallet in dep_summary.columns:
                    dep_all[wallet] = float(pd.to_numeric(
                        dep_summary[wallet].astype(str).str.replace(",", "", regex=False),
                        errors="coerce"
                    ).fillna(0).sum())
            method_map = {
                "EBANKING": "EBANKING",
                "EBANKING ": "EBANKING",
                "IBANKING": "IBANKING",
                "IBANKING ": "IBANKING",
            }
            types = dep_summary["Deposit Type"].astype(str).str.strip().str.upper()
            for method in ("EBANKING", "IBANKING"):
                mask = types.eq(method)
                if mask.any():
                    for wallet in dep_by_method[method]:
                        if wallet in dep_summary.columns:
                            vals = pd.to_numeric(dep_summary.loc[mask, wallet].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0)
                            dep_by_method[method][wallet] = float(vals.sum())

        agent_wallets = ["BKASH", "NAGAD", "ROCKET", "UPAY"]
        personal_wallets = ["BKASHC", "NAGADC", "ROCKETC", "UPAYC"]

        # Headline LIMIT values come from CIH Limit Availability.
        agent_limit_df = availability.get("agent_limit", pd.DataFrame())
        personal_limit_df = availability.get("personal_limit", pd.DataFrame())
        agent_limit_map = {}
        for _, row in agent_limit_df.iterrows():
            agent_limit_map[str(row.get("Wallet", "")).strip().upper()] = self._number(row.get("TOTAL", 0))

        personal_limit_map = {
            "EBANKING": {},
            "IBANKING": {},
        }
        for _, row in personal_limit_df.iterrows():
            wallet = str(row.get("Wallet", "")).strip().upper()
            if wallet:
                personal_limit_map["EBANKING"][wallet] = self._number(row.get("EBANKING", 0))
                personal_limit_map["IBANKING"][wallet] = self._number(row.get("IBANKING", 0))

        def agent_qualifying(part):
            if part.empty:
                return part
            # Deposit-capable agent accounts: Login Yes, Active, Group contains DP.
            return part[
                part["LOGIN"].eq("YES")
                & part["STATUS"].eq("ACTIVE")
                & part["GROUP"].astype(str).str.upper().str.contains("DP", regex=False, na=False)
            ]

        def personal_qualifying(part, method):
            if part.empty:
                return part
            g = part["GROUP"].astype(str).str.strip().str.upper()
            base = part[part["LOGIN"].eq("YES") & part["STATUS"].eq("ACTIVE")].copy()
            if base.empty:
                return base
            g = base["GROUP"].astype(str).str.strip().str.upper()
            # Method-specific groups. Remove the WD-only variants explicitly.
            target = g.str.contains(method, regex=False, na=False)
            wd_only_patterns = (
                r"WD\s*ONLY\s*16\s*HOURS\s*-\s*IBANKING",
                r"WD\s*ONLY\s*16\s*HOURS\s*-\s*PERSONAL\s*EBANKING",
                r"WD\s*ONLY\s*24\s*HOURS\s*-\s*IBANKING",
                r"WD\s*ONLY\s*24\s*HOURS\s*-\s*PERSONAL\s*EBANKING",
            )
            excluded = g.str.contains("|".join(wd_only_patterns), regex=True, na=False)
            return base[target & ~excluded]

        def build_agent_table():
            rows=[]
            for wallet in agent_wallets:
                part = agent_qualifying(raw[raw["WALLET"].eq(wallet)].copy()) if not raw.empty else pd.DataFrame()
                rows.append({
                    "WALLET": wallet,
                    "LIMIT": agent_limit_map.get(wallet, 0.0),
                    "Remaining Limit": float(part["REMAINING_DP"].sum()) if not part.empty else 0.0,
                    "Counts": int(len(part)),
                    "DEPOSIT": dep_all.get(wallet, 0.0),
                })
            out=pd.DataFrame(rows)
            return out

        def build_personal_table(method):
            rows=[]
            for wallet in personal_wallets:
                part = personal_qualifying(raw[raw["WALLET"].eq(wallet)].copy(), method) if not raw.empty else pd.DataFrame()
                rows.append({
                    "WALLET": wallet,
                    "LIMIT": personal_limit_map[method].get(wallet, 0.0),
                    "Remaining Limit": float(part["REMAINING_DP"].sum()) if not part.empty else 0.0,
                    "Counts": int(len(part)),
                    "DEPOSIT": dep_by_method[method].get(wallet, 0.0),
                })
            return pd.DataFrame(rows)

        def append_total(df):
            total={"WALLET":"TOTAL"}
            for c in ["LIMIT","Remaining Limit","DEPOSIT"]:
                total[c]=float(pd.to_numeric(df[c],errors="coerce").fillna(0).sum()) if not df.empty else 0.0
            total["Counts"]=int(pd.to_numeric(df["Counts"],errors="coerce").fillna(0).sum()) if not df.empty else 0
            return pd.concat([df,pd.DataFrame([total])],ignore_index=True)

        agent=build_agent_table()
        personal_eb=build_personal_table("EBANKING")
        personal_ib=build_personal_table("IBANKING")
        result = {
            "agent": append_total(agent),
            "personal_ebanking": append_total(personal_eb),
            "personal_ibanking": append_total(personal_ib),
        }
        return self._store_cache(cache_key, result)

    # ========================================================
    # MAIN SUMMARY
    # ========================================================

    def generate_summary(self, from_date, to_date):

        account_statement = self.generate_account_statement(
            from_date,
            to_date
        )

        merchant_deposit = self.generate_merchant_deposit(
            from_date,
            to_date
        )

        merchant_payout = self.generate_merchant_payout(
            from_date,
            to_date
        )

        deposit_type = self.generate_deposit_type_summary(
            from_date,
            to_date
        )

        self.data.summary_result = account_statement
        self.data.merchant_deposit_result = merchant_deposit
        self.data.merchant_payout_result = merchant_payout
        self.data.deposit_type_result = deposit_type
        self.data._touch_summary()

        return account_statement

    # ========================================================
    # 1. ACCOUNT STATEMENT
    # ========================================================

    def generate_account_statement(self, from_date=None, to_date=None):
        """Generate Wallet Account, Deposit, Withdrawal, B2B In and B2B Out.

        This is used by Account Monitoring as well as the generated statement.
        Cache it by date range so opening the monitoring pages does not repeatedly
        rescan the full Deposit/Pay Out/Statement imports.
        """
        cache_key = f"account_statement:{str(from_date or '')}:{str(to_date or '')}"
        cached = self._cached(cache_key)
        if cached is not None:
            return cached.copy()

        master = self.data.dataframes.get("Wallet Account Master List")
        deposits = self.data.dataframes.get("Deposit History")
        payouts = self.data.dataframes.get("Pay Out History")
        statement = self.data.dataframes.get("Account Statement")

        # Wallet accounts are sourced ONLY from Deposit History J (To Account)
        # and Pay Out History K (From Account), then matched to the persistent master.
        discovered = []
        if deposits is not None and "To Account" in deposits.columns:
            discovered.extend(deposits["To Account"].apply(self.clean_wallet_account).dropna().tolist())
        if payouts is not None and "From Account" in payouts.columns:
            discovered.extend(payouts["From Account"].apply(self.clean_wallet_account).dropna().tolist())
        discovered = list(dict.fromkeys(discovered))

        master_accounts = []
        if master is not None and "WALLETNAME" in master.columns:
            master_accounts = (
                master["WALLETNAME"]
                .astype(str)
                .str.strip()
                .str.upper()
                .replace({"NAN": ""})
            )
            master_accounts = [x for x in master_accounts.tolist() if x]

        # Summary should show only accounts already in the master list.
        wallet_accounts = [w for w in discovered if w in set(master_accounts)]
        if not wallet_accounts:
            empty = pd.DataFrame(columns=["Wallet Account", "Deposit", "Withdrawal", "B2B In", "B2B Out"])
            return self._store_cache(cache_key, empty)

        wallet_set = set(wallet_accounts)
        result = pd.DataFrame({"Wallet Account": wallet_accounts})

        deposit_summary = pd.Series(dtype="float64")
        if deposits is not None and not deposits.empty:
            dep = deposits.copy()
            required = {"To Account", "Amount", "Status", "Updated Time"}
            if required.issubset(dep.columns):
                dep = self.filter_by_updated_time(dep, from_date, to_date, "Updated Time")
                dep = dep[self.normalize_status(dep["Status"]) == "successful"]
                dep["Wallet Account"] = dep["To Account"].apply(self.clean_wallet_account)
                dep["Amount"] = pd.to_numeric(dep["Amount"].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0)
                dep = dep[dep["Wallet Account"].isin(wallet_set)]
                deposit_summary = dep.groupby("Wallet Account")["Amount"].sum()

        withdrawal_summary = pd.Series(dtype="float64")
        if payouts is not None and not payouts.empty:
            pay = payouts.copy()
            required = {"From Account", "Amount", "Status", "Updated Time"}
            if required.issubset(pay.columns):
                pay = self.filter_by_updated_time(pay, from_date, to_date, "Updated Time")
                pay = pay[self.normalize_status(pay["Status"]) == "successful"]
                pay["Wallet Account"] = pay["From Account"].apply(self.clean_wallet_account)
                pay["Amount"] = pd.to_numeric(pay["Amount"].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0)
                pay = pay[pay["Wallet Account"].isin(wallet_set)]
                withdrawal_summary = pay.groupby("Wallet Account")["Amount"].sum()

        b2b_in_summary = pd.Series(dtype="float64")
        b2b_out_summary = pd.Series(dtype="float64")
        if statement is not None and not statement.empty:
            stmt = statement.copy()

            # Account Statement source columns are fixed by the user's logic:
            # D = Amount, K = Updated Time, L = Channel.
            # The account field is used only to attach each B2B transaction to
            # the wallet in the master list. Support either common header name.
            account_col = None
            for candidate in ("Account", "Wallet Account"):
                if candidate in stmt.columns:
                    account_col = candidate
                    break

            required = {"Amount", "Channel", "Updated Time"}
            if account_col and required.issubset(stmt.columns):
                # Date MUST come from Account Statement column K / Updated Time.
                stmt = self.filter_by_updated_time(
                    stmt, from_date, to_date, "Updated Time"
                )

                # Account Statement Column B has a different format from
                # Deposit/Pay Out account fields:
                #   HORSE-NG-040 (01345214060)
                # For B2B, use only HORSE-NG-040 as the wallet key.
                stmt["Wallet Account"] = stmt[account_col].apply(
                    self.extract_statement_wallet_account
                )
                stmt["Amount"] = pd.to_numeric(
                    stmt["Amount"].astype(str).str.replace(",", "", regex=False),
                    errors="coerce"
                ).fillna(0)
                stmt["Channel_Normalized"] = self.normalize_channel(
                    stmt["Channel"]
                )
                stmt = stmt[stmt["Wallet Account"].isin(wallet_set)]

                # B2B IN:
                # B2B / B2B Receive / B2B Send / b2b_transfer -> positive only
                # CI -> positive only
                in_channels = {
                    "B2B",
                    "B2B RECEIVE",
                    "B2B SEND",
                    "B2B_TRANSFER",
                    "CI",
                }

                # B2B OUT:
                # B2B / B2B Receive / B2B Send / b2b_transfer -> negative only
                # CO -> negative only
                out_channels = {
                    "B2B",
                    "B2B RECEIVE",
                    "B2B SEND",
                    "B2B_TRANSFER",
                    "CO",
                }

                b2b_in = stmt[
                    stmt["Channel_Normalized"].isin(in_channels)
                    & (stmt["Amount"] > 0)
                ]
                b2b_out = stmt[
                    stmt["Channel_Normalized"].isin(out_channels)
                    & (stmt["Amount"] < 0)
                ]

                b2b_in_summary = b2b_in.groupby(
                    "Wallet Account"
                )["Amount"].sum()

                # Keep B2B Out negative exactly as it appears in Column D.
                b2b_out_summary = b2b_out.groupby(
                    "Wallet Account"
                )["Amount"].sum()

        result["Deposit"] = result["Wallet Account"].map(deposit_summary).fillna(0)
        result["Withdrawal"] = result["Wallet Account"].map(withdrawal_summary).fillna(0)
        result["B2B In"] = result["Wallet Account"].map(b2b_in_summary).fillna(0)
        result["B2B Out"] = result["Wallet Account"].map(b2b_out_summary).fillna(0)
        result = result[["Wallet Account", "Deposit", "Withdrawal", "B2B In", "B2B Out"]].reset_index(drop=True)
        return self._store_cache(cache_key, result)

    # ========================================================
    # 2. MERCHANT DEPOSIT
    # ========================================================

    def generate_merchant_deposit(
        self,
        from_date=None,
        to_date=None
    ):

        deposits = self.data.dataframes.get(
            "Deposit History"
        )

        columns = [
            "Merchant Code",
            *self.DEPOSIT_BANKS
        ]

        if deposits is None or deposits.empty:
            return pd.DataFrame(columns=columns)

        required = {
            "Merchant Code",
            "Bank",
            "Amount",
            "Status",
            "Updated Time",
        }

        if not required.issubset(
            deposits.columns
        ):
            return pd.DataFrame(columns=columns)

        df = deposits.copy()

        # Date
        df = self.filter_by_updated_time(
            df,
            from_date,
            to_date,
            "Updated Time"
        )

        # Successful only
        df = df[
            self.normalize_status(
                df["Status"]
            ) == "successful"
        ]

        # Bank
        df["Bank_Normalized"] = (
            self.normalize_bank(
                df["Bank"]
            )
        )

        # Amount
        df["Amount"] = pd.to_numeric(
            df["Amount"],
            errors="coerce"
        ).fillna(0)

        # Only required banks
        df = df[
            df["Bank_Normalized"].isin(
                self.DEPOSIT_BANKS
            )
        ]

        pivot = df.pivot_table(
            index="Merchant Code",
            columns="Bank_Normalized",
            values="Amount",
            aggfunc="sum",
            fill_value=0,
        )

        # Ensure all banks exist
        for bank in self.DEPOSIT_BANKS:
            if bank not in pivot.columns:
                pivot[bank] = 0

        pivot = pivot[
            self.DEPOSIT_BANKS
        ]

        pivot.reset_index(inplace=True)

        return pivot[
            columns
        ]

    # ========================================================
    # 3. MERCHANT PAY OUT
    # ========================================================

    def generate_merchant_payout(
        self,
        from_date=None,
        to_date=None
    ):

        payouts = self.data.dataframes.get(
            "Pay Out History"
        )

        columns = [
            "Merchant",
            *self.PAYOUT_BANKS
        ]

        if payouts is None or payouts.empty:
            return pd.DataFrame(columns=columns)

        required = {
            "Merchant",
            "Bank",
            "Amount",
            "Status",
            "Updated Time",
        }

        if not required.issubset(
            payouts.columns
        ):
            return pd.DataFrame(columns=columns)

        df = payouts.copy()

        # Date
        df = self.filter_by_updated_time(
            df,
            from_date,
            to_date,
            "Updated Time"
        )

        # Successful only
        df = df[
            self.normalize_status(
                df["Status"]
            ) == "successful"
        ]

        # Bank
        df["Bank_Normalized"] = (
            self.normalize_bank(
                df["Bank"]
            )
        )

        # Amount
        df["Amount"] = pd.to_numeric(
            df["Amount"],
            errors="coerce"
        ).fillna(0)

        # Required payout banks only
        df = df[
            df["Bank_Normalized"].isin(
                self.PAYOUT_BANKS
            )
        ]

        pivot = df.pivot_table(
            index="Merchant",
            columns="Bank_Normalized",
            values="Amount",
            aggfunc="sum",
            fill_value=0,
        )

        for bank in self.PAYOUT_BANKS:
            if bank not in pivot.columns:
                pivot[bank] = 0

        pivot = pivot[
            self.PAYOUT_BANKS
        ]

        pivot.reset_index(inplace=True)

        return pivot[
            columns
        ]

    # ========================================================
    # 4. DEPOSIT TYPE SUMMARY
    # ========================================================

    def generate_deposit_type_summary(
        self,
        from_date=None,
        to_date=None
    ):

        deposits = self.data.dataframes.get(
            "Deposit History"
        )

        columns = [
            "Deposit Type",
            *self.DEPOSIT_BANKS
        ]

        if deposits is None or deposits.empty:
            return pd.DataFrame(columns=columns)

        required = {
            "Deposit Type",
            "Bank",
            "Amount",
            "Status",
            "Updated Time",
        }

        if not required.issubset(
            deposits.columns
        ):
            return pd.DataFrame(columns=columns)

        df = deposits.copy()

        # Date
        df = self.filter_by_updated_time(
            df,
            from_date,
            to_date,
            "Updated Time"
        )

        # Successful only
        df = df[
            self.normalize_status(
                df["Status"]
            ) == "successful"
        ]

        # Bank
        df["Bank_Normalized"] = (
            self.normalize_bank(
                df["Bank"]
            )
        )

        # Amount
        df["Amount"] = pd.to_numeric(
            df["Amount"],
            errors="coerce"
        ).fillna(0)

        # Only requested banks
        df = df[
            df["Bank_Normalized"].isin(
                self.DEPOSIT_BANKS
            )
        ]

        pivot = df.pivot_table(
            index="Deposit Type",
            columns="Bank_Normalized",
            values="Amount",
            aggfunc="sum",
            fill_value=0,
        )

        for bank in self.DEPOSIT_BANKS:
            if bank not in pivot.columns:
                pivot[bank] = 0

        pivot = pivot[
            self.DEPOSIT_BANKS
        ]

        pivot.reset_index(inplace=True)

        return pivot[
            columns
        ]

    # ========================================================
    # UNKNOWN ACCOUNTS
    # ========================================================

    def find_unknown_accounts(self, from_date=None, to_date=None):
        """Find valid wallet accounts from Deposit J / Payout K that are absent from master."""
        master = self.data.dataframes.get("Wallet Account Master List")
        deposits = self.data.dataframes.get("Deposit History")
        payouts = self.data.dataframes.get("Pay Out History")

        master_accounts = set()
        if master is not None and "WALLETNAME" in master.columns:
            master_accounts = set(
                master["WALLETNAME"].astype(str).str.strip().str.upper()
            )

        discovered = []
        if deposits is not None and "To Account" in deposits.columns:
            dep = self.filter_by_updated_time(deposits, from_date, to_date, "Updated Time")
            discovered.extend(dep["To Account"].apply(self.clean_wallet_account).dropna().tolist())
        if payouts is not None and "From Account" in payouts.columns:
            pay = self.filter_by_updated_time(payouts, from_date, to_date, "Updated Time")
            discovered.extend(pay["From Account"].apply(self.clean_wallet_account).dropna().tolist())

        unknown = [x for x in dict.fromkeys(discovered) if x not in master_accounts]
        return pd.DataFrame({"Wallet Account": unknown})

    @staticmethod
    def _parse_stop_date_and_remarks(value):
        """Extract date + non-date text from parentheses in Short Name (column H)."""
        if pd.isna(value):
            return "", ""

        text = str(value).strip()
        groups = re.findall(r"\(([^)]*)\)", text)
        if not groups:
            return "", ""

        date_pattern = re.compile(
            r"(?<!\d)(?:"
            r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
            r"|\d{1,2}[/-]\d{2,4}"
            r"|\d{4}[/-]\d{1,2}[/-]\d{1,2}"
            r")(?!\d)"
        )

        stop_date = ""
        remarks_parts = []

        for group in groups:
            cleaned = group.strip()
            match = date_pattern.search(cleaned)
            if match and not stop_date:
                raw_date = match.group(0)
                # Keep ambiguous dates in their original form rather than silently
                # swapping day/month. Unambiguous dates are normalized to DD/MM/YY.
                try:
                    parts = re.split(r"[/-]", raw_date)
                    if len(parts) == 3:
                        a, b, c = parts
                        if len(c) == 4 and len(a) == 4:
                            parsed = pd.to_datetime(raw_date, errors="coerce")
                        elif int(a) > 12:
                            parsed = pd.to_datetime(f"{a}/{b}/{c}", dayfirst=True, errors="coerce")
                        elif int(b) > 12:
                            parsed = pd.to_datetime(f"{a}/{b}/{c}", dayfirst=False, errors="coerce")
                        else:
                            parsed = pd.to_datetime(f"{a}/{b}/{c}", dayfirst=True, errors="coerce")
                        if pd.notna(parsed):
                            stop_date = parsed.strftime("%d/%m/%y")
                        else:
                            stop_date = raw_date
                    elif len(parts) == 2:
                        parsed = pd.to_datetime(raw_date, format=None, errors="coerce")
                        stop_date = parsed.strftime("%m/%y") if pd.notna(parsed) else raw_date
                    else:
                        stop_date = raw_date
                except Exception:
                    stop_date = raw_date

                cleaned = date_pattern.sub("", cleaned, count=1)

            cleaned = re.sub(r"\s*[-–—:]\s*$", "", cleaned).strip(" -–—:;,")
            cleaned = re.sub(r"\s{2,}", " ", cleaned)
            if cleaned:
                remarks_parts.append(cleaned)

        remarks = " | ".join(dict.fromkeys(remarks_parts))
        return stop_date, remarks

    def generate_locked_disabled_result_uncached(self):
        """Build the requested Locked/Disabled export from columns E/F/H/I/K.

        E = Bank Code
        F = Account Name
        H = Short Name (source for Stop Date + Remarks)
        I = Account Number
        K = Status
        """
        frames = []

        for dataset_name in ("Active Accounts", "Locked Accounts", "Disabled Accounts"):
            source = self.data.dataframes.get(dataset_name)
            if source is None or source.empty:
                continue

            required = {"Account Name", "Bank Code", "Short Name", "Account Number", "Status"}
            missing = required - set(source.columns)
            if missing:
                # If the import has positional/blank headers, map the requested Excel
                # columns E/F/H/I/K by position as a fallback.
                if len(source.columns) >= 11:
                    temp = source.iloc[:, [4, 5, 7, 8, 10]].copy()
                    temp.columns = ["Bank Code", "Account Name", "Short Name", "Account Number", "Status"]
                else:
                    raise ValueError(
                        f"{dataset_name} is missing required columns: {', '.join(sorted(missing))}."
                    )
            else:
                temp = source[["Bank Code", "Account Name", "Short Name", "Account Number", "Status"]].copy()

            parsed = temp["Short Name"].apply(self._parse_stop_date_and_remarks)
            temp["Stop Date"] = parsed.apply(lambda x: x[0])
            temp["Remarks"] = parsed.apply(lambda x: x[1])

            result = temp[["Account Name", "Bank Code", "Account Number", "Stop Date", "Status", "Remarks"]].copy()

            # The three imported datasets are separate sources/pages. Normalize the
            # displayed status from the dataset itself so values such as "Disable"
            # in the source still appear on the Disabled Accounts page and in the
            # corresponding Google Sheets tab.
            canonical_status = {
                "Active Accounts": "Active",
                "Locked Accounts": "Locked",
                "Disabled Accounts": "Disabled",
            }.get(dataset_name)
            if canonical_status:
                result["Status"] = canonical_status

            # Only export genuine wallet/account names in the required format,
            # e.g. HORSE-NG-040. Ignore masked/invalid names such as *****,
            # 0*****, ****/****, or other non-wallet account names.
            account_clean = result["Account Name"].astype(str).str.strip().str.upper()
            valid_wallet = account_clean.str.fullmatch(r"[A-Z0-9]+-[A-Z]{2}-[0-9]{3}", na=False)
            result = result.loc[valid_wallet].copy()
            result["Account Name"] = account_clean.loc[valid_wallet].values

            frames.append(result)

        if not frames:
            return pd.DataFrame(columns=["Account Name", "Bank Code", "Account Number", "Stop Date", "Status", "Remarks"])

        return pd.concat(frames, ignore_index=True)


# Cached public wrapper for the relatively expensive Active/Locked/Disabled transformation.
# Cache invalidates whenever operational data is imported or cleared.
def _generate_locked_disabled_cached(self):
    cached = self._cached('locked_disabled')
    if cached is not None:
        return cached.copy()
    result = self.generate_locked_disabled_result_uncached()
    self.data.locked_disabled_result = result
    return self._store_cache('locked_disabled', result)

BusinessLogic.generate_locked_disabled_result = _generate_locked_disabled_cached