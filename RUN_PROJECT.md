# Run Project — Smart Route Planner for Sales Field Officers

This guide details how to set up, run, verify, and debug the Smart Route Planner system across development and production environments.

---

## 1. Prerequisites

Before running the project, verify that the following system dependencies are installed:

- **Node.js**: v18.0.0 or higher (v20+ recommended)
- **npm**: v9.0.0 or higher
- **Python**: v3.10 to v3.14 (Python 3.14.6 is currently installed in `backend/.venv`)
- **Operating System**: Windows, macOS, or Linux

---

## 2. First-Time Setup

### Step 1: Install Node Dependencies
Run the following commands in order from the repository root:
```bash
# Install root supervisor dependencies
npm install

# Install frontend dependencies
npm --prefix frontend install
```

### Step 2: Set Up Python Virtual Environment
The system includes a dedicated Python virtual environment under `backend/.venv`.

If setting up on a new machine:
```bash
# Windows
python -m venv backend/.venv
backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt

# Linux / macOS
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
```

### Step 3: Initialize SQLite Database
The project utilizes SQLite with its database file located at `backend/instance/smart_route_planner.db`.
The database schema and demo data (including FAST-NUCES Karachi) initialize automatically upon first launch or via:
```bash
# Windows
backend\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'backend'); from app import create_app; from app.services.db_service import init_database, load_demo_data; app = create_app(); ctx = app.app_context(); ctx.push(); init_database(); load_demo_data()"
```

---

## 3. Complete Project Startup (One Command)

To run the complete application (Vite Frontend + Express Gateway + Python Flask Backend):

```bash
npm run dev
```

### What this starts:
1. **Node.js Express Gateway** on port **`3000`** (`http://127.0.0.1:3000`).
2. **Vite Development Middleware** seamlessly served through the Express gateway at `http://localhost:3000`.
3. **Python Flask Backend Supervisor** automatically spawned as a child process on port **`5000`** (`http://127.0.0.1:5000`).

### Primary Application URL:
> **`http://localhost:3000`**  
*(Open this in your browser to access the application)*

---

## 4. Individual Service Startup (Debugging Mode)

You can also run each subsystem independently:

### A. Frontend Only (Vite Standalone Server)
```bash
npm run dev:frontend
```
- Starts Vite on **`http://localhost:5173`**.
- Directly proxies `/api` calls to `http://127.0.0.1:5000`.

### B. Express Gateway Only
```bash
npm run dev:gateway
```
- Starts the Express Gateway on **`http://localhost:3000`**.
- Forwards `/api` calls to the Flask backend on port `5000`.

### C. Backend Only (Flask Standalone Server)
```bash
npm run dev:backend
```
- Starts the Flask REST API on **`http://127.0.0.1:5000`**.

---

## 5. Health-Check & Diagnostic Endpoints

Verify service availability via browser or terminal:

| Service / Endpoint | URL | Expected Status | Description |
| :--- | :--- | :--- | :--- |
| **Application UI** | `http://localhost:3000/` | `200 OK` | Main React Single Page App |
| **Gateway Health** | `http://localhost:3000/api/health` | `200 OK` | Express-to-Flask proxy health check |
| **Direct Flask Health** | `http://127.0.0.1:5000/api/health` | `200 OK` | Flask direct health check & DB status |
| **Distributors API** | `http://localhost:3000/api/distributors?pageSize=20` | `200 OK` | Returns all 10 Karachi distributors |

---

## 6. How to Safely Stop Services

- In the terminal where `npm run dev` is running, press **`Ctrl + C`**.
- The Express supervisor catches `SIGINT` / `SIGTERM` and automatically terminates the child Flask backend process (`python.exe`), preventing orphaned background processes.
- If a port remains blocked on Windows:
```powershell
Get-Process -Name node, python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*server.ts*' -or $_.CommandLine -like '*run.py*' } | Stop-Process -Force
```

---

## 7. Troubleshooting Guide

### 1. `EADDRINUSE: address already in use :::3000` or `:::5000`
- **Cause**: An earlier session did not release port 3000 or 5000.
- **Fix**: Check running processes on these ports:
  ```powershell
  Get-NetTCPConnection -LocalPort 3000, 5000 -ErrorAction SilentlyContinue
  ```
  Terminate the blocking process using `Stop-Process -Id <PID> -Force`.

### 2. `WinError 10013: An attempt was made to access a socket...`
- **Cause**: Windows sandbox restrictions or third-party firewall blocking loopback socket binding.
- **Fix**: Run the command outside restricted sandbox environments or ensure Windows Defender allows loopback connections to ports 3000 and 5000.

### 3. `ModuleNotFoundError: No module named 'dotenv'` or `No module named 'flask'`
- **Cause**: Command executed using the global system Python instead of the virtual environment.
- **Fix**: Always invoke Python via `backend/.venv/Scripts/python.exe` (Windows) or `backend/.venv/bin/python` (macOS/Linux).

### 4. `503 Service Unavailable: BACKEND_STARTING`
- **Cause**: Flask is bootstrapping or running database schema verification.
- **Fix**: Wait 2–3 seconds and refresh. The supervisor automatically routes requests as soon as Flask responds to health checks.

### 5. `503 Service Unavailable: ROUTING_PROVIDERS_UNAVAILABLE`
- **Cause**: Public OSRM demo server (`router.project-osrm.org`) was temporarily unreachable due to network disconnects.
- **Fix**: Verify your internet connection or configure an offline OSRM instance via `OSRM_BASE_URL` in `.env`.
