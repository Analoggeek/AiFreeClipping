// Small enhancements: latest release links, version label, copy command.
(async function () {
  const RELEASES = 'https://api.github.com/repos/Analoggeek/AiFreeClipping/releases/latest';
  try {
    const response = await fetch(RELEASES);
    if (!response.ok) throw new Error('no release');
    const release = await response.json();
    const tag = release.tag_name || 'v1.0.0';
    const versionLine = document.getElementById('version-line');
    if (versionLine) versionLine.textContent = `Latest release ${tag} · installers include the app, Python engine and FFmpeg. Model weights install from the app.`;
    document.querySelectorAll('.platform[data-file]').forEach((card) => {
      const suffix = card.dataset.file;
      const asset = (release.assets || []).find((item) => item.name.endsWith(suffix));
      if (asset) card.href = asset.browser_download_url;
    });
  } catch (_) {
    // Keep links pointing at the releases page when offline or rate-limited.
  }
})();

document.querySelectorAll('[onclick*="clipboard"]').forEach((element) => {
  element.addEventListener('click', async (event) => {
    event.preventDefault();
    const command = 'npm install && npm run dev:app';
    try {
      await navigator.clipboard.writeText(command);
      element.textContent = 'Copied! ✓';
      setTimeout(() => { element.textContent = 'Copy command ⧉'; }, 1800);
    } catch (_) { /* clipboard unavailable */ }
  });
});
