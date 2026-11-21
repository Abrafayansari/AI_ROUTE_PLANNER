import React, { useState } from 'react';
import { ArrowRight, ChevronDown, ChevronUp, Network, ShieldAlert, Sparkles } from 'lucide-react';

interface Topic {
  week: string;
  title: string;
  description: string;
  details: string;
}

const CLASSICAL_TOPICS: Topic[] = [
  {
    week: 'Week 2 · Intelligent Agents & Environment',
    title: 'Field Officer Agent & Route-Planning Environment',
    description:
      'The sales field officer is modeled as a goal-based planning agent operating in a deterministic, fully observable, discrete, static route graph environment. Percepts include office and distributor coordinates, visit durations, and opening windows; actions move the agent from its current node to an unvisited distributor or back to the base office.',
    details:
      'State representation: (currentNode, visitedBitmask, returnedFlag). Initial state: (office, 0, false). Goal state: all selected distributors visited and returned to office (if enabled).',
  },
  {
    week: 'Week 3 · Uninformed Search',
    title: 'Breadth-First Search (BFS)',
    description:
      'Explores states level-by-level in FIFO order without inspecting edge weights or heuristics. On weighted route graphs, BFS minimizes the number of edges (hops), NOT total simulated travel distance.',
    details:
      'Time & Space Complexity: O(n · 2^n) distinct states in graph-search mode. Useful as an unweighted baseline to show why ignoring edge costs leads to suboptimal routes.',
  },
  {
    week: 'Week 4 · Informed Search & Cost-Based Baseline',
    title: 'Uniform Cost Search (UCS) vs. A* Search',
    description:
      'UCS is an uninformed cost-based search ordered strictly by cumulative path cost g(n). It guarantees the minimum-cost tour for non-negative edge weights but expands states equally in all directions. A* is an informed search ordered by f(n) = g(n) + h(n), where h(n) is a mathematically admissible lower bound.',
    details:
      'Admissible Heuristic h(n): min_{u in U} w(current, u) + MST(U) + (returnToOffice ? min_{u in U} w(u, office) : 0), where U is the set of unvisited distributors. Because these three edge sets are disjoint, h(n) never overestimates the true remaining tour cost, guaranteeing A* finds the same optimal distance as UCS while expanding fewer nodes.',
  },
  {
    week: 'Week 5 · Constraint Satisfaction Problem (CSP)',
    title: 'Backtracking Visit Scheduler with Forward Checking',
    description:
      'Models each distributor as a CSP variable whose domain is valid start-time slots. Enforces hard constraints: officer working hours, distributor opening/closing windows, mandatory lunch break, non-overlapping visits with fixed travel buffers, and maximum daily visits.',
    details:
      'Uses Minimum Remaining Values (MRV) and priority tie-breaking for variable ordering (priority never overrides hard constraints). Reports exact constraint failure reasons for any unscheduled distributor.',
  },
  {
    week: 'Week 7 · Evolutionary Search',
    title: 'Genetic Algorithm (GA) for Tour Permutations',
    description:
      'Maintains a population of valid distributor permutations with fixed office start/end. Uses tournament selection, Order Crossover (OX1) so every distributor appears exactly once, inversion/swap mutation, and elitism.',
    details:
      'GA is a stochastic heuristic search: it scales beyond the 12-distributor exact search cap in milliseconds, though it does not guarantee global optimality.',
  },
  {
    week: 'Week 12 · Unsupervised Learning',
    title: 'K-Means Geographic Clustering',
    description:
      'Partitions distributor coordinates into K geographic territories using seeded K-Means++ initialization, Haversine nearest-centroid assignment, and mean-coordinate updates until convergence.',
    details:
      'K-Means is unsupervised learning for spatial grouping only; it does not produce a visit order or road route.',
  },
];

interface QaItem {
  id: number;
  question: string;
  summary: string;
  answer: React.ReactNode;
}

const BAYESIAN_QA: QaItem[] = [
  {
    id: 1,
    question: '1. Why is a Bayesian Network appropriate for delay prediction instead of a deterministic formula?',
    summary: 'Probabilistic reasoning under uncertainty vs. brittle binary heuristics',
    answer: (
      <div className="space-y-2 text-sm text-slate-700">
        <p>
          In field sales operations, delays are governed by inherently stochastic, non-linear factors such as fluctuating traffic density, customer negotiation delays, and cumulative schedule slippage. A deterministic formula (such as <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs">score &gt; 5 &rArr; Delayed</code>) creates brittle all-or-nothing thresholds that cannot quantify uncertainty, degrees of confidence, or marginal trade-offs.
        </p>
        <p>
          A Bayesian Network models delay as a random variable conditioned on prior knowledge and observed evidence. It computes a coherent posterior probability distribution <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs">P(DelayRisk = r | Evidence)</code>, giving sales field officers calibrated risk probabilities (e.g. 92% High Risk vs. 45% Medium Risk) rather than an arbitrary binary guess.
        </p>
      </div>
    ),
  },
  {
    id: 2,
    question: '2. What are the random variables, their states, and the graph topology (DAG)?',
    summary: '4 discrete parent variables and 1 target variable in a Directed Acyclic Graph',
    answer: (
      <div className="space-y-2 text-sm text-slate-700">
        <p>The network consists of 5 discrete random variables organized in a 2-tier Directed Acyclic Graph (DAG):</p>
        <ul className="list-inside list-disc space-y-1 font-mono text-xs">
          <li><strong>Distance (D)</strong>: &#123;Near (&lt; 5 km), Medium (5–15 km), Far (&gt; 15 km)&#125;</li>
          <li><strong>Visit Duration (V)</strong>: &#123;Short (&lt; 30 min), Medium (30–59 min), Long (&ge; 60 min)&#125;</li>
          <li><strong>Time Slot (T)</strong>: &#123;Morning (&lt; 12:30), Afternoon (&ge; 12:30)&#125;</li>
          <li><strong>Distributor Priority (P)</strong>: &#123;Low (1–2), Medium (3), High (4–5)&#125;</li>
          <li><strong>Delay Risk (R)</strong> [Target]: &#123;Low, Medium, High&#125;</li>
        </ul>
        <p>
          <strong>Edges:</strong> Directed edges connect every parent to the target: <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs">D &rarr; R</code>, <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs">V &rarr; R</code>, <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs">T &rarr; R</code>, <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs">P &rarr; R</code>.
        </p>
      </div>
    ),
  },
  {
    id: 3,
    question: '3. Why are Distance, Duration, Time Slot, and Priority chosen as parents of Delay Risk?',
    summary: 'Domain-specific causal rationale for field route delay mechanics',
    answer: (
      <div className="space-y-2 text-sm text-slate-700">
        <ul className="space-y-1.5 text-xs">
          <li>
            <strong className="text-slate-900">Transit Distance:</strong> Longer travel legs between stops directly increase exposure to road congestion, detours, and transit time variance.
          </li>
          <li>
            <strong className="text-slate-900">Visit Duration:</strong> Extensive client meetings (&ge; 60 min) exhibit high variance in finish times due to unpredictable order negotiations and manager sign-offs.
          </li>
          <li>
            <strong className="text-slate-900">Scheduled Time Slot:</strong> Afternoon visits (&ge; 12:30) carry compounded cumulative schedule slippage from earlier morning delays, as well as afternoon traffic peaks.
          </li>
          <li>
            <strong className="text-slate-900">Distributor Priority:</strong> Higher priority accounts (Tier 4-5 key distributors) require thorough catalog walkthroughs, stock audits, and dispute resolutions, making overruns significantly more probable.
          </li>
        </ul>
      </div>
    ),
  },
  {
    id: 4,
    question: '4. What conditional independence assumptions are encoded in this network?',
    summary: 'Parent independence and d-separation properties in the DAG',
    answer: (
      <div className="space-y-2 text-sm text-slate-700">
        <p>
          The graph structure specifies that the four parent variables are unconditionally independent:
        </p>
        <p className="rounded bg-slate-100 p-2 font-mono text-xs">
          P(D, V, T, P) = P(D) &times; P(V) &times; P(T) &times; P(P)
        </p>
        <p>
          Furthermore, conditioned on the complete state of its four parents, Delay Risk <code className="font-mono text-xs">R</code> is conditionally independent of any other ancestral variables. While <code className="font-mono text-xs">R</code> is unobserved, observing one parent (e.g. Distance = Far) provides no information about the state of another parent (e.g. Priority), preventing spurious correlations.
        </p>
      </div>
    ),
  },
  {
    id: 5,
    question: '5. How does exact inference work with full evidence versus partial evidence (marginalization)?',
    summary: 'Direct CPT indexing for complete evidence; sum-product marginalization for partial evidence',
    answer: (
      <div className="space-y-2 text-sm text-slate-700">
        <p>
          <strong>Full Evidence:</strong> When all 4 parents are known <code className="font-mono text-xs">e = &#123;D=d, V=v, T=t, P=p&#125;</code>, exact inference is an O(1) lookup in the 54-row Conditional Probability Table:
        </p>
        <p className="rounded bg-slate-100 p-2 font-mono text-xs">
          P(R=r | e) = P(R=r | D=d, V=v, T=t, P=p)
        </p>
        <p>
          <strong>Partial Evidence:</strong> When some parent variables are unobserved (e.g. only distance and duration are known before scheduling), the engine marginalizes over the unobserved parents using their prior probability distributions:
        </p>
        <p className="rounded bg-slate-100 p-2 font-mono text-xs">
          P(R=r | e_obs) = &alpha; &times; &sum;_(u &isin; Unobserved) [ P(R=r | e_obs, u) &times; &prod;_(X_i &isin; u) P(X_i) ]
        </p>
        <p>
          where <code className="font-mono text-xs">&alpha;</code> is the normalization constant enforcing <code className="font-mono text-xs">&sum;_r P(R=r | e_obs) = 1.0</code>.
        </p>
      </div>
    ),
  },
  {
    id: 6,
    question: '6. How does the CPT enforce that probabilities sum to 1.0 for each parent combination?',
    summary: '54 row configurations with rigorous normalization and startup validation',
    answer: (
      <div className="space-y-2 text-sm text-slate-700">
        <p>
          The parent variable space spans <code className="font-mono text-xs">3 &times; 3 &times; 2 &times; 3 = 54</code> distinct configurations. For every row <code className="font-mono text-xs">(d, v, t, p)</code>, the conditional distribution over Delay Risk is strictly normalized:
        </p>
        <p className="rounded bg-slate-100 p-2 font-mono text-xs">
          P(R=Low | d, v, t, p) + P(R=Medium | d, v, t, p) + P(R=High | d, v, t, p) = 1.0000
        </p>
        <p>
          The backend runs a programmatic assertion at module import (<code className="font-mono text-xs">validate_cpts()</code>) that validates all 54 rows and all 4 prior distributions sum to 1.0 within a tolerance of <code className="font-mono text-xs">10^-4</code>.
        </p>
      </div>
    ),
  },
  {
    id: 7,
    question: '7. What is the difference between prior probability and posterior probability in this context?',
    summary: 'A priori base distribution vs. evidentiary posterior distribution',
    answer: (
      <div className="space-y-2 text-sm text-slate-700">
        <p>
          <strong>Prior Probability P(X):</strong> The marginal probability distribution of a variable before any evidence is observed for a specific visit. For instance:
        </p>
        <p className="rounded bg-slate-100 p-2 font-mono text-xs">
          P(Distance) = &#123;Near: 0.40, Medium: 0.40, Far: 0.20&#125;
          <br />
          P(VisitDuration) = &#123;Short: 0.35, Medium: 0.45, Long: 0.20&#125;
          <br />
          P(TimeSlot) = &#123;Morning: 0.50, Afternoon: 0.50&#125;
          <br />
          P(Priority) = &#123;Low: 0.25, Medium: 0.45, High: 0.30&#125;
        </p>
        <p>
          <strong>Posterior Probability P(R | e):</strong> The updated probability distribution of Delay Risk after conditioning on observed evidence for a specific scheduled stop (e.g. Far distance, Long duration, Afternoon slot, High priority &rArr; P(High)=92.03%).
        </p>
      </div>
    ),
  },
  {
    id: 8,
    question: '8. How does the sales field officer use the predicted risk (decision support, not hard constraint)?',
    summary: 'Actionable advisory buffers rather than destructive pruning',
    answer: (
      <div className="space-y-2 text-sm text-slate-700">
        <p>
          In classical CSP scheduling, hard constraints (such as opening windows and lunch breaks) must be satisfied or a visit is deemed infeasible. In contrast, the Bayesian Network functions as <strong>decision support</strong>:
        </p>
        <ul className="list-inside list-disc space-y-1 text-xs">
          <li><strong>Low Risk (&lt;25%):</strong> Standard schedule execution; default 10-15 min travel buffers are sufficient.</li>
          <li><strong>Medium Risk (25-50%):</strong> Advisory to add an extra 10-minute travel buffer or schedule the stop earlier in its window.</li>
          <li><strong>High Risk (&gt;50%):</strong> Warning that cumulative delays may cascade into subsequent stops; advises rescheduling to the morning slot, adding a 20-30 min contingency buffer, or splitting the visit.</li>
        </ul>
      </div>
    ),
  },
  {
    id: 9,
    question: '9. Why is this model marked as an illustrative baseline (1.0.0-illustrative) rather than an empirically fitted model?',
    summary: 'Scientific honesty regarding database contents and future MLE parameter learning',
    answer: (
      <div className="space-y-2 text-sm text-slate-700">
        <p>
          <strong>Database Ground Truth:</strong> Inspection of the existing Neon PostgreSQL database reveals that while planned routes and distributor records exist, actual field GPS telemetry and historical arrival timestamp logs have not yet been accumulated.
        </p>
        <p>
          Rather than fabricating synthetic delays or claiming false empirical validation, the model is transparently labeled as <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs">1.0.0-illustrative / illustrative_baseline</code>. The database table <code className="font-mono text-xs">visit_delay_predictions</code> logs every prediction with full evidence and timestamps, establishing the exact data collection foundation needed for Maximum Likelihood Estimation (MLE) or Expectation-Maximization (EM) parameter fitting once actual arrival logs are gathered.
        </p>
      </div>
    ),
  },
  {
    id: 10,
    question: '10. Step-by-step numerical calculation walk-through for a specific evidence configuration',
    summary: 'Concrete mathematical calculation from project CPT for Far + Long + Afternoon + High',
    answer: (
      <div className="space-y-3 text-sm text-slate-700">
        <p>
          Consider an extreme scenario evaluated by our engine:
          <br />
          <span className="font-mono text-xs text-slate-900 font-semibold">
            Evidence: Distance = Far (&gt; 15 km), Duration = Long (&ge; 60 min), Time Slot = Afternoon (&ge; 12:30), Priority = High (4–5)
          </span>
        </p>
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs space-y-2">
          <div>
            <strong>1. Component Factor Weights:</strong>
            <br />
            w_dist(Far) = 2.5, w_dur(Long) = 2.2, w_time(Afternoon) = 1.6, w_prio(High) = 1.1
            <br />
            Raw Score = 2.5 + 2.2 + 1.6 + 1.1 = 7.4 (Normalized score s = 7.4 / 7.4 = 1.0)
          </div>
          <div>
            <strong>2. Logit Computation:</strong>
            <br />
            logit_low = exp(3.2 &times; (1.0 - 1.0) - 0.5) = exp(-0.5) &approx; 0.6065
            <br />
            logit_med = exp(2.0 &times; (1.0 - |1.0 - 0.5| &times; 2.2)) = exp(-0.2) &approx; 0.8187
            <br />
            logit_high = exp(3.4 &times; 1.0 - 0.6) = exp(2.8) &approx; 16.4446
            <br />
            Total logit sum = 0.6065 + 0.8187 + 16.4446 = 17.8698
          </div>
          <div>
            <strong>3. Posterior Probabilities (sum = 1.0000):</strong>
            <br />
            P(DelayRisk = Low | e) = 0.6065 / 17.8698 = <strong>0.0339 (3.39%)</strong>
            <br />
            P(DelayRisk = Medium | e) = 0.8187 / 17.8698 = <strong>0.0458 (4.58%)</strong>
            <br />
            P(DelayRisk = High | e) = 1.0 - 0.0339 - 0.0458 = <strong>0.9203 (92.03%)</strong>
          </div>
          <div>
            <strong>4. Classification & Recommendation:</strong>
            <br />
            argmax_r P(DelayRisk = r | e) = <strong>High (92.03%)</strong>
            <br />
            Advisory: &ldquo;High Delay Risk (92.0% probability). Severe compound delay factors detected. Add at least 20-30 min schedule buffer or reschedule to morning slot.&rdquo;
          </div>
        </div>
      </div>
    ),
  },
];

export const AiConceptsPage: React.FC = () => {
  const [openQaId, setOpenQaId] = useState<number | null>(10); // default open the numerical walk-through

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-blue-700">
          <Sparkles className="h-4 w-4" />
          AI Engineering & Algorithms Laboratory
        </div>
        <h2 className="mt-1 text-xl font-bold text-slate-900">
          Course Topics & Probabilistic Inference Architecture
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">
          Smart Route Planner implements classical and probabilistic AI techniques across seven modular syllabus domains on the Python backend using NumPy and Pandas. Real-road distances, route geometries, and travel durations come from a prioritized provider chain—Google Routes API (optional, when configured), OSRM / OpenStreetMap (free default fallback), and OpenRouteService (free-tier fallback, when configured)—while our Python algorithms remain solely responsible for route optimization (BFS, UCS, A*, GA), CSP scheduling, K-Means clustering, and Bayesian delay prediction across both Fastest Time and Shortest Distance objectives.
        </p>
        <div className="mt-3 inline-flex items-center gap-2 rounded-md bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-800">
          Syllabus Modules Implemented: Weeks 2, 3, 4, 5, 7, 12, and 14 (Bayesian Networks).
        </div>
      </div>

      {/* Week 14 Bayesian Network Deep Dive */}
      <div className="rounded-xl border border-indigo-200 bg-gradient-to-br from-indigo-50/50 via-white to-slate-50 p-6 shadow-sm space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-indigo-100 pb-4">
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-900">
              <Network className="h-3.5 w-3.5" />
              Week 14 · Bayesian Networks & Probabilistic Reasoning
            </span>
            <h3 className="mt-2 text-lg font-bold text-slate-900">
              Distributor Visit Delay Prediction — Exact Probabilistic Inference
            </h3>
            <p className="mt-1 text-xs text-slate-600">
              A comprehensive 5-variable Bayesian Network supporting exact discrete inference, CPT verification, and schedule buffer advisories.
            </p>
          </div>
          <div className="flex items-center gap-2 font-mono text-xs">
            <span className="rounded bg-indigo-50 px-2 py-1 text-indigo-700 border border-indigo-200">
              Model: 1.0.0-illustrative
            </span>
            <span className="rounded bg-emerald-50 px-2 py-1 text-emerald-700 border border-emerald-200">
              54 CPT Configurations
            </span>
          </div>
        </div>

        {/* SVG Network DAG Diagram */}
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-slate-900">Bayesian Network DAG Topology</h4>
            <span className="text-xs text-slate-500">Directed Acyclic Graph (4 Parents &rarr; 1 Target)</span>
          </div>
          <div className="mt-4 flex flex-col items-center">
            {/* 4 Parents row */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 w-full max-w-2xl">
              <div className="rounded-lg border border-blue-200 bg-blue-50/70 p-3 text-center shadow-xs">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-blue-600">Parent Variable</div>
                <div className="text-xs font-bold text-slate-900">Distance (D)</div>
                <div className="mt-1 text-[10px] text-slate-500 font-mono">Near | Med | Far</div>
                <div className="mt-1 text-[9px] text-blue-700 font-mono">Priors: 0.40 / 0.40 / 0.20</div>
              </div>

              <div className="rounded-lg border border-cyan-200 bg-cyan-50/70 p-3 text-center shadow-xs">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-cyan-600">Parent Variable</div>
                <div className="text-xs font-bold text-slate-900">Duration (V)</div>
                <div className="mt-1 text-[10px] text-slate-500 font-mono">Short | Med | Long</div>
                <div className="mt-1 text-[9px] text-cyan-700 font-mono">Priors: 0.35 / 0.45 / 0.20</div>
              </div>

              <div className="rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-center shadow-xs">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-amber-600">Parent Variable</div>
                <div className="text-xs font-bold text-slate-900">Time Slot (T)</div>
                <div className="mt-1 text-[10px] text-slate-500 font-mono">Morning | Afternoon</div>
                <div className="mt-1 text-[9px] text-amber-700 font-mono">Priors: 0.50 / 0.50</div>
              </div>

              <div className="rounded-lg border border-purple-200 bg-purple-50/70 p-3 text-center shadow-xs">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-purple-600">Parent Variable</div>
                <div className="text-xs font-bold text-slate-900">Priority (P)</div>
                <div className="mt-1 text-[10px] text-slate-500 font-mono">Low | Med | High</div>
                <div className="mt-1 text-[9px] text-purple-700 font-mono">Priors: 0.25 / 0.45 / 0.30</div>
              </div>
            </div>

            {/* Arrows pointing down */}
            <div className="my-3 flex items-center justify-center gap-8 text-indigo-400">
              <svg className="w-64 h-10" viewBox="0 0 256 40" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M 32 0 L 120 36" stroke="#6366f1" strokeWidth="2" strokeDasharray="3 3" />
                <path d="M 96 0 L 124 36" stroke="#6366f1" strokeWidth="2" />
                <path d="M 160 0 L 132 36" stroke="#6366f1" strokeWidth="2" />
                <path d="M 224 0 L 136 36" stroke="#6366f1" strokeWidth="2" strokeDasharray="3 3" />
                <polygon points="128,38 123,30 133,30" fill="#4f46e5" />
              </svg>
            </div>

            {/* Target Node */}
            <div className="w-full max-w-md rounded-xl border-2 border-indigo-500 bg-indigo-600 p-4 text-center text-white shadow-md">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-indigo-200">
                Target Random Variable (Conditioned on All 4 Parents)
              </div>
              <div className="text-base font-bold">Delay Risk (R)</div>
              <div className="mt-1 font-mono text-xs text-indigo-100">
                States: Low Risk | Medium Risk | High Risk
              </div>
              <div className="mt-2 text-[11px] text-indigo-100">
                Inference: P(R | D, V, T, P) via 54-row CPT lookup &amp; marginalization
              </div>
            </div>
          </div>
        </div>

        {/* 10 Core Questions Accordion */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-base font-semibold text-slate-900">
              Core Theoretical &amp; Practical Principles (10 Essential Questions)
            </h4>
            <span className="text-xs text-slate-500">Click to expand any section</span>
          </div>

          <div className="space-y-2">
            {BAYESIAN_QA.map((qa) => {
              const isOpen = openQaId === qa.id;
              return (
                <div
                  key={qa.id}
                  className="rounded-lg border border-slate-200 bg-white transition-colors"
                >
                  <button
                    type="button"
                    onClick={() => setOpenQaId(isOpen ? null : qa.id)}
                    className="flex w-full items-center justify-between p-4 text-left hover:bg-slate-50/80"
                  >
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{qa.question}</p>
                      <p className="text-xs text-slate-500 mt-0.5">{qa.summary}</p>
                    </div>
                    {isOpen ? (
                      <ChevronUp className="h-4 w-4 shrink-0 text-slate-500" />
                    ) : (
                      <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
                    )}
                  </button>
                  {isOpen && (
                    <div className="border-t border-slate-100 p-4 bg-slate-50/40">
                      {qa.answer}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Classical Syllabus Topics (Weeks 2, 3, 4, 5, 7, 12) */}
      <div>
        <h3 className="text-base font-bold text-slate-900 mb-3">
          Classical Search, Optimization &amp; Clustering Syllabus Modules
        </h3>
        <div className="grid gap-4 md:grid-cols-2">
          {CLASSICAL_TOPICS.map((t) => (
            <div key={t.week} className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs">
              <p className="text-xs font-semibold text-blue-700">{t.week}</p>
              <h4 className="mt-1 text-base font-semibold text-slate-900">{t.title}</h4>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">{t.description}</p>
              <p className="mt-3 border-t border-slate-100 pt-3 font-mono text-xs leading-relaxed text-slate-700">
                {t.details}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
