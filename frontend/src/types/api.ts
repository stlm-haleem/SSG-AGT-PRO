// Shared auth types. Everything else is untyped (`any`) response bodies from
// the SSG AGT API — the shape naturally varies per page (tables, KPIs,
// options), so per-page components type what they need locally.

export type Role = string; // "ADMIN" or any custom role name

export interface LoginResponse {
  access_token: string;
  token_type: string;
  role: Role;
  username: string;
  permissions: string[];
  is_admin: boolean;
  last_generate_at?: string;
}

export interface ApiErrorBody {
  detail?: string | { msg: string }[];
}

export interface UserCreatePayload {
  username: string;
  password: string;
  role: Role;
}

export interface UserUpdatePayload {
  username?: string;
  role?: Role;
  active?: boolean;
  password?: string;
}
