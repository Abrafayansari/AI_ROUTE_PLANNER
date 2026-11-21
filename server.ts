import 'dotenv/config';
import { spawn, type ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import express, { type Request, type Response } from 'express';

const FLASK_HOST = '127.0.0.1';
const FLASK_PORT = Number(process.env.FLASK_PORT) || 5000;

type BackendState = 'bootstrapping' | 'starting' | 'ready' | 'error';

let backendState: BackendState = 'bootstrapping';
let backendStatusMessage = 'Python Flask backend is initializing...';
let flaskProc: ChildProcess | null = null;
let shuttingDown = false;
let restartTimer: NodeJS.Timeout | null = null;

function resolvePythonExecutable(): string {
  const venvPython = path.resolve(process.cwd(), 'backend/.venv/bin/python');
  if (fs.existsSync(venvPython)) {
    return venvPython;
  }
  return 'python3';
}

function runCommand(
  cmd: string,
  args: string[],
  label: string,
  cwd: string = process.cwd()
): Promise<void> {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, {
      cwd,
      env: process.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    child.stdout?.on('data', (chunk: Buffer) => {
      process.stdout.write(`[${label}] ${chunk.toString()}`);
    });
    child.stderr?.on('data', (chunk: Buffer) => {
      process.stderr.write(`[${label}] ${chunk.toString()}`);
    });
    child.on('error', (err) => reject(err));
    child.on('exit', (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`${label} exited with code ${code ?? 'unknown'}`));
      }
    });
  });
}

async function ensureFrontendDependencies(): Promise<void> {
  const frontendDir = path.resolve(process.cwd(), 'frontend');
  const frontendModules = path.resolve(frontendDir, 'node_modules');
  if (fs.existsSync(frontendModules)) {
    return;
  }
  console.log('[setup] Installing frontend dependencies...');
  await runCommand('npm', ['--prefix', 'frontend', 'install', '--no-audit', '--no-fund'], 'frontend-setup');
}

async function ensurePythonEnvironment(): Promise<void> {
  backendState = 'bootstrapping';
  backendStatusMessage = 'Bootstrapping Python virtual environment and backend dependencies...';
  const bootstrapScript = path.resolve(process.cwd(), 'backend/bootstrap.py');
  await runCommand('python3', [bootstrapScript], 'python-bootstrap');
}

function startFlaskBackend(): ChildProcess {
  backendState = 'starting';
  backendStatusMessage = 'Starting Python Flask backend...';

  const pythonBin = resolvePythonExecutable();
  const runScript = path.resolve(process.cwd(), 'backend/run.py');

  const child = spawn(pythonBin, [runScript], {
    cwd: path.resolve(process.cwd(), 'backend'),
    env: {
      ...process.env,
      PORT: String(FLASK_PORT),
      FLASK_HOST,
      PYTHONUNBUFFERED: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  child.stdout?.on('data', (chunk: Buffer) => {
    process.stdout.write(`[flask] ${chunk.toString()}`);
  });
  child.stderr?.on('data', (chunk: Buffer) => {
    process.stderr.write(`[flask] ${chunk.toString()}`);
  });
  child.on('error', (err) => {
    console.error(`Failed to launch Flask backend: ${err.message}`);
  });
  child.on('exit', (code, signal) => {
    if (flaskProc === child) {
      flaskProc = null;
    }
    if (shuttingDown) {
      return;
    }
    backendState = 'starting';
    backendStatusMessage = 'Python Flask backend restarted after unexpected exit...';
    console.error(
      `Flask backend exited unexpectedly (code=${code ?? 'null'}, signal=${signal ?? 'none'}). Restarting in 2s...`
    );
    if (!restartTimer) {
      restartTimer = setTimeout(() => {
        restartTimer = null;
        if (!shuttingDown) {
          void bootFlaskSupervisor();
        }
      }, 2000);
    }
  });

  flaskProc = child;
  return child;
}

async function waitForFlaskReady(timeoutMs = 20000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ready = await new Promise<boolean>((resolve) => {
      const req = http.get(
        {
          hostname: FLASK_HOST,
          port: FLASK_PORT,
          path: '/api/health',
          timeout: 1000,
        },
        (res) => {
          res.resume();
          resolve(res.statusCode !== undefined && (res.statusCode < 500 || res.statusCode === 503));
        }
      );
      req.on('error', () => resolve(false));
      req.on('timeout', () => {
        req.destroy();
        resolve(false);
      });
    });

    if (ready) {
      backendState = 'ready';
      backendStatusMessage = 'Python Flask backend is ready.';
      return true;
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  console.warn('Flask backend did not respond before startup timeout; continuing proxy setup.');
  return false;
}

async function bootFlaskSupervisor(): Promise<void> {
  try {
    await ensurePythonEnvironment();
    startFlaskBackend();
    await waitForFlaskReady(25000);
  } catch (err) {
    backendState = 'error';
    backendStatusMessage =
      err instanceof Error
        ? `Python backend initialization failed: ${err.message}`
        : 'Python backend initialization failed.';
    console.error(backendStatusMessage);
    throw err;
  }
}

function proxyToFlask(req: Request, res: Response): void {
  const clientIp = req.ip || req.socket.remoteAddress || '127.0.0.1';
  const existingForwarded = req.headers['x-forwarded-for'];
  const forwardedHeader = existingForwarded
    ? `${Array.isArray(existingForwarded) ? existingForwarded.join(', ') : existingForwarded}, ${clientIp}`
    : clientIp;

  const headers: http.OutgoingHttpHeaders = {
    ...req.headers,
    host: `${FLASK_HOST}:${FLASK_PORT}`,
    'x-forwarded-for': forwardedHeader,
  };

  const proxyReq = http.request(
    {
      hostname: FLASK_HOST,
      port: FLASK_PORT,
      path: req.originalUrl,
      method: req.method,
      headers,
    },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    }
  );

  proxyReq.on('error', () => {
    if (!res.headersSent) {
      const isStarting = backendState === 'bootstrapping' || backendState === 'starting';
      res.status(503).json({
        success: false,
        error: {
          code: isStarting ? 'BACKEND_STARTING' : 'BACKEND_UNAVAILABLE',
          message: isStarting
            ? backendStatusMessage
            : 'Python Flask backend is temporarily unavailable.',
        },
      });
    }
  });

  req.pipe(proxyReq, { end: true });
}

async function startServer(): Promise<void> {
  const isProd = process.env.NODE_ENV === 'production';

  if (!isProd) {
    await ensureFrontendDependencies();
  }

  let fatalBootError: unknown = null;
  const backendBootPromise = bootFlaskSupervisor().catch((err) => {
    fatalBootError = err;
  });

  const shutdown = () => {
    shuttingDown = true;
    if (restartTimer) {
      clearTimeout(restartTimer);
      restartTimer = null;
    }
    if (flaskProc && !flaskProc.killed) {
      flaskProc.kill('SIGTERM');
    }
    process.exit(0);
  };
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);

  // Wait up to 25s so warm and typical boots have Flask ready before port 3000 opens,
  // avoiding initial 503 race errors on /api/health while bounded on cold-start installs.
  await Promise.race([
    backendBootPromise,
    new Promise<void>((resolve) => setTimeout(resolve, 25000)),
  ]);

  if (fatalBootError) {
    throw fatalBootError;
  }

  const app = express();
  const port = Number(process.env.PORT) || 3000;

  // Forward all /api requests directly to Python Flask backend
  app.use('/api', (req, res) => {
    proxyToFlask(req, res);
  });

  if (!isProd) {
    const { createServer: createViteServer } = await import('vite');
    const frontendRoot = path.resolve(process.cwd(), 'frontend');
    const vite = await createViteServer({
      configFile: path.resolve(frontendRoot, 'vite.config.ts'),
      root: frontendRoot,
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distDir = path.resolve(process.cwd(), 'frontend/dist');
    app.use(express.static(distDir));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distDir, 'index.html'));
    });
  }

  app.listen(port, '0.0.0.0', () => {
    console.log(`Smart Route Planner frontend+proxy listening on http://0.0.0.0:${port}`);
  });
}

startServer().catch((err) => {
  console.error('Server failed to start:', err instanceof Error ? err.message : 'Unknown error');
  process.exit(1);
});
