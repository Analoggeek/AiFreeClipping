/* Progressive enhancement: verified v1.1.0 links remain usable without JS/API. */
(() => {
  'use strict';
  const repository = 'https://github.com/Analoggeek/AiFreeClipping';
  const assetPrefix = repository + '/releases/download/';

  function assetType(name) {
    if (/^CLIPOS-Setup\.exe$/i.test(name)) return 'windows';
    if (/^CLIPOS-[\d.]+-arm64\.dmg$/i.test(name)) return 'mac-arm';
    if (/^CLIPOS-[\d.]+-intel\.dmg$/i.test(name)) return 'mac-intel';
    if (/^CLIPOS_[\d.]+_amd64\.deb$/i.test(name)) return 'linux-deb';
    if (/^CLIPOS-arm64\.app\.tar\.gz$/i.test(name)) return 'mac-arm-app';
    if (/^CLIPOS-intel\.app\.tar\.gz$/i.test(name)) return 'mac-intel-app';
    if (/^CLIPOS-[\d.]+-linux-x86_64\.zip$/i.test(name)) return 'linux-zip';
    return null;
  }

  async function refreshRelease() {
    const status = document.getElementById('release-note');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch('https://api.github.com/repos/Analoggeek/AiFreeClipping/releases/latest', {
        headers: {Accept: 'application/vnd.github+json'}, signal: controller.signal
      });
      if (!response.ok) throw new Error('Release service unavailable');
      const release = await response.json();
      if (release.draft || release.prerelease || !/^v\d+\.\d+\.\d+$/.test(release.tag_name)) throw new Error('Not a stable release');
      const assets = new Map();
      for (const asset of release.assets || []) {
        const key = assetType(asset.name || '');
        if (key && typeof asset.browser_download_url === 'string' &&
            asset.browser_download_url.startsWith(assetPrefix + release.tag_name + '/')) {
          assets.set(key, asset);
        }
      }
      // Never mix an incomplete new release with old-version platform links.
      const keys = Array.from(document.querySelectorAll('[data-asset]'), link => link.dataset.asset);
      if (!keys.every(key => assets.has(key))) throw new Error('Incomplete release');
      for (const link of document.querySelectorAll('[data-asset]')) {
        const asset = assets.get(link.dataset.asset);
        link.href = asset.browser_download_url;
        const size = document.querySelector(`[data-size="${link.dataset.asset}"]`);
        if (size) size.textContent = release.tag_name + (Number.isFinite(asset.size) && asset.size > 0 ? ' · ' + Math.round(asset.size / 1048576) + ' MiB' : '');
      }
      document.getElementById('release-link').href = repository + '/releases/tag/' + release.tag_name;
      status.textContent = 'Latest stable release · ' + release.tag_name;
    } catch (_) {
      status.textContent = 'Verified release · v1.1.0 — live update check unavailable';
    } finally {
      clearTimeout(timer);
    }
  }
  refreshRelease();
})();
