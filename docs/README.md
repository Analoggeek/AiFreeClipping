# Ai clipping PRO website

Responsive, dependency-free product website for the published **v3.6.1** native
application. GitHub Pages serves `main:/docs` at
**https://analoggeek.github.io/AiFreeClipping/**.

## What is included

- Product branding, real compressed app captures, responsive feature cards and downloads.
- Floating brand mark, decorative waveform, hover states and scroll reveals.
- Keyboard-operable screenshot tabs, download filters, mobile navigation, native
  FAQ disclosures, Linux command copy and persisted reduced-motion preference.
- OS reduced-motion support; visible keyboard focus, skip link and semantic landmarks.
- All seven direct v3.6.1 release assets work without JavaScript, with no API request,
  analytics, cookies, external fonts or external runtime dependencies.
- No browser-based video processing demo or fake project/model/download statistics.

README interactions are GitHub-compatible links and collapsible details, not scripts.

## Preview

```sh
python -m http.server 3000 --bind 0.0.0.0 --directory docs
```

## Test

Static contracts run with `python -m pytest tests/test_website.py -q`.
For the browser suite install Playwright and a browser in a development environment:

```sh
pip install playwright
playwright install chromium
python scripts/test_website.py
```

Set `CHROMIUM_EXECUTABLE` to use an existing Chromium binary. The browser suite
starts its own temporary HTTP server; no external network is needed. It checks
mobile/desktop layout, real controls, keyboard tabs, reduced motion, no-JavaScript
fallback, and the absence of unexpected browser errors or third-party requests.

## Publication

Merging the static files into `main` triggers the repository's existing GitHub Pages
branch deployment. The Pages build/deployment result must be checked before claiming
the public site is updated. No desktop installer rebuild or version change is required
for a website/README-only update. Native v3.6.1 installer assets are not replaced.

## Updating the current release

Update the page, README, static tests and sizes together only after a complete
release is published. Do not mix platforms from different releases or point the
feature page at an unknown future release. The visible product name is Ai clipping
PRO; legacy `CLIPOS` asset/executable names intentionally preserve compatibility.

Feature claims must match the shipped application. In particular, no unrestricted effect library, universal realtime playback or live Gemma
quality acceptance is claimed on the current page. See the actual release notes for boundaries.
