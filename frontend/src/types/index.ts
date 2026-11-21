export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  message?: string;
  error?: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export interface DatabaseHealth {
  configured: boolean;
  connected: boolean;
  schemaReady: boolean;
  missingTables: string[];
  existingTables: string[];
  latencyMs: number | null;
  message: string;
}

export interface HealthPayload {
  app: string;
  database: DatabaseHealth;
}

export interface OfficeLocation {
  id: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  is_default: boolean;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
}

export interface Distributor {
  id: string;
  name: string;
  contact_person: string;
  phone: string;
  email: string | null;
  address: string;
  latitude: number;
  longitude: number;
  priority: number;
  visit_duration_minutes: number;
  opening_time: string;
  closing_time: string;
  is_active: boolean;
  notes: string;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
}

export interface PaginationMeta {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

export interface ClusterCentroid {
  clusterIndex: number;
  clusterLabel: string;
  centroidLat: number;
  centroidLng: number;
  count: number;
}

export interface ClusterAssignment {
  distributorId: string;
  distributorName: string;
  latitude: number;
  longitude: number;
  clusterIndex: number;
  clusterLabel: string;
  distanceToCentroidKm: number;
}

export interface KMeansRunResult {
  routePlanId?: string;
  k: number;
  seed: number;
  initMethod: 'kmeans++' | 'random';
  maxIterations: number;
  iterations: number;
  converged: boolean;
  totalWcss: number;
  centroids: ClusterCentroid[];
  assignments: ClusterAssignment[];
  iterationHistory: Array<{ iteration: number; inertia: number; reassignedCount: number }>;
}

export interface ScheduledVisitEntry {
  distributorId: string;
  distributorName: string;
  priority: number;
  startTime: string;
  endTime: string;
  startMinutes: number;
  endMinutes: number;
  durationMinutes: number;
  bufferMinutes: number;
  openingTime: string;
  closingTime: string;
  distanceKm?: number;
  delayRisk?: 'Low' | 'Medium' | 'High';
  delayProbabilities?: { Low: number; Medium: number; High: number };
  recommendedBufferMinutes?: number;
  delayAdvisory?: string;
}

export interface UnscheduledVisitReport {
  distributorId: string;
  distributorName: string;
  priority: number;
  visitDurationMinutes: number;
  openingTime: string;
  closingTime: string;
  reason: string;
}

export interface CspRunResult {
  routePlanId?: string;
  scheduleRunId?: string;
  scheduleDate: string;
  allDistributorsScheduled: boolean;
  usesFixedTravelBuffer: boolean;
  scheduled: ScheduledVisitEntry[];
  unscheduled: UnscheduledVisitReport[];
  backtracks: number;
  executionTimeMs: number;
  constraintsSummary: string;
  bayesianAdvisory?: {
    evaluatedCount: number;
    highRiskCount: number;
    highRiskDistributors: string[];
    recommendedTravelBuffer: number;
    hasHighRisk: boolean;
    recommendationText: string;
    advisoryDetails: string[];
  };
}

export interface GraphNode {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  isOffice: boolean;
  visitDurationMinutes?: number;
}

export type AlgorithmName = 'BFS' | 'UCS' | 'A*' | 'GENETIC_ALGORITHM';

export interface AlgorithmComparisonItem {
  algorithm: AlgorithmName;
  isInformed: boolean;
  isHeuristic?: boolean;
  isOptimalForObjective: boolean;
  objectiveDescription: string;
  routeOrder: number[];
  totalCost: number;
  estimatedDistanceKm: number;
  estimatedDurationMinutes: number;
  edgeCount: number;
  nodesExpanded: number;
  executionTimeMs: number;
  completed: boolean;
  warning?: string;
  generationsRun?: number;
  convergenceHistory?: Array<{ generation: number; bestCost: number }>;
}

export interface OptimizePreviewResponse {
  nodes: GraphNode[];
  matrix: {
    distanceKm: number[][];
    durationMinutes: number[][];
    straightLineKm: number[][];
    cacheHit: boolean;
    speedKmh: number;
    seed: number;
    distanceMultiplier: number;
    travelMode: 'simulated_vehicle' | 'simulated_walking' | 'simulated_van';
  };
  recommendedAlgorithm: AlgorithmName | null;
  results: AlgorithmComparisonItem[];
  delayPredictions?: BayesianPrediction[];
}

export interface RoutePlanSummary {
  id: string;
  name: string;
  plan_date: string;
  office_id: string;
  office_name?: string;
  office_address?: string;
  office_latitude?: number;
  office_longitude?: number;
  travel_mode: 'simulated_vehicle' | 'simulated_walking' | 'simulated_van';
  return_to_office: boolean;
  recommended_algorithm: AlgorithmName | null;
  selected_algorithm: AlgorithmName | null;
  total_distance_km: number;
  total_duration_minutes: number;
  distance_multiplier: number;
  graph_seed: number;
  status: 'draft' | 'optimized' | 'scheduled' | 'in_progress' | 'completed';
  notes: string;
  is_demo: boolean;
  stop_count?: number;
  visited_count?: number;
  created_at: string;
  updated_at: string;
}

export interface RouteStopDetail {
  id: string;
  route_plan_id: string;
  distributor_id: string | null;
  stop_order: number;
  stop_name: string;
  stop_type: 'office_start' | 'distributor' | 'office_end';
  latitude: number;
  longitude: number;
  estimated_arrival: string | null;
  estimated_departure: string | null;
  estimated_arrival_hhmm: string | null;
  estimated_departure_hhmm: string | null;
  travel_from_previous_minutes: number | null;
  distance_from_previous_km: number | null;
  visit_duration_minutes: number;
  status: 'pending' | 'visited' | 'skipped';
  distributor_address: string | null;
  distributor_priority: number | null;
}

export interface SavedAlgorithmRun {
  id: string;
  route_plan_id: string;
  algorithm_name: AlgorithmName;
  status: string;
  route_order: string[];
  route_names: Array<{ nodeIndex: number; id: string; name: string; isOffice: boolean }>;
  total_cost: number;
  total_distance_km: number;
  estimated_duration_minutes: number;
  nodes_expanded: number;
  execution_time_ms: number;
  parameters: Record<string, unknown>;
  result_details: {
    isInformed?: boolean;
    isRecommended?: boolean;
    objectiveDescription?: string;
    edgeCount?: number;
    isOptimalForObjective?: boolean;
  };
  error_message: string | null;
  created_at: string;
}

export interface RoutePlanDetailPayload {
  plan: RoutePlanSummary;
  stops: RouteStopDetail[];
  algorithms: SavedAlgorithmRun[];
  scheduleEntries: Array<{
    id: string;
    distributor_id: string | null;
    distributor_name: string;
    scheduled_start: string;
    scheduled_end: string;
    visit_duration_minutes: number;
  }>;
  delayPredictions?: BayesianPrediction[];
}

export interface AnalyticsSummary {
  counts: {
    totalDistributors: number;
    activeDistributors: number;
    demoDistributors: number;
    totalRoutePlans: number;
    scheduledOrCompletedPlans: number;
    avgDistanceKm: number | null;
    avgDurationMinutes: number | null;
  };
  latestRoutePlan: RoutePlanSummary | null;
  algorithmAverages: Array<{
    algorithmName: string;
    runCount: number;
    avgCost: number;
    avgDistanceKm: number;
    avgDurationMinutes: number;
    avgNodesExpanded: number;
    avgExecutionMs: number;
  }>;
  recentAlgorithmRuns: Array<SavedAlgorithmRun & { route_plan_name: string }>;
  latestClusters: Array<{
    clusterLabel: string;
    clusterIndex: number;
    size: number;
  }>;
  scheduleSummary: {
    hasRun: boolean;
    scheduledCount: number;
    remainingActiveCount: number;
    scheduleDate: string | null;
  };
  plainLanguageSummary: string[];
}

export interface BayesianPrediction {
  id?: string;
  distributorId?: string | null;
  distributorName: string;
  stopOrder?: number | null;
  routePlanId?: string | null;
  routePlanName?: string | null;
  inputs?: {
    distanceKm?: number | null;
    visitDurationMinutes?: number | null;
    timeSlotRaw?: string | null;
    priorityRaw?: number | null;
  };
  distanceKm?: number | null;
  distanceCategory?: 'Near' | 'Medium' | 'Far';
  visitDurationMinutes?: number | null;
  visitDurationCategory?: 'Short' | 'Medium' | 'Long';
  timeSlot?: 'Morning' | 'Afternoon';
  priorityCategory?: 'Low' | 'Medium' | 'High';
  evidence?: {
    distanceCategory: 'Near' | 'Medium' | 'Far';
    visitDurationCategory: 'Short' | 'Medium' | 'Long';
    timeSlot: 'Morning' | 'Afternoon';
    priorityCategory: 'Low' | 'Medium' | 'High';
  };
  probabilities: {
    Low: number;
    Medium: number;
    High: number;
  };
  predictedRisk: 'Low' | 'Medium' | 'High';
  recommendedBufferMinutes: number;
  recommendation?: string | null;
  explanation?: string | null;
  modelVersion: string;
  modelStatus: string;
  validationStatus?: string;
  createdAt?: string;
}

export interface BayesianModelVariable {
  name: string;
  role: 'parent' | 'target';
  description: string;
  states: string[];
  thresholds?: Record<string, unknown>;
  priors?: Record<string, number>;
  parents?: string[];
}

export interface BayesianModelInfo {
  modelVersion: string;
  modelStatus: string;
  validationStatus: string;
  variables: BayesianModelVariable[];
  topology: {
    nodes: Array<{
      id: string;
      label: string;
      type: 'parent' | 'target';
      states: string[];
      priors?: Record<string, number>;
      parents?: string[];
    }>;
    edges: Array<{ from: string; to: string }>;
    totalCptConfigurations: number;
  };
  thresholds: {
    distance_km: { near_max: number; medium_max: number };
    visit_duration_minutes: { short_max: number; medium_max: number };
    time_slot: { afternoon_cutoff: string };
    priority: { low_max: number; medium_val: number };
  };
  totalCptConfigurations: number;
}

export interface CptRow {
  id: number;
  distance: string;
  visitDuration: string;
  timeSlot: string;
  priority: string;
  pLow: number;
  pMedium: number;
  pHigh: number;
  mostLikely: string;
}

export interface RouteDelayResponse {
  routePlanId: string;
  routePlanName: string;
  totalEvaluated: number;
  summary: {
    lowRiskCount: number;
    mediumRiskCount: number;
    highRiskCount: number;
    highRiskPercentage: number;
    avgHighProbability: number;
    overallRiskLevel: 'Low' | 'Medium' | 'High';
  };
  predictions: BayesianPrediction[];
  modelVersion: string;
  modelStatus: string;
  validationStatus: string;
}

