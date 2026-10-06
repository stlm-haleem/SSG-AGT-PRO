"""Permission catalogue for SSG AGT Pro — one entry per page and per destructive
action. Parent keys (``cih``, ``monitoring`` ...) are navigation containers
only — they never grant access to their children. Action keys (``*_edit`` /
``*_delete``) never grant page access by themselves: the matching view key is
required too.
"""

PERMISSION_TREE = [
    ("command", "Command Center", [("dashboard", "Command Center"), ("dashboard_generate", "Generate Dashboard")]),
    ("cih", "CIH Overview", [
        ("cih_summary", "Summary"), ("cih_agent", "Agent Wallet Balances"),
        ("cih_personal", "Personal Wallet Balances"), ("cih_limit_availability", "Limit Availability"),
    ]),
    ("monitoring", "Account Monitoring", [
        ("monitoring_agent", "Agent Accounts"), ("monitoring_personal", "Personal Accounts"),
        ("monitoring_vip", "VIP Accounts"), ("monitoring_withdrawal", "Withdrawal Only"),
        ("monitoring_permanent_stop", "Permanent Stop Accounts"),
    ]),
    ("overview", "Account Overview", [
        ("overview_agent", "Agent Account Overview"), ("overview_personal", "Personal Account Overview"),
        ("overview_high_discrepancy", "High Discrepancy"), ("overview_limit_reached", "Limit Reached"),
    ]),
    ("imports", "Data Import", [
        ("imports_data", "Import Data"), ("imports_active", "Active Accounts"),
        ("imports_locked", "Locked Accounts"), ("imports_disabled", "Disabled Accounts"),
        ("imports_statement", "Generated Statements"),
        ("imports_master", "Import Wallet Master List"), ("imports_closed", "Import Permanently Closed"),
        ("imports_google_sync", "Google Sync"), ("imports_telegram_reports", "Telegram Reports"),
        ("imports_edit", "Import / Generate"), ("imports_delete", "Clear Imported Data"),
    ]),
    ("master", "Wallet Masterlist", [
        ("master_list", "Master List"), ("unknown", "Unknown Accounts"),
        ("pending", "Pending Accounts"), ("closed", "Permanently Closed"),
        ("master_edit", "Edit Master List"), ("master_delete", "Delete Master List rows"),
        ("unknown_edit", "Add Unknown to Master"), ("pending_edit", "Update Pending wallet"),
        ("pending_delete", "Delete Pending"), ("closed_edit", "Edit Permanently Closed"),
        ("closed_delete", "Delete Permanently Closed"),
    ]),
    ("admin", "Administration", [
        ("admin_users", "Users"), ("admin_roles", "Manage Roles"), ("admin_integrations", "Integrations"),
        ("admin_users_edit", "Add / Edit Users"), ("admin_users_delete", "Delete Users"),
        ("admin_roles_edit", "Add / Edit Roles"), ("admin_roles_delete", "Delete Roles"),
        ("admin_integrations_edit", "Edit Integration Settings"),
        ("admin_integrations_delete", "Delete Integration Destinations"),
    ]),
]

ALL_KEYS = [k for _, _, items in PERMISSION_TREE for k, _ in items]
ADMIN_KEYS = {k for k in ALL_KEYS if k.startswith("admin")}
LABELS = {k: label for _, _, items in PERMISSION_TREE for k, label in items}

_OPERATIONS = [k for k in ALL_KEYS if k not in ADMIN_KEYS and k not in ("imports_delete", "master_delete", "pending_delete", "closed_delete")]
_VIEWER = [k for k in ALL_KEYS if not k.endswith(("_edit", "_delete", "_generate")) and k not in ADMIN_KEYS
           and not k.startswith("imports_")]

DEFAULT_ROLES = {
    "ADMIN": ALL_KEYS,           # always full access, cannot be edited
    "OPERATION": _OPERATIONS,    # everything except admin + destructive actions
    "User": _OPERATIONS,
    "Viewer": _VIEWER,
}
