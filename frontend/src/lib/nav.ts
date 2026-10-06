import {
  Activity, AlertOctagon, Archive, BadgeCheck, BarChart3, Banknote, Building2, ClipboardList, Database, FileSpreadsheet,
  Ban, Gauge, Gem, HelpCircle, Hourglass, KeyRound, LayoutDashboard, LineChart, ListChecks, Lock, PlugZap, Radar, ScrollText,
  ShieldCheck, ShieldAlert, Sigma, TableProperties, Upload, UserCog, Users, Wallet, WalletCards, type LucideIcon,
} from "lucide-react";

export interface NavItem {
  route: string;
  label: string;
  icon: LucideIcon;
  /** any-of permission keys */
  perm: string | string[];
}
export interface NavGroup {
  id: string;
  label: string;
  items: NavItem[];
}

export const NAV: NavGroup[] = [
  {
    id: "command",
    label: "Command",
    items: [{ route: "command", label: "Command Center", icon: LayoutDashboard, perm: "dashboard" }],
  },
  {
    id: "cih",
    label: "CIH Overview",
    items: [
      { route: "cih/summary", label: "Summary", icon: Sigma, perm: "cih_summary" },
      { route: "cih/agent", label: "Agent Wallets", icon: WalletCards, perm: "cih_agent" },
      { route: "cih/personal", label: "Personal Wallets", icon: Banknote, perm: "cih_personal" },
      { route: "cih/limit-availability", label: "Limit Availability", icon: BarChart3, perm: "cih_limit_availability" },
    ],
  },
  {
    id: "monitoring",
    label: "Account Monitoring",
    items: [
      { route: "monitoring/agent", label: "Agent Accounts", icon: Building2, perm: "monitoring_agent" },
      { route: "monitoring/personal", label: "Personal Accounts", icon: Users, perm: "monitoring_personal" },
      { route: "monitoring/vip", label: "VIP Accounts", icon: Gem, perm: "monitoring_vip" },
      { route: "monitoring/withdrawal", label: "Withdrawal Only", icon: Activity, perm: "monitoring_withdrawal" },
      { route: "monitoring/permanent-stop", label: "Permanent Stop", icon: Ban, perm: "monitoring_permanent_stop" },
    ],
  },
  {
    id: "overview",
    label: "Account Overview",
    items: [
      { route: "overview/agent", label: "Agent Overview", icon: LineChart, perm: "overview_agent" },
      { route: "overview/personal", label: "Personal Overview", icon: LineChart, perm: "overview_personal" },
      { route: "overview/high-discrepancy", label: "High Discrepancy", icon: AlertOctagon, perm: "overview_high_discrepancy" },
      { route: "overview/limit-reached", label: "Limit Reached", icon: ShieldAlert, perm: "overview_limit_reached" },
    ],
  },
  {
    id: "data",
    label: "Data",
    items: [
      { route: "data/import", label: "Data Import", icon: Database, perm: ["imports_data", "imports_master", "imports_closed", "imports_google_sync", "imports_telegram_reports"] },
      { route: "data/active", label: "Active Accounts", icon: BadgeCheck, perm: "imports_active" },
      { route: "data/locked", label: "Locked Accounts", icon: Lock, perm: "imports_locked" },
      { route: "data/disabled", label: "Disabled Accounts", icon: ShieldAlert, perm: "imports_disabled" },
      { route: "data/statements", label: "Generated Statements", icon: FileSpreadsheet, perm: "imports_statement" },
    ],
  },
  {
    id: "master",
    label: "Masterlist",
    items: [
      { route: "master/list", label: "Master List", icon: TableProperties, perm: "master_list" },
      { route: "master/pending", label: "Pending Accounts", icon: Hourglass, perm: "pending" },
      { route: "master/unknown", label: "Unknown Accounts", icon: HelpCircle, perm: "unknown" },
      { route: "master/closed", label: "Permanently Closed", icon: Archive, perm: "closed" },
    ],
  },
  {
    id: "admin",
    label: "Administration",
    items: [
      { route: "admin/users", label: "Users", icon: UserCog, perm: "admin_users" },
      { route: "admin/roles", label: "Roles & Permissions", icon: ShieldCheck, perm: "admin_roles" },
      { route: "admin/integrations", label: "Integrations", icon: PlugZap, perm: "admin_integrations" },
    ],
  },
];

export const ALL_ITEMS = NAV.flatMap((g) => g.items.map((i) => ({ ...i, group: g.label })));
export const iconFallback = { ClipboardList, KeyRound, ListChecks };

export function allowed(item: NavItem, can: (k: string) => boolean): boolean {
  return (Array.isArray(item.perm) ? item.perm : [item.perm]).some(can);
}
