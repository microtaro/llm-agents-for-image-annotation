// Read one API path; reload() reads it again. A null path reads nothing. The data is kept in
// TanStack Query's cache, keyed by the path's parts, so every part showing the same path
// shares it, and invalidate() reads again everything of a dataset after the AI or a run
// changed it (trial of TanStack Query, 2026-10-06).
import { keepPreviousData, QueryClient, useQuery } from "@tanstack/react-query";
import { useCallback } from "react";
import { api, ApiError } from "@/api/client";

export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: 0 } },
});

// How long a read may take before it is given up (2026-10-29: reads that never answered, after
// the dev server restarted under the page, held the browser's connections, and every read after
// them queued until the browser refused them all).
const READ_MS = 30_000;

/** A read of the cache: stopped when the cache drops it (a newer read of the same path) or when
 * it takes longer than READ_MS. */
export function readApi<T>(path: string, signal: AbortSignal, body?: unknown): Promise<T> {
  return api<T>(path, { body, signal: AbortSignal.any([signal, AbortSignal.timeout(READ_MS)]) });
}

export interface Loaded<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  /** The data is the previous path's, shown while this one loads (keepPreviousData). */
  previous: boolean;
  reload: () => void;
}

/** "/v1/datasets/d1/runs" -> ["v1", "datasets", "d1", "runs"]: a dataset's paths share a head. */
export const keyOf = (path: string) => path.split("/").filter(Boolean);

export function useApi<T>(path: string | null): Loaded<T> {
  const result = useQuery<T, ApiError>({
    queryKey: path === null ? ["none"] : keyOf(path),
    queryFn: ({ signal }) => readApi<T>(path!, signal),
    enabled: path !== null,
    placeholderData: keepPreviousData,
  });
  const { refetch } = result;
  // Nothing to read again without a path (refetch does not heed `enabled`: the gallery read
  // "/null" when no run was going, found 2026-10-12).
  const reload = useCallback(() => {
    if (path !== null) void refetch();
  }, [refetch, path]);
  return {
    // What failed to read is not there any more (a deleted draft reads as 404).
    data: path === null || result.error ? null : (result.data ?? null),
    error: result.error ?? null,
    loading: result.isLoading,
    previous: result.isPlaceholderData,
    reload,
  };
}

/** What a POST answers without changing anything (a decision's preview), shared like a read:
 * the same path and body are one entry, read again with the dataset's paths (invalidate). */
export function usePosted<T>(path: string | null, body: unknown): Loaded<T> {
  const key = JSON.stringify(body);
  const result = useQuery<T, ApiError>({
    queryKey: path === null ? ["none"] : [...keyOf(path), key],
    queryFn: ({ signal }) => readApi<T>(path!, signal, body),
    enabled: path !== null,
    placeholderData: keepPreviousData,
  });
  const { refetch } = result;
  const reload = useCallback(() => {
    if (path !== null) void refetch();
  }, [refetch, path]);
  return {
    data: path === null || result.error ? null : (result.data ?? null),
    error: result.error ?? null,
    loading: result.isLoading,
    previous: result.isPlaceholderData,
    reload,
  };
}

/** Read again every path of a dataset (and its runs), e.g. when the AI has answered; or only
 * the paths under a part of it (invalidate(id, "drafts") after the draft is written). */
export function invalidate(datasetId: string, ...under: string[]): void {
  void queryClient.invalidateQueries({ queryKey: ["v1", "datasets", datasetId, ...under] });
  if (!under.length) {
    void queryClient.invalidateQueries({ queryKey: ["v1", "runs"] });
    // The person's turns count every dataset's (definition 44.1).
    void queryClient.invalidateQueries({ queryKey: ["v1", "turns"] });
  }
}
