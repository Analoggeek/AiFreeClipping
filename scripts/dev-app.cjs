/* One-command desktop dev run: Python engine + Vite + Electron. */
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const root = path.join(__dirname, '..');
const tokenPath = path.join(os.homedir(), '.AiFreeClipping', '.api_token');
const children = [];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function run(command, args, env = {}) {
  const child = spawn(command, args, {
    cwd: root,
    shell: process.platform === 'win32',
    env: { ...process.env, ...env },
    stdio: 'inherit',
  });
  children.push(child);
  return child;
}

async function waitFor(predicate, label, attempts = 120) {
  for (let i = 0; i < attempts; i++) {
    if (await predicate()) return true;
    await sleep(500);
  }
  throw new Error(`Timed out waiting for ${label}`);
}

function ping(url) {
  return new Promise((resolve) => {
    http.get(url, (response) => { response.resume(); resolve(response.statusCode < 500); })
      .on('error', () => resolve(false));
  });
}

(async () => {
  if (fs.existsSync(tokenPath)) fs.unlinkSync(tokenPath);
  const python = fs.existsSync(path.join(root, '.venv', 'bin', 'python'))
    ? path.join(root, '.venv', 'bin', 'python')
    : 'python3';
  run(python, ['-m', 'backend.app.main'], {
    PYTHONPATH: path.join(root, 'backend'),
    AIFREECLIP_PORT: '8787',
    PYTHONUNBUFFERED: '1',
  });
  await waitFor(() => fs.existsSync(tokenPath), 'local engine');
  run('npm', ['run', 'dev'], {});
  await waitFor(() => ping('http://127.0.0.1:5173'), 'vite');
  run('npx', ['electron', '.'], {
    AIFREECLIP_EXTERNAL_BACKEND: '1',
    AIFREECLIP_API_BASE: 'http://127.0.0.1:8787',
  });
})().catch((error) => {
  console.error(error);
  children.forEach((child) => child.kill());
  process.exitCode = 1;
});

process.on('SIGINT', () => { children.forEach((child) => child.kill()); process.exit(0); });
