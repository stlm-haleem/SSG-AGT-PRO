import { useEffect, useState } from "react";
import { qs } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import type { Table } from "@/components/common/DataTable";
import type { PageMeta } from "@/components/common/Pagination";

export type PagedResponse = Table & PageMeta & { options?: Record<string, string[]>; [k: string]: unknown };

/**
 * Server-paginated list: keeps page/per_page state, resets to page 1 whenever
 * the filter params change, and re-fetches through useFetch.
 */
export function usePaged<T extends PagedResponse = PagedResponse>(
  path: string,
  token: string,
  params: Record<string, string | number | boolean | string[] | undefined | null> = {},
  enabled = true
) {
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(25);
  const filterKey = JSON.stringify(params);
  useEffect(() => setPage(1), [filterKey, perPage]);
  const url = enabled ? `${path}${qs({ ...params, page, per_page: perPage })}` : null;
  const f = useFetch<T>(url, token);
  const meta: PageMeta | null = f.data
    ? { page: f.data.page, per_page: f.data.per_page, total: f.data.total, pages: f.data.pages }
    : null;
  return { ...f, page, setPage, perPage, setPerPage, meta };
}
