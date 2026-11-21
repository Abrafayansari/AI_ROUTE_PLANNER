# Smart Route Planner for Sales Field Officers

A full-stack AI lab & field operations web application built with **React + TypeScript + Vite**, a **Python 3.11+ Flask** backend, and **Neon PostgreSQL**.

**No External Map APIs:** This application does **not** use Google Maps, Mapbox, OpenStreetMap tiles, geocoding, or any third-party routing API. All spatial plots are rendered locally as an aspect-corrected SVG schematic from stored latitude/longitude coordinates, and all distances/durations are computed server-side in Python using the Haversine formula and a deterministic simulated multiplier.

---

## Architecture

- **Frontend (`frontend/`):** React 19, TypeScript, Vite, Tailwind CSS v4, React Router (`react-router-dom`), Axios, Recharts, Lucide React
- **Backend (`backend/`):** Python 3.11+ Flask (`create_app()`), Flask-CORS, Flask-SQLAlchemy, `psycopg` v3, Flask-Migrate / Alembic (`backend/migrations/`), Pydantic v2 validation, NumPy, Pandas, scikit-learn, pytest
- **Database:** Neon PostgreSQL (`DATABASE_URL` server-side only) with SQLAlchemy ORM, parameterized queries, and transactional multi-table persistence
- **AI Algorithms (`backend/app/algorithms/`):** Implemented purely in independent, unit-tested Python modules:
  - `bfs.py` (Week 3: Uninformed BFS)
  - `ucs.py` (Week 4: Uninformed Uniform Cost Search)
  - `astar.py` (Week 4: Informed A* with admissible Prim MST heuristic)
  - `genetic_algorithm.py` (Week 7: Evolutionary Search with OX1 crossover)
  - `kmeans.py` (Week 12: Unsupervised K-Means Geographic Clustering)
  - `csp.py` (Week 5: Backtracking + Forward Checking CSP Visit Scheduler)
- **Root Orchestrator (`server.ts`):** Thin dev/runtime launcher that starts Python Flask on `127.0.0.1:5000`, proxies `/api/*` requests to Flask, and serves the Vite React frontend on port `3000`.

---

## Environment Variables

- **Root `.env` / AI Studio Secrets:**
  - `DATABASE_URL` (required, server-side only): Neon pooled PostgreSQL connection string (`postgresql://...?sslmode=require`). Never expose to React or prefix with `VITE_`.
  - `PORT` (optional, default `3000`): Frontend/proxy port.
- **Backend (`backend/.env.example`):**
  - `DATABASE_URL`
  - `FLASK_ENV` (e.g., `development`)
  - `PORT` (default `5000`)
  - `FRONTEND_URL` (comma-separated CORS origins, e.g., `http://localhost:5173,http://localhost:3000`)
- **Frontend (`frontend/.env.example`):**
  - `VITE_API_BASE_URL` (optional; leave blank when using Vite/proxy same-origin `/api` routing)

> **Security Reminder:** Never hardcode credentials or commit `.env` files. If a Neon password was previously pasted in chat, reset/rotate that role password in Neon Console before configuring `DATABASE_URL`.

---

## AI Modules & Complexity Notes

| Course Week | Topic | Implementation | Complexity & Guarantees |
|---|---|---|---|
| **Week 2** | Intelligent Agents & Environment | Field Officer agent in `backend/app/algorithms/` | State: `(currentNode, visitedBitmask, returnedFlag)`. Deterministic, discrete, fully observable environment. |
| **Week 3** | Uninformed Search | `run_bfs` in `backend/app/algorithms/bfs.py` | `O(n · 2^n)` states. Minimizes **edge count (hops)**, NOT weighted distance. Capped at 12 distributors. |
| **Week 4** | Uninformed Cost-Based vs. Informed Search | `run_ucs` & `run_astar` in `backend/app/algorithms/` | `O(n · 2^n)` worst case; A* uses admissible `minEntry + MST(U) + minExit` heuristic to prune states while matching UCS optimal simulated distance. Capped at 12 distributors. |
| **Week 5** | Constraint Satisfaction Problem (CSP) | `run_csp_scheduler` in `backend/app/algorithms/csp.py` | Backtracking + forward checking + MRV/priority ordering. Strictly enforces working hours, opening windows, lunch break, max visits, and fixed travel buffers. |
| **Week 7** | Evolutionary Search | `run_genetic_algorithm` in `backend/app/algorithms/genetic_algorithm.py` | `O(G · P · n)`. Tournament selection, Order Crossover (OX1), inversion/swap mutation, elitism. Heuristic (no optimality guarantee); scales past 12 stops. |
| **Week 12** | Unsupervised Learning | `run_kmeans` in `backend/app/algorithms/kmeans.py` | `O(I · K · n)`. Seeded K-Means++ or random init with Haversine assignment and centroid updates until convergence. |

*Scope Boundary:* Hidden Markov Models (HMM), Kalman Filters, supervised learning, and reinforcement learning are intentionally excluded.

---

## API Endpoints (Flask Blueprints under `/api`)

All endpoints return `{ success: true, data, message }` or `{ success: false, error: { code, message } }`.

- `GET /api/health` — Checks Flask and Neon PostgreSQL connection + schema readiness (never exposes secrets).
- `POST /api/db/init` — Idempotently verifies schema tables/columns without dropping or overwriting user data.
- `POST /api/demo/load` — Inserts fictional demo office & 9 distributors (`is_demo = TRUE`) without overwriting existing data.
- `POST /api/demo/clear` — Deletes only `is_demo = TRUE` records.
- `GET /api/office`, `POST /api/office`, `PUT /api/office/:id`
- `GET /api/distributors`, `POST /api/distributors`, `GET /api/distributors/:id`, `PUT /api/distributors/:id`, `DELETE /api/distributors/:id`
- `POST /api/distributors/import`, `GET /api/distributors/export`
- `POST /api/clusters/run`, `GET /api/clusters/latest`
- `POST /api/schedules/run`, `GET /api/schedules/latest`
- `POST /api/graph/matrix` — Generates & caches local Haversine simulated cost matrix.
- `POST /api/optimize/preview` — Runs BFS, UCS, A*, and GA on the same cost matrix.
- `GET /api/route-plans`, `POST /api/route-plans`, `GET /api/route-plans/:id`, `PUT /api/route-plans/:id`, `DELETE /api/route-plans/:id`
- `POST /api/route-plans/:id/optimize`, `GET /api/route-plans/:id/algorithms`
- `PATCH /api/route-stops/:id/status`
- `GET /api/analytics/summary` — Pandas-aggregated performance metrics and grounded insights.

---

## Running Locally & Tests

### Integrated Workspace (Port 3000)
```bash
npm run dev     # Starts Python Flask (127.0.0.1:5000) + Vite/Express proxy (0.0.0.0:3000)
npm test        # Runs pytest suite (backend/tests)
npm run lint    # Runs TypeScript checks on frontend
npm run build   # Builds production frontend bundle in frontend/dist
```

### Standalone Backend & Frontend
```bash
# Backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest -v tests
.venv/bin/python run.py

# Frontend
cd frontend
npm install
npm run dev
```
