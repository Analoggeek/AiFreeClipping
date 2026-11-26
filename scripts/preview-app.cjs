/* Local preview server: serves the built app on :8080 and proxies the Python engine.
   Dev-only helper — the packaged desktop app does not use this. */
const http = require('http');
const fs = require('fs');
const os = require('os');
const path = require('path');

const PORT = Number(process.env.PREVIEW_PORT || 8080);
const BACKEND_PORT = Number(process.env.AIFREECLIP_PORT || 8787);
const DIST = path.join(__dirname, '..', 'dist');
const TOKEN_FILE = path.join(os.homedir(), '.AiFreeClipping', '.api_token');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.json': 'application/json',
  '.wasm': 'application/wasm',
};

function token() {
  return fs.readFileSync(TOKEN_FILE, 'utf8').trim();
}

function proxy(req, res, url) {
  const options = {
    hostname: '127.0.0.1',
    port: BACKEND_PORT,
    path: url.pathname + url.search,
    method: req.method,
    headers: { ...req.headers, host: `127.0.0.1:${BACKEND_PORT}` },
  };
  const upstream = http.request(options, (response) => {
    res.writeHead(response.statusCode || 502, response.headers);
    response.pipe(res);
  });
  upstream.on('error', (error) => {
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ detail: `Local engine unavailable: ${error.message}` }));
  });
  req.pipe(upstream);
}

http.createServer((req, res) => {
  const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/media/')) {
    return proxy(req, res, url);
  }
  let relative = decodeURIComponent(url.pathname);
  if (relative === '/' || relative === '') relative = '/index.html';
  const file = path.join(DIST, relative);
  if (!file.startsWith(DIST)) {
    res.writeHead(403); res.end('Forbidden'); return;
  }
  fs.readFile(file, (error, content) => {
    if (error) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('Not found');
      return;
    }
    let body = content;
    const type = MIME[path.extname(file).toLowerCase()] || 'application/octet-stream';
    if (file.endsWith('index.html')) {
      const inject = `<script>(function(){var u=new URL(window.location.href);u.searchParams.set('token',${JSON.stringify(token())});u.searchParams.set('api','');window.history.replaceState(null,'',u.toString());})();</script>`;
      body = Buffer.from(content.toString().replace('</head>', `${inject}</head>`));
    }
    res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-store' });
    res.end(body);
  });
}).listen(PORT, '0.0.0.0', () => {
  console.log(`AI Clipper Pro app preview on http://0.0.0.0:${PORT} (engine :${BACKEND_PORT})`);
});
