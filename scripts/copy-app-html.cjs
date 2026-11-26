/* Keep dist/index.html as the packaged app entry while the repo root serves the marketing site. */
const fs = require('fs');
const path = require('path');

const dist = path.join(__dirname, '..', 'dist');
const source = path.join(dist, 'app.html');
const target = path.join(dist, 'index.html');
if (fs.existsSync(source)) fs.copyFileSync(source, target);
else console.warn('dist/app.html not found; skipped copy');
