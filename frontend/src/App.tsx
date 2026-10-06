import { useEffect, useMemo, useState } from "react";
import { LoginScreen } from "@/components/LoginScreen";
import { Shell } from "@/components/layout/Shell";
import { ToastProvider } from "@/components/common/Toast";
import { EmptyState } from "@/components/common/States";
import { CommandCenter } from "@/components/pages/CommandCenter";
import { CihSummary } from "@/components/pages/CihSummary";
import { CihWallets } from "@/components/pages/CihWallets";
import { LimitAvailability } from "@/components/pages/LimitAvailability";
import { Monitoring } from "@/components/pages/Monitoring";
import { Overview } from "@/components/pages/Overview";
import { DataImport } from "@/components/pages/DataImport";
import { AccountsStatus } from "@/components/pages/AccountsStatus";
import { Statements } from "@/components/pages/Statements";
import { MasterList } from "@/components/pages/MasterList";
import { Pending } from "@/components/pages/Pending";
import { Unknown } from "@/components/pages/Unknown";
import { Closed } from "@/components/pages/Closed";
import { UsersAdmin } from "@/components/pages/UsersAdmin";
import { RolesAdmin } from "@/components/pages/RolesAdmin";
import { IntegrationsAdmin } from "@/components/pages/IntegrationsAdmin";
import { useAuth } from "@/hooks/useAuth";
import { useTheme } from "@/hooks/useTheme";
import { ALL_ITEMS, allowed } from "@/lib/nav";
import { ShieldOff } from "lucide-react";

function firstAllowedRoute(can: (k: string) => boolean): string {
  const item = ALL_ITEMS.find((i) => allowed(i, can));
  return item?.route ?? "command";
}

function AppShellContent({ auth }: { auth: ReturnType<typeof useAuth> }) {
  const theme = useTheme();
  const token = auth.token as string;
  const [route, setRoute] = useState<string>(() => localStorage.getItem("ssg_route") || "");

  useEffect(() => {
    const current = ALL_ITEMS.find((i) => i.route === route);
    if (!route || !current || !allowed(current, auth.can)) {
      setRoute(firstAllowedRoute(auth.can));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { if (route) localStorage.setItem("ssg_route", route); }, [route]);

  const navigate = (r: string) => setRoute(r);

  const page = useMemo(() => {
    switch (route) {
      case "command": return <CommandCenter token={token} can={auth.can} />;

      case "cih/summary": return <CihSummary token={token} />;
      case "cih/agent": return <CihWallets token={token} personal={false} />;
      case "cih/personal": return <CihWallets token={token} personal={true} />;
      case "cih/limit-availability": return <LimitAvailability token={token} />;

      case "monitoring/agent": return <Monitoring token={token} slug="agent" />;
      case "monitoring/personal": return <Monitoring token={token} slug="personal" />;
      case "monitoring/vip": return <Monitoring token={token} slug="vip" />;
      case "monitoring/withdrawal": return <Monitoring token={token} slug="withdrawal" />;
      case "monitoring/permanent-stop": return <Monitoring token={token} slug="permanent-stop" />;

      case "overview/agent": return <Overview token={token} slug="agent" />;
      case "overview/personal": return <Overview token={token} slug="personal" />;
      case "overview/high-discrepancy": return <Overview token={token} slug="high-discrepancy" />;
      case "overview/limit-reached": return <Overview token={token} slug="limit-reached" />;

      case "data/import": return <DataImport token={token} can={auth.can} onGenerated={auth.setLastGenerate} />;
      case "data/active": return <AccountsStatus token={token} slug="active" />;
      case "data/locked": return <AccountsStatus token={token} slug="locked" />;
      case "data/disabled": return <AccountsStatus token={token} slug="disabled" />;
      case "data/statements": return <Statements token={token} />;

      case "master/list": return <MasterList token={token} can={auth.can} />;
      case "master/pending": return <Pending token={token} can={auth.can} />;
      case "master/unknown": return <Unknown token={token} can={auth.can} />;
      case "master/closed": return <Closed token={token} can={auth.can} />;

      case "admin/users": return <UsersAdmin token={token} currentUsername={auth.username ?? ""} />;
      case "admin/roles": return <RolesAdmin token={token} />;
      case "admin/integrations": return <IntegrationsAdmin token={token} />;

      default:
        return (
          <EmptyState
            title="Nothing here yet"
            hint="Choose a section from the sidebar."
            action={<ShieldOff className="mt-2 h-6 w-6 text-muted-foreground" />}
          />
        );
    }
  }, [route, token, auth]);

  return (
    <Shell
      route={route}
      onNavigate={navigate}
      can={auth.can}
      username={auth.username ?? ""}
      role={auth.role ?? ""}
      theme={theme.theme}
      onToggleTheme={theme.toggle}
      onLogout={auth.logout}
      lastGenerate={auth.lastGenerate}
    >
      {page}
    </Shell>
  );
}

export default function App() {
  const auth = useAuth();

  if (!auth.token || !auth.role || !auth.username) {
    return (
      <ToastProvider>
        <LoginScreen onLogin={auth.login} />
      </ToastProvider>
    );
  }

  return (
    <ToastProvider>
      <AppShellContent auth={auth} />
    </ToastProvider>
  );
}
