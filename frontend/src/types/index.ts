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
  dialect?: string | null;
  activeDatabase?: string;
  neonReachable?: boolean;
  neonTablesVerified?: boolean;
  fallbackActive?: boolean;
  fallbackReason?: string | null;
  schemaReady: boolean;
  missingTables: string[];
  existingTables: string[];
  latencyMs: number | null;
  message: string;
}

export interface ProviderAttempt {
  provider: string;
  status: 'succeeded' | 'failed' | 'skipped';
  reason?: string;
}

export interface MapsStatusPayload {
  serverConfigured: boolean;
  googleServerConfigured?: boolean;
  clientKeyConfigured: boolean;
  osrmEnabled?: boolean;
  osrmBaseUrl?: string;
  osrmProfile?: string;
  openRouteServiceConfigured?: boolean;
  providerPriority?: string[];
  provider: RoutingProvider;
  providerLabel?: string;
  fallbackActive: boolean;
  supportedObjectives: OptimizationObjective[];
  defaultObjective: OptimizationObjective;
}

export interface HealthPayload {
  app: string;
  database: DatabaseHealth;
  googleMaps?: MapsStatusPayload;
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
  travelMinutesFromPrevious?: number;
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
  officeId?: string | null;
  officeName?: string | null;
  scheduleDate: string;
  provider?: RoutingProvider;
  providerLabel?: string;
  dataSource?: DataSourceType;
  isLiveTraffic?: boolean;
  durationType?: 'live_traffic' | 'estimated_road_duration' | 'simulated';
  durationLabel?: string;
  trafficCalculatedAt?: string | null;
  calculatedAt?: string | null;
  fallbackReason?: string | null;
  providerAttempts?: ProviderAttempt[];
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
export type OptimizationObjective = 'FASTEST_TIME' | 'SHORTEST_DISTANCE';
export type RoutingProvider = 'google_maps' | 'osrm' | 'openrouteservice' | 'simulated_fallback';
export type DataSourceType =
  | 'google_live_traffic'
  | 'google_road_distance'
  | 'osrm_osm'
  | 'openrouteservice'
  | 'simulated_fallback';
export type TravelMode =
  | 'DRIVE'
  | 'TWO_WHEELER'
  | 'WALK'
  | 'simulated_vehicle'
  | 'simulated_walking'
  | 'simulated_van';

export interface RouteGeometryPayload {
  provider?: RoutingProvider;
  providerLabel?: string;
  encodedPolyline: string | null;
  dataSource: DataSourceType;
  isLiveTraffic?: boolean;
  durationType?: 'live_traffic' | 'estimated_road_duration' | 'simulated';
  durationLabel?: string;
  trafficCalculatedAt: string | null;
  calculatedAt?: string | null;
  distanceKm?: number;
  durationMinutes?: number;
  staticDurationMinutes?: number;
  trafficDelayMinutes?: number;
  routeLabels?: string[];
  fallbackReason?: string | null;
  providerAttempts?: ProviderAttempt[];
  cacheHit?: boolean;
}

export interface AlgorithmComparisonItem {
  algorithm: AlgorithmName;
  isInformed: boolean;
  isHeuristic?: boolean;
  isOptimalForObjective: boolean;
  optimizationObjective?: OptimizationObjective;
  objectiveDescription: string;
  routeOrder: number[];
  totalCost: number;
  estimatedDistanceKm: number;
  estimatedDurationMinutes: number;
  totalStaticDurationMinutes?: number;
  trafficDelayMinutes?: number;
  edgeCount: number;
  nodesExpanded: number;
  executionTimeMs: number;
  completed: boolean;
  warning?: string;
  generationsRun?: number;
  convergenceHistory?: Array<{ generation: number; bestCost: number; unit?: 'min' | 'km' }>;
}

export interface OptimizePreviewResponse {
  nodes: GraphNode[];
  optimizationObjective: OptimizationObjective;
  provider?: RoutingProvider;
  providerLabel?: string;
  dataSource: DataSourceType;
  isLiveTraffic?: boolean;
  durationType?: 'live_traffic' | 'estimated_road_duration' | 'simulated';
  durationLabel?: string;
  trafficCalculatedAt: string | null;
  calculatedAt?: string | null;
  fallbackReason?: string | null;
  providerAttempts?: ProviderAttempt[];
  roadDistanceAvailable?: boolean;
  encodedPolyline?: string | null;
  normalDurationMinutes?: number | null;
  trafficDelayMinutes?: number | null;
  matrix: {
    distanceKm: number[][];
    durationMinutes: number[][];
    staticDurationMinutes?: number[][];
    straightLineKm: number[][];
    cacheHit: boolean;
    speedKmh: number;
    seed: number;
    distanceMultiplier: number;
    travelMode: TravelMode;
    optimizationObjective?: OptimizationObjective;
    provider?: RoutingProvider;
    providerLabel?: string;
    dataSource?: DataSourceType;
    isLiveTraffic?: boolean;
    durationType?: 'live_traffic' | 'estimated_road_duration' | 'simulated';
    durationLabel?: string;
    trafficCalculatedAt?: string | null;
    calculatedAt?: string | null;
    fallbackReason?: string | null;
    roadDistanceAvailable?: boolean;
  };
  recommendedAlgorithm: AlgorithmName | null;
  appliedConfig?: {
    seed: number;
    distanceMultiplier: number;
    travelMode: TravelMode;
    optimizationObjective?: OptimizationObjective;
    provider?: RoutingProvider;
    providerLabel?: string;
    dataSource?: DataSourceType;
    isLiveTraffic?: boolean;
    durationType?: 'live_traffic' | 'estimated_road_duration' | 'simulated';
    durationLabel?: string;
    returnToOffice: boolean;
    gaPopulationSize: number;
    gaGenerations: number;
    gaMutationRate: number;
  };
  results: AlgorithmComparisonItem[];
  delayPredictions?: BayesianPrediction[];
  delayPredictionsByAlgorithm?: Partial<Record<AlgorithmName, BayesianPrediction[]>>;
  geometryByAlgorithm?: Partial<Record<AlgorithmName, RouteGeometryPayload>>;
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
  travel_mode: TravelMode;
  optimization_objective?: OptimizationObjective;
  data_source?: DataSourceType;
  provider_label?: string;
  is_live_traffic?: boolean;
  duration_label?: string;
  traffic_calculated_at?: string | null;
  normal_duration_minutes?: number | null;
  traffic_delay_minutes?: number | null;
  encoded_polyline?: string | null;
  map_provider?: string;
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
  static_travel_from_previous_minutes?: number | null;
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
  optimization_objective?: OptimizationObjective;
  data_source?: DataSourceType;
  traffic_calculated_at?: string | null;
  encoded_polyline?: string | null;
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
    totalStaticDurationMinutes?: number;
    trafficDelayMinutes?: number;
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
    totalOffices?: number;
    totalDistributors: number;
    activeDistributors: number;
    demoDistributors: number;
    totalRoutePlans: number;
    scheduledOrCompletedPlans: number;
    totalScheduledVisits?: number;
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
  delayPredictionSummary?: {
    totalPredictions: number;
    lowRiskCount: number;
    mediumRiskCount: number;
    highRiskCount: number;
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
  distanceCategory?: 'Near' | 'Medium' | 'Far' | 'Unobserved';
  visitDurationMinutes?: number | null;
  visitDurationCategory?: 'Short' | 'Medium' | 'Long' | 'Unobserved';
  timeSlot?: 'Morning' | 'Afternoon' | 'Unobserved';
  priorityCategory?: 'Low' | 'Medium' | 'High' | 'Unobserved';
  evidence?: {
    distanceCategory: 'Near' | 'Medium' | 'Far' | 'Unobserved';
    visitDurationCategory: 'Short' | 'Medium' | 'Long' | 'Unobserved';
    timeSlot: 'Morning' | 'Afternoon' | 'Unobserved';
    priorityCategory: 'Low' | 'Medium' | 'High' | 'Unobserved';
  };
  isPartialEvidence?: boolean;
  marginalizedVariables?: string[];
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

export type SmartFixMode = 'QUICK_FIX' | 'SMART_OPTIMIZE' | 'SUGGESTIONS_ONLY';

export interface DiagnosticIssue {
  type: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  distributorId?: string;
  distributorName?: string;
  message: string;
  shortfallMinutes?: number;
  requiredMinutes?: number;
  availableMinutes?: number;
  travelMinutes?: number;
  bufferMinutes?: number;
  probabilities?: { Low: number; Medium: number; High: number };
  recommendedBufferMinutes?: number;
}

export interface DiagnosticsSummary {
  valid: boolean;
  issueCount: number;
  criticalCount: number;
  highCount: number;
  mediumCount: number;
  issues: DiagnosticIssue[];
}

export interface ComparisonItem {
  distributorId: string;
  distributorName: string;
  status: 'MOVED' | 'UNCHANGED' | 'ADDED' | 'REMOVED';
  originalStartTime: string | null;
  proposedStartTime: string | null;
  originalEndTime: string | null;
  proposedEndTime: string | null;
  visitDurationMinutes: number;
  priority: number;
  openingTime: string;
  closingTime: string;
  travelMinutes?: number | null;
  bufferMinutes?: number | null;
  delayRisk?: 'Low' | 'Medium' | 'High';
}

export interface ScheduleSuggestion {
  category: string;
  title: string;
  detail: string;
  impact: string;
  modeRecommended: SmartFixMode;
}

export interface SmartFixResponse {
  mode: SmartFixMode;
  routePlanId?: string;
  officeId?: string;
  officeName?: string;
  provider?: string;
  dataSource?: string;
  diagnostics: DiagnosticsSummary;
  activeProposal: {
    mode: SmartFixMode;
    feasible: boolean;
    solverStatus: string;
    executionTimeMs: number;
    scheduled: ScheduledVisitEntry[];
    unscheduled: UnscheduledVisitReport[];
    totalTravelMinutes?: number;
    totalDistanceKm?: number;
    totalWaitingMinutes?: number;
    highRiskCount?: number;
    objectiveScore?: number;
    backtracks?: number;
  };
  quickFix: {
    mode: 'QUICK_FIX';
    feasible: boolean;
    solverStatus: string;
    executionTimeMs: number;
    scheduled: ScheduledVisitEntry[];
    unscheduled: UnscheduledVisitReport[];
    totalTravelMinutes?: number;
    totalDistanceKm?: number;
  };
  smartOptimize: {
    mode: 'SMART_OPTIMIZE';
    feasible: boolean;
    solverStatus: string;
    executionTimeMs: number;
    scheduled: ScheduledVisitEntry[];
    unscheduled: UnscheduledVisitReport[];
    totalTravelMinutes?: number;
    totalDistanceKm?: number;
    totalWaitingMinutes?: number;
    highRiskCount?: number;
    objectiveScore?: number;
    backtracks?: number;
  };
  suggestions: {
    suggestionCount: number;
    suggestions: ScheduleSuggestion[];
    diagnosticsSummary: {
      totalIssues: number;
      criticalIssues: number;
      highIssues: number;
    };
  };
  comparison: {
    items: ComparisonItem[];
    movedCount: number;
    unchangedCount: number;
    addedCount: number;
    removedCount: number;
    resolvedIssuesCount: number;
    remainingIssuesCount: number;
    remainingIssues: DiagnosticIssue[];
  };
}

