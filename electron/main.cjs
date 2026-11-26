/* Electron shell: hosts the React UI and manages the bundled local Python engine. */
const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const net = require('net');

const isDev = !app.isPackaged;
// In production this resolves inside app.asar; Electron can load files from there.
const root = path.join(__dirname, '..');
const runtimeCwd = isDev ? root : process.resourcesPath;
const dataDir = path.join(os.homedir(), '.AiFreeClipping');
let backendProcess = null;
let apiBase = '';
let apiToken = '';
let mainWindow = null;

function freePort() {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function findBackendBinary() {
  const resourceRoot = path.join(process.resourcesPath, 'backend_bin');
  if (fs.existsSync(resourceRoot)) {
    const candidates = [];
    const walk = (dir) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (/ai-clipper-backend(\.exe)?$/i.test(entry.name)) candidates.push(full);
      }
    };
    try { walk(resourceRoot); } catch (_) { /* ignore */ }
    const match = candidates.find((file) => file.includes(process.platform === 'darwin' ? 'macos' : process.platform));
    if (match) return { command: match, args: [] };
    if (candidates.length) return { command: candidates[0], args: [] };
  }
  const pythonCandidates = [
    path.join(root, '.venv', 'bin', 'python'),
    path.join(root, '.venv', 'Scripts', 'python.exe'),
    process.env.PYTHON || 'python3',
  ];
  const python = pythonCandidates.find((candidate) => {
    if (candidate.includes('/')) return fs.existsSync(candidate);
    return true;
  });
  return {
    command: python,
    args: ['-m', 'backend.app.main'],
    env: { PYTHONPATH: path.join(root, 'backend') },
  };
}

async function startBackend() {
  fs.mkdirSync(dataDir, { recursive: true });
  const tokenPath = path.join(dataDir, '.api_token');
  if (process.env.AIFREECLIP_EXTERNAL_BACKEND === '1') {
    apiBase = process.env.AIFREECLIP_API_BASE || 'http://127.0.0.1:8787';
    for (let i = 0; i < 40 && !fs.existsSync(tokenPath); i++) await sleep(250);
    apiToken = fs.existsSync(tokenPath) ? fs.readFileSync(tokenPath, 'utf8').trim() : '';
    return;
  }
  if (fs.existsSync(tokenPath)) fs.unlinkSync(tokenPath);
  const port = await freePort();
  apiBase = `http://127.0.0.1:${port}`;
  const binary = findBackendBinary();
  const env = {
    ...process.env,
    ...(binary.env || {}),
    AIFREECLIP_PORT: String(port),
    AIFREECLIP_HOST: '127.0.0.1',
    PYTHONUNBUFFERED: '1',
  };
  if (!binary.command.includes('python') && !binary.command.includes('Python')) {
    // Packaged binaries read the token from the same file; nothing else needed.
  }
  backendProcess = spawn(binary.command, binary.args, {
    cwd: runtimeCwd,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  backendProcess.stdout.on('data', (chunk) => console.log('[engine]', chunk.toString().trim()));
  backendProcess.stderr.on('data', (chunk) => console.error('[engine]', chunk.toString().trim()));
  backendProcess.on('exit', (code) => {
    console.warn('[engine] exited with', code);
    backendProcess = null;
  });

  for (let i = 0; i < 90; i++) {
    if (fs.existsSync(tokenPath)) {
      apiToken = fs.readFileSync(tokenPath, 'utf8').trim();
      try {
        const response = await fetch(`${apiBase}/api/health`, { headers: { 'X-AI-Clipper-Token': apiToken } });
        if (response.ok) return;
      } catch (_) { /* still starting */ }
    }
    await sleep(400);
  }
  throw new Error('The local AI engine did not start. Check that Python 3.11+ and the bundled runtime are installed.');
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1120,
    minHeight: 720,
    backgroundColor: '#090b14',
    title: 'AI Clipper Pro — made by analoggeek',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      webSecurity: true,
    },
  });
  if (isDev) {
    await mainWindow.loadURL(
      `http://127.0.0.1:5173?token=${encodeURIComponent(apiToken)}&api=${encodeURIComponent(apiBase)}`
    );
  } else {
    await mainWindow.loadFile(path.join(root, 'dist', 'index.html'), {
      query: { token: apiToken, api: apiBase },
    });
  }
  if (isDev) mainWindow.webContents.openDevTools({ mode: 'detach' });
}

app.whenReady().then(async () => {
  ipcMain.on('app:token', (event) => { event.returnValue = apiToken; });
  ipcMain.on('app:api-base', (event) => { event.returnValue = apiBase; });
  ipcMain.handle('dialog:files', async (_event, filters) => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openFile', 'multiSelections'],
      filters: filters || [
        { name: 'Media', extensions: ['mp4', 'mov', 'mkv', 'webm', 'avi', 'mp3', 'wav', 'm4a', 'png', 'jpg', 'jpeg', 'webp', 'gif'] },
        { name: 'All files', extensions: ['*'] },
      ],
    });
    return result.canceled ? [] : result.filePaths;
  });
  ipcMain.handle('dialog:directory', async () => {
    const result = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory'] });
    return result.canceled ? '' : result.filePaths[0];
  });
  ipcMain.handle('shell:open', async (_event, target) => shell.openPath(String(target)));
  ipcMain.handle('shell:reveal', async (_event, target) => shell.showItemInFolder(String(target)));
  ipcMain.handle('app:info', async () => ({
    version: app.getVersion(),
    platform: process.platform,
    arch: process.arch,
    dataDir,
    apiBase,
  }));
  try {
    await startBackend();
    await createWindow();
  } catch (error) {
    dialog.showErrorBox('AI Clipper Pro could not start', String(error && error.message ? error.message : error));
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
app.on('before-quit', () => {
  if (backendProcess && !backendProcess.killed) {
    try { backendProcess.kill('SIGTERM'); } catch (_) { /* ignore */ }
  }
});
