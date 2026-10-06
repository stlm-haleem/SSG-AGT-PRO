import { useState, type FormEvent } from "react";
import { Eye, EyeOff, Loader2, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { LoginResponse, Role } from "@/types/api";

interface LoginScreenProps {
  onLogin: (token: string, role: Role, username: string, permissions: string[], isAdmin: boolean, lastGenerate?: string) => void;
}

export function LoginScreen({ onLogin }: LoginScreenProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (!username.trim() || !password) {
      setError("Enter username and password.");
      return;
    }
    setLoading(true);
    try {
      const body = new URLSearchParams({ username, password });
      const res = await fetch("/api/auth/login", {
        method: "POST",
        body,
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Invalid username or password.");
      }
      const data: LoginResponse = await res.json();
      onLogin(data.access_token, data.role, data.username, data.permissions ?? [], !!data.is_admin, data.last_generate_at ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-bg relative flex min-h-screen items-center justify-center overflow-hidden p-4">
      <div className="pointer-events-none absolute -top-40 left-1/2 h-[520px] w-[820px] -translate-x-1/2 rounded-full bg-gradient-to-br from-indigo-500/25 via-violet-500/20 to-fuchsia-500/20 blur-3xl" />
      <div className="fade-in surface relative w-full max-w-sm p-8">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-500 text-white shadow-lg shadow-indigo-500/30">
            <Wallet className="h-7 w-7" />
          </div>
          <h1 className="text-lg font-semibold tracking-tight">SSG AGT Pro</h1>
          <p className="mt-1 text-sm text-muted-foreground">Sign in to your account</p>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="username">Username</Label>
            <Input id="username" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus autoComplete="username" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <div className="relative">
              <Input
                id="password"
                type={showPw ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                className="pr-9"
              />
              <button
                type="button"
                onClick={() => setShowPw((s) => !s)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
          {error && <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" disabled={loading}>
            {loading && <Loader2 className="h-4 w-4 animate-spin" />} {loading ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </div>
    </div>
  );
}
