import { apiRequest } from "./client";
import type { ClaimsDashboard, DashboardOverview, OperationsDashboard } from "./types";

export interface DashboardFilters {
  startDate?: string;
  endDate?: string;
}

function queryString(filters: DashboardFilters): string {
  const params = new URLSearchParams();
  if (filters.startDate) params.set("start_date", filters.startDate);
  if (filters.endDate) params.set("end_date", filters.endDate);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function getDashboardOverview(
  filters: DashboardFilters = {},
  signal?: AbortSignal,
): Promise<DashboardOverview> {
  return apiRequest(`/api/dashboards/overview${queryString(filters)}`, {}, signal);
}

export function getClaimsDashboard(
  filters: DashboardFilters = {},
  signal?: AbortSignal,
): Promise<ClaimsDashboard> {
  return apiRequest(`/api/dashboards/claims${queryString(filters)}`, {}, signal);
}

export function getOperationsDashboard(
  filters: DashboardFilters = {},
  signal?: AbortSignal,
): Promise<OperationsDashboard> {
  return apiRequest(`/api/dashboards/operations${queryString(filters)}`, {}, signal);
}
