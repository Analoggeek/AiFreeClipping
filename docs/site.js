(async () => {
  const container = document.getElementById('downloads');
  try {
    const response = await fetch('https://api.github.com/repos/Analoggeek/AiFreeClipping/releases/latest', {headers:{Accept:'application/vnd.github+json'}});
    if (!response.ok) throw new Error('Release unavailable');
    const release = await response.json();
    container.replaceChildren();
    for (const asset of release.assets || []) {
      const name = asset.name.toLowerCase();
      let label = name.endsWith('setup.exe') ? 'Windows · Download .exe' :
        name.endsWith('.dmg') ? (name.includes('intel') ? 'macOS Intel · Download .dmg' : 'macOS Apple Silicon · Download .dmg') :
        name.endsWith('.deb') ? 'Linux · Download .deb' : null;
      if (!label || !asset.browser_download_url.startsWith('https://github.com/Analoggeek/AiFreeClipping/releases/download/')) continue;
      const link = document.createElement('a');
      link.textContent = label + ' ↗'; link.href = asset.browser_download_url;
      container.append(link);
    }
    if (!container.children.length) throw new Error('No installers published');
    document.getElementById('release-note').textContent = `${release.tag_name} · Published GitHub assets. Intel compatibility of older releases is still under review; see release notes before installation.`;
  } catch (_) {
    container.textContent = 'Cannot load installers right now. Use the GitHub releases link below.';
  }
})();
