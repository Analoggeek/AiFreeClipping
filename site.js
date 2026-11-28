// Static-site enhancements. Everything degrades gracefully when offline.
(function () {
  const navToggle = document.getElementById('nav-toggle');
  const nav = document.getElementById('nav');
  if (navToggle && nav) navToggle.addEventListener('click', () => nav.classList.toggle('open'));
  nav?.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => nav.classList.remove('open')));

  const header = document.getElementById('site-header');
  const onScroll = () => header?.classList.toggle('scrolled', window.scrollY > 24);
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // Cursor glow for desktop visitors.
  const glow = document.getElementById('cursor-glow');
  if (glow && window.matchMedia('(pointer:fine)').matches) {
    window.addEventListener('pointermove', (event) => {
      glow.style.opacity = '1';
      glow.style.left = event.clientX + 'px';
      glow.style.top = event.clientY + 'px';
    });
    document.addEventListener('pointerleave', () => { glow.style.opacity = '0'; });
  }

  // Reveal on scroll.
  const reveals = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) { entry.target.classList.add('in'); observer.unobserve(entry.target); }
      });
    }, { threshold: 0.12 });
    reveals.forEach((element) => observer.observe(element));
  } else {
    reveals.forEach((element) => element.classList.add('in'));
  }

  // Animated counters.
  const counters = document.querySelectorAll('[data-count]');
  const runCounter = (element) => {
    const target = Number(element.dataset.count || 0);
    const start = performance.now();
    const tick = (now) => {
      const progress = Math.min(1, (now - start) / 1100);
      element.textContent = String(Math.round(target * (1 - Math.pow(1 - progress, 3))));
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  };
  if ('IntersectionObserver' in window) {
    const counterObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) { runCounter(entry.target); counterObserver.unobserve(entry.target); }
      });
    }, { threshold: 0.6 });
    counters.forEach((element) => counterObserver.observe(element));
  } else {
    counters.forEach((element) => { element.textContent = element.dataset.count || '0'; });
  }

  // Screenshot tabs.
  const screens = {
    overview: { src: 'assets/screen-overview.svg', title: 'Dashboard', detail: 'Library, live hardware usage and the complete creation pipeline.' },
    clipper: { src: 'assets/screen-clipper.svg', title: 'AI Clipper', detail: 'Region lock, ranked viral moments and one-click effect copying.' },
    editor: { src: 'assets/screen-editor.svg', title: 'Timeline Editor', detail: 'Multi-track editing, captions, stickers, stock media and live inspector.' },
  };
  const image = document.getElementById('screen-image');
  const title = document.getElementById('screen-title');
  const detail = document.getElementById('screen-detail');
  document.querySelectorAll('.screen-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      const key = tab.dataset.screen;
      const screen = screens[key];
      if (!screen || !image) return;
      document.querySelectorAll('.screen-tab').forEach((item) => item.classList.toggle('active', item === tab));
      image.classList.add('switching');
      window.setTimeout(() => {
        image.src = screen.src;
        image.alt = `AI Clipper Pro ${screen.title} screenshot`;
        if (title) title.textContent = screen.title;
        if (detail) detail.textContent = screen.detail;
        image.classList.remove('switching');
      }, 180);
    });
  });

  // Copy source command.
  document.getElementById('copy-command')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    try {
      await navigator.clipboard.writeText('npm install && pip install -r backend/requirements.txt && npm start');
      button.textContent = 'Copied! ✓';
      window.setTimeout(() => { button.textContent = 'Copy source command ⧉'; }, 1800);
    } catch (_) { button.textContent = 'Select and copy the command'; }
  });

  // Latest release links, version line and direct installers.
  (async () => {
    try {
      const response = await fetch('https://api.github.com/repos/Analoggeek/AiFreeClipping/releases/latest');
      if (!response.ok) throw new Error('release lookup failed');
      const release = await response.json();
      const tag = release.tag_name || 'v5.2.6';
      const versionLine = document.getElementById('version-line');
      if (versionLine) {
        versionLine.textContent = `Latest release ${tag} — direct installer links below (GitHub keeps binaries in the collapsible Assets panel). Includes the app, Python engine and FFmpeg; models install inside the app.`;
      }
      document.querySelectorAll('.platform-card[data-file]').forEach((card) => {
        const suffix = card.dataset.file;
        const asset = (release.assets || []).find((item) => item.name.endsWith(suffix));
        if (asset) {
          card.href = asset.browser_download_url;
          card.target = '_blank';
          card.rel = 'noopener';
        }
      });
    } catch (_) {
      // Static v5.2.6 candidate links may not resolve until its installers are published.
    }
  })();
})();
