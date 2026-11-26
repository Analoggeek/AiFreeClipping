/* Browser fallback launcher: local engine + Vite + default browser, no Electron needed. */
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const root = path.join(__dirname, '..');
const dataDir = path.join(os.homedir(), '.AiFreeClipping');
const tokenPath = path.join(dataDir, '.api_token');
const port = Number(process.env.AIFREECLIP_PORT || 8787);
const webPort = Number(process.env.AIFREECLIP_WEB_PORT || 5173);
const apiBase = process.env.AIFREECLIP_API_BASE || `http://127.0.0.1:${port}`;
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

function ping(url) {
  return new Promise((resolve) => {
    http.get(url, (response) => { response.resume(); resolve(response.statusCode < 500); })
      .on('error', () => resolve(false));
  });
}

async function waitFor(predicate, label, attempts = 120) {
  for (let i = 0; i < attempts; i++) {
    if (await predicate()) return true;
    await sleep(500);
  }
  throw new Error(`Timed out waiting for ${label}`);
}

function openBrowser(url) {
  const command = process.platform === 'darwin' ? 'open' : process.platform === 'win32' ? 'start' : 'xdg-open';
  const child = spawn(command, [url], { shell: process.platform === 'win32', stdio: 'ignore', detached: true });
  child.on('error', () => undefined);
  child.unref();
}

(async () => {
  fs.mkdirSync(dataDir, { recursive: true });
  let engineReused = false;
  if (fs.existsSync(tokenPath) && await ping(`http://127.0.0.1:${port}/api/health`)) {
    console.log(`Reusing local engine on port ${port}`);
    engineReused = true;
  }
  if (!engineReused) {
    if (fs.existsSync(tokenPath)) fs.unlinkSync(tokenPath);
    const python = fs.existsSync(path.join(root, '.venv', 'bin', 'python'))
      ? path.join(root, '.venv', 'bin', 'python')
      : fs.existsSync(path.join(root, '.venv', 'Scripts', 'python.exe'))
        ? path.join(root, '.venv', 'Scripts', 'python.exe')
        : 'python3';
    console.log('Starting local AI engine…');
    run(python, ['-m', 'backend.app.main'], {
      PYTHONPATH: path.join(root, 'backend'),
      AIFREECLIP_PORT: String(port),
      PYTHONUNBUFFERED: '1',
    });
    await waitFor(() => fs.existsSync(tokenPath), 'local engine');
  }
  const token = fs.readFileSync(tokenPath, 'utf8').trim();
  console.log('Starting web studio…');
  run('npm', ['run', 'dev', '--', '--port', String(webPort)], {});
  await waitFor(() => ping(`http://127.0.0.1:${webPort}`), 'web studio');
  const url = `http://127.0.0.1:${webPort}?token=${encodeURIComponent(token)}&api=${encodeURIComponent(apiBase)}`;
  console.log('\nAI Clipper Pro is ready:\n' + url + '\n');
  openBrowser(url);
})().catch((error) => {
  console.error(error);
  children.forEach((child) => child.kill());
  process.exitCode = 1;
});

process.on('SIGINT', () => { children.forEach((child) => child.kill()); process.exit(0); });
