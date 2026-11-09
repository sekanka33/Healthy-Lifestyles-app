import { useCallback, useEffect, useState } from 'react';
import { ApiError } from './api';
import { useAuth } from './auth';

export interface QueryState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

/** GET `path` with the admin session; refetches when `path` changes. Keeps the previous data while reloading. */
export function useApiQuery<T>(path: string | null): QueryState<T> {
  const { request } = useAuth();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(!!path);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!path) return;
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    request<T>(path, { signal: ctrl.signal })
      .then((d) => setData(d))
      .catch((e) => {
        if ((e as Error).name === 'AbortError') return;
        setError(e instanceof ApiError ? e : new ApiError(0, 'unknown', 'Something went wrong.'));
      })
      .finally(() => { if (!ctrl.signal.aborted) setLoading(false); });
    return () => ctrl.abort();
  }, [path, request, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading, reload };
}
