import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";

/** GET `path` with the token; re-fetches whenever `path` changes. */
export function useFetch<T>(path: string | null, token: string) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const seq = useRef(0);

  const load = useCallback(async () => {
    if (!path) return;
    const my = ++seq.current;
    setLoading(true);
    setError("");
    try {
      const d = await apiFetch<T>(path, token);
      if (my === seq.current) setData(d);
    } catch (e) {
      if (my === seq.current) setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      if (my === seq.current) setLoading(false);
    }
  }, [path, token]);

  useEffect(() => { load(); }, [load]);
  return { data, loading, error, reload: load, setData };
}

/** Debounce a fast-changing value (search boxes). */
export function useDebounced<T>(value: T, ms = 350): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
