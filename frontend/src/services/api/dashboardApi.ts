import { legacyApiGet, type QueryParams, type RequestOptions } from '../../api/client';

const DASHBOARD_TIMEOUT_MS = 30000;
const DASHBOARD_REFRESH_TIMEOUT_MS = 150000;

export function fetchDashboardMovers<T>(
  params: QueryParams = {},
  options: RequestOptions = {},
): Promise<T> {
  const isRefresh = Boolean(params.refresh);
  return legacyApiGet<T>('/api/dashboard/movers', params, {
    timeoutMs: isRefresh ? DASHBOARD_REFRESH_TIMEOUT_MS : DASHBOARD_TIMEOUT_MS,
    ...options,
  });
}
