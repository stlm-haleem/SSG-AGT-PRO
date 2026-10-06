import { useCallback, useMemo, useState } from "react";
import type { Role } from "@/types/api";

export interface AuthState {
  token: string | null;
  role: Role | null;
  username: string | null;
  permissions: Set<string>;
  isAdmin: boolean;
  can: (key: string) => boolean;
  /** ISO timestamp of this user's most recent Generate Summary ("" when none yet) */
  lastGenerate: string;
  setLastGenerate: (v: string) => void;
  login: (token: string, role: Role, username: string, permissions: string[], isAdmin: boolean, lastGenerate?: string) => void;
  logout: () => void;
}

const read = (k: string) => localStorage.getItem(k);

export function useAuth(): AuthState {
  const [token, setToken] = useState<string | null>(() => read("ssg_token"));
  const [role, setRole] = useState<Role | null>(() => read("ssg_role"));
  const [username, setUsername] = useState<string | null>(() => read("ssg_username"));
  const [perms, setPerms] = useState<string[]>(() => {
    try { return JSON.parse(read("ssg_perms") || "[]"); } catch { return []; }
  });
  const [isAdmin, setIsAdmin] = useState<boolean>(() => read("ssg_admin") === "1");
  const [lastGenerate, setLastGenerateState] = useState<string>(() => read("ssg_last_generate") || "");

  const setLastGenerate = (v: string) => {
    localStorage.setItem("ssg_last_generate", v || "");
    setLastGenerateState(v || "");
  };

  const login: AuthState["login"] = (t, r, u, p, a, lg = "") => {
    localStorage.setItem("ssg_token", t);
    localStorage.setItem("ssg_role", r);
    localStorage.setItem("ssg_username", u);
    localStorage.setItem("ssg_perms", JSON.stringify(p));
    localStorage.setItem("ssg_admin", a ? "1" : "0");
    localStorage.setItem("ssg_last_generate", lg);
    setToken(t); setRole(r); setUsername(u); setPerms(p); setIsAdmin(a); setLastGenerateState(lg);
  };

  const logout = () => {
    ["ssg_token", "ssg_role", "ssg_username", "ssg_perms", "ssg_admin", "ssg_last_generate"].forEach((k) => localStorage.removeItem(k));
    setToken(null); setRole(null); setUsername(null); setPerms([]); setIsAdmin(false); setLastGenerateState("");
  };

  const permissions = useMemo(() => new Set(perms), [perms]);
  const can = useCallback((key: string) => isAdmin || permissions.has(key), [isAdmin, permissions]);

  return { token, role, username, permissions, isAdmin, can, lastGenerate, setLastGenerate, login, logout };
}
