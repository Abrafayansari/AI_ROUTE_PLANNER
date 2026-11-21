# Smart Route Planner for Sales Field Officers

A full-stack AI & field operations web application built with **React 19 + TypeScript + Vite**, a **Node.js / Express gateway**, a **Python 3.11+ Flask** AI & API server, and **Neon PostgreSQL** (with SQLite portability for isolated tests and local verification).

**Mapping & Simulation Boundary:** Interactive map views use **Leaflet** with **OpenStreetMap** basemap tiles client-side alongside a locally rendered **SVG Schematic Coordinate Plot**. **Zero external routing, distance-matrix, or geocoding APIs are used** — all pairwise distances and travel times are computed server-side in Python via the Haversine formula, simulated multipliers, and seeded mode speeds.

---

## Architecture

- **Frontend (`frontend/`):** React 19, TypeScript, Vite, Tailwind CSS v4, React Router (`react-router-dom`), Axios, Recharts, Leaflet (`leaflet`), Lucide React
- **Gateway (`server.ts`):** Express runtime on port `3000` that launches Python Flask on `127.0.0.1:5000`, waits up to `25s` for Flask readiness, proxies `/api/*` requests to Flask, and serves Vite in dev or `frontend/dist` in production
- **Backend (`backend/`):** Python 3.11+ Flask (`create_app()`), Flask-CORS, Flask-SQLAlchemy, `psycopg` v3, Flask-Migrate / Alembic (`backend/migrations/`), Pydantic v2 validation, NumPy, Pandas, pytest
- **Database (`db/schema.sql` & `backend/app/models/`):**
  - 10 tables: `office_locations`, `distributors`, `route_plans`, `route_stops`, `distributor_clusters`, `schedules`, `algorithm_runs`, `visit_delay_predictions`, `app_settings`, `audit_logs`
  - Uses server-side `DATABASE_URL` only (never exposed to React or prefixed with `VITE_`). Supports both PostgreSQL (`psycopg`) and portable SQLite for automated testing.
- **Demo Dataset:** Karachi, Pakistan (`Karachi Central Hub` at `24.8607, 67.0644` + 9 Karachi distributors tagged `is_demo = TRUE`).

---

## AI Modules (`backend/app/algorithms/`)

All AI algorithms run purely in Python:

| Course Week | Topic | Implementation | Key Details & Guarantees |
|---|---|---|---|
| **Week 2** | Intelligent Agents & Environment | Field Officer agent model | State `(currentNode, visitedBitmask, returnedFlag)` over local Haversine cost matrices |
| **Week 3** | Uninformed Search | `run_bfs` (`bfs.py`) | `O(n · 2^n)` states; minimizes edge count (hops), not weighted distance; capped at 12 distributors |
| **Week 4** | Cost-Based vs. Informed Search | `run_ucs` (`ucs.py`), `run_astar` (`astar.py`) | A* uses admissible `minEntry + MST(U) + minExit` lower bound to match UCS optimal simulated distance with fewer expanded nodes; capped at 12 distributors |
| **Week 5** | Constraint Satisfaction (CSP) | `run_csp_scheduler` (`csp.py`) | Backtracking + forward checking + MRV/priority ordering; enforces working hours, opening windows, lunch break, max daily visits, and fixed travel buffers |
| **Week 7** | Evolutionary Search | `run_genetic_algorithm` (`genetic_algorithm.py`) | Tournament selection, Order Crossover (OX1), inversion/swap mutation, elitism; configurable population size, generations, mutation rate, and seed; scales beyond 12 distributors |
| **Week 12** | Unsupervised Learning | `run_kmeans` (`kmeans.py`) | Seeded K-Means++ or random init using NumPy & Haversine coordinate assignment until convergence |
| **Week 14** | Probabilistic Reasoning | `BayesianDelayNetwork` (`bayesian_network.py`) | 5-variable discrete DAG (`Distance`, `VisitDuration`, `TimeSlot`, `Priority` → `DelayRisk`), 54-row validated CPT (`v1.0.0-illustrative`), and full or partial-evidence marginalization via priors |

---

## Configurable Route Optimizer Settings

On **Route Optimizer** (`/optimizer`), defaults match `seed = 42`, `distanceMultiplier = 1.0`, `gaPopulationSize = 80`, `gaGenerations = 150`, and `gaMutationRate = 0.18`. Expanding **Advanced Optimizer Settings** lets users adjust these inputs live, preview all 4 algorithms + per-algorithm Bayesian delay risk reports, and persist the chosen configuration to `route_plans` and `algorithm_runs`.

---

## Scope & Operational Boundary

- **Single-Workspace Demo Scope:** Intentionally operates without a user-auth/login gate for academic laboratory demonstration and evaluation.
- **Illustrative Bayesian CPTs:** The Bayesian Network parameters (`1.0.0-illustrative`) are domain-calibrated baselines pending empirical GPS arrival telemetry; saved evaluations in `visit_delay_predictions` provide the audit log for future parameter learning.

---

## Environment Variables

- **Server-Side (`DATABASE_URL`):** PostgreSQL connection string (`postgresql://...?sslmode=require`) or SQLite URI (`sqlite:///...` for isolated local testing). Never prefix with `VITE_` or commit `.env` files.
- **Optional Server Env:** `PORT` (Express port, default `3000`), `FLASK_PORT` (Flask internal port, default `5000`), `FRONTEND_URL` (CORS origins).
- **Frontend (`frontend/.env.example`):** `VITE_API_BASE_URL` (leave blank for same-origin `/api` proxy).

---

## API Endpoints (`/api`)

All responses use `{ success: true, data, message }` or `{ success: false, error: { code, message } }`.

- `GET /api/health` — Database connectivity & 10-table schema readiness check
- `POST /api/db/init` — Idempotent non-destructive schema verification/creation
- `POST /api/demo/load`, `POST /api/demo/clear` — Load or remove only `is_demo = TRUE` Karachi records
- `GET /api/office`, `POST /api/office`, `PUT /api/office/:id`, `DELETE /api/office/:id`
- `GET /api/distributors`, `POST /api/distributors`, `GET /api/distributors/:id`, `PUT /api/distributors/:id`, `DELETE /api/distributors/:id`
- `POST /api/distributors/import`, `GET /api/distributors/export` (with CSV formula-injection neutralization)
- `POST /api/clusters/run`, `GET /api/clusters/latest`
- `POST /api/schedules/run`, `GET /api/schedules/latest` (accepts optional `officeId`, returns Haversine leg distances and Bayesian advisory)
- `POST /api/graph/matrix`, `POST /api/optimize/preview`
- `GET /api/route-plans`, `POST /api/route-plans`, `GET /api/route-plans/:id`, `PUT /api/route-plans/:id`, `DELETE /api/route-plans/:id`
- `POST /api/route-plans/:id/optimize`, `GET /api/route-plans/:id/algorithms`, `PATCH /api/route-stops/:id/status`
- `GET /api/predictions/model-info`, `GET /api/predictions/cpt`, `POST /api/predictions/visit-delay`, `POST /api/predictions/route-delay`, `GET /api/predictions/visit-delay/history`
- `GET /api/analytics/summary` — Pandas-aggregated metrics across saved plans, algorithm runs, clusters, schedules, and delay predictions

---

## Running, Building & Testing

```bash
# Development (Express on :3000 + Flask on :5000 + Vite)
npm run dev

# Backend test suite (isolated SQLite; no Neon mutation)
DATABASE_URL="" PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -m pytest backend/tests -v -p no:cacheprovider

# Frontend TypeScript check & production build
npm run lint
npm run build
```
