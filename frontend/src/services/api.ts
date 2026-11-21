import axios, { AxiosError, type AxiosRequestConfig } from 'axios';
import type {
  AnalyticsSummary,
  ApiResponse,
  BayesianModelInfo,
  BayesianPrediction,
  CptRow,
  CspRunResult,
  Distributor,
  HealthPayload,
  KMeansRunResult,
  OfficeLocation,
  OptimizePreviewResponse,
  PaginationMeta,
  RouteDelayResponse,
  RoutePlanDetailPayload,
  RoutePlanSummary,
} from '../types';

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

const http = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

function extractAxiosErrorMessage(err: unknown): string {
  if (err instanceof AxiosError) {
    const body = err.response?.data as ApiResponse<unknown> | undefined;
    if (body?.error?.message) {
      return body.error.message;
    }
    if (err.response?.status) {
      return `Request failed with status ${err.response.status}`;
    }
    return err.message || 'Network request failed';
  }
  if (err instanceof Error) return err.message;
  return 'Unexpected API error';
}

async function request<T>(
  config: AxiosRequestConfig
): Promise<{ data: T; message?: string }> {
  try {
    const res = await http.request<ApiResponse<T>>(config);
    const json = res.data;
    if (!json.success) {
      throw new Error(json.error?.message || `Request failed with status ${res.status}`);
    }
    return { data: json.data as T, message: json.message };
  } catch (err) {
    throw new Error(extractAxiosErrorMessage(err));
  }
}

export async function fetchHealth(): Promise<HealthPayload> {
  try {
    const res = await http.get<ApiResponse<HealthPayload>>('/api/health');
    if (res.data?.data) return res.data.data;
    throw new Error(res.data?.error?.message || 'Unable to check health');
  } catch (err) {
    if (err instanceof AxiosError && err.response?.data) {
      const payload = err.response.data as ApiResponse<HealthPayload>;
      if (payload.data) return payload.data;
    }
    throw new Error(extractAxiosErrorMessage(err));
  }
}

export const distributorsExportUrl = `${API_BASE_URL}/api/distributors/export`;

export const api = {
  initDatabase: () =>
    request<{ applied: string[]; database: HealthPayload['database'] }>({
      url: '/api/db/init',
      method: 'POST',
    }),
  loadDemoData: () => request({ url: '/api/demo/load', method: 'POST' }),
  clearDemoData: () => request({ url: '/api/demo/clear', method: 'POST' }),

  getOffices: () =>
    request<{ offices: OfficeLocation[]; defaultOffice: OfficeLocation | null }>({
      url: '/api/office',
      method: 'GET',
    }),
  createOffice: (body: Omit<OfficeLocation, 'id' | 'is_demo' | 'created_at' | 'updated_at'>) =>
    request<OfficeLocation>({ url: '/api/office', method: 'POST', data: body }),
  updateOffice: (
    id: string,
    body: Omit<OfficeLocation, 'id' | 'is_demo' | 'created_at' | 'updated_at'>
  ) => request<OfficeLocation>({ url: `/api/office/${id}`, method: 'PUT', data: body }),

  getDistributors: (
    params: {
      search?: string;
      active?: 'all' | 'true' | 'false';
      sortBy?: string;
      sortDir?: 'asc' | 'desc';
      page?: number;
      pageSize?: number;
    } = {}
  ) =>
    request<{ items: Distributor[]; pagination: PaginationMeta }>({
      url: '/api/distributors',
      method: 'GET',
      params,
    }),
  createDistributor: (body: Record<string, unknown>) =>
    request<Distributor>({ url: '/api/distributors', method: 'POST', data: body }),
  updateDistributor: (id: string, body: Record<string, unknown>) =>
    request<Distributor>({ url: `/api/distributors/${id}`, method: 'PUT', data: body }),
  deleteDistributor: (id: string) =>
    request<{ id: string }>({ url: `/api/distributors/${id}`, method: 'DELETE' }),
  importDistributorsCsv: (csv: string) =>
    request<{ importedCount: number }>({
      url: '/api/distributors/import',
      method: 'POST',
      data: { csv },
    }),

  runClustering: (body: {
    distributorIds: string[];
    k: number;
    seed: number;
    maxIterations: number;
    initMethod: 'kmeans++' | 'random';
  }) => request<KMeansRunResult>({ url: '/api/clusters/run', method: 'POST', data: body }),
  getLatestClusters: () =>
    request<{
      routePlanId: string;
      k: number;
      centroids: KMeansRunResult['centroids'];
      assignments: KMeansRunResult['assignments'];
    } | null>({ url: '/api/clusters/latest', method: 'GET' }),

  runSchedule: (body: {
    distributorIds: string[];
    scheduleDate: string;
    workStartTime: string;
    workEndTime: string;
    slotIncrementMinutes: number;
    travelBufferMinutes: number;
    lunchBreakEnabled: boolean;
    lunchStartTime: string;
    lunchDurationMinutes: number;
    maxVisitsPerDay: number;
    routePlanId?: string | null;
  }) => request<CspRunResult>({ url: '/api/schedules/run', method: 'POST', data: body }),
  getLatestSchedule: () =>
    request<{
      routePlanId: string;
      scheduleDate: string;
      entries: Array<{
        id: string;
        distributor_id: string;
        distributor_name: string;
        priority: number;
        start_time: string;
        end_time: string;
        visit_duration_minutes: number;
        opening_time: string;
        closing_time: string;
        schedule_date: string;
        constraint_notes: string;
      }>;
    } | null>({ url: '/api/schedules/latest', method: 'GET' }),

  previewOptimization: (body: {
    officeId: string;
    distributorIds: string[];
    seed: number;
    distanceMultiplier: number;
    travelMode: 'simulated_vehicle' | 'simulated_walking' | 'simulated_van';
    returnToOffice: boolean;
    gaPopulationSize: number;
    gaGenerations: number;
    gaMutationRate: number;
  }) => request<OptimizePreviewResponse>({ url: '/api/optimize/preview', method: 'POST', data: body }),

  getRoutePlans: (page = 1, pageSize = 20) =>
    request<{ items: RoutePlanSummary[]; pagination: PaginationMeta }>({
      url: '/api/route-plans',
      method: 'GET',
      params: { page, pageSize },
    }),
  createRoutePlan: (body: {
    name: string;
    planDate: string;
    officeId: string;
    distributorIds: string[];
    travelMode: 'simulated_vehicle' | 'simulated_walking' | 'simulated_van';
    returnToOffice: boolean;
    distanceMultiplier: number;
    graphSeed: number;
    notes?: string;
  }) => request<RoutePlanSummary>({ url: '/api/route-plans', method: 'POST', data: body }),
  optimizeRoutePlan: (id: string, body: Record<string, unknown> = {}) =>
    request({ url: `/api/route-plans/${id}/optimize`, method: 'POST', data: body }),
  getRoutePlanDetail: (id: string) =>
    request<RoutePlanDetailPayload>({ url: `/api/route-plans/${id}`, method: 'GET' }),
  updateRoutePlan: (id: string, body: Record<string, unknown>) =>
    request<RoutePlanSummary>({ url: `/api/route-plans/${id}`, method: 'PUT', data: body }),
  deleteRoutePlan: (id: string) =>
    request<{ id: string }>({ url: `/api/route-plans/${id}`, method: 'DELETE' }),
  updateStopStatus: (stopId: string, status: 'pending' | 'visited' | 'skipped', notes?: string) =>
    request({
      url: `/api/route-stops/${stopId}/status`,
      method: 'PATCH',
      data: { status, notes },
    }),

  getAnalyticsSummary: () =>
    request<AnalyticsSummary>({ url: '/api/analytics/summary', method: 'GET' }),

  getModelInfo: () =>
    request<BayesianModelInfo>({ url: '/api/predictions/model-info', method: 'GET' }),
  getCptTable: () =>
    request<{ modelVersion: string; totalRows: number; validationStatus: string; rows: CptRow[] }>({
      url: '/api/predictions/cpt',
      method: 'GET',
    }),
  predictVisitDelay: (body: Record<string, unknown>) =>
    request<BayesianPrediction>({
      url: '/api/predictions/visit-delay',
      method: 'POST',
      data: body,
    }),
  predictRouteDelay: (body: { routePlanId: string; saveToDb?: boolean }) =>
    request<RouteDelayResponse>({
      url: '/api/predictions/route-delay',
      method: 'POST',
      data: body,
    }),
  getPredictionHistory: (params: { routePlanId?: string; limit?: number } = {}) =>
    request<{ items: BayesianPrediction[]; count: number }>({
      url: '/api/predictions/visit-delay/history',
      method: 'GET',
      params,
    }),
};
