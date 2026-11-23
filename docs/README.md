# CLIPOS website — Analoggeek

Responsive static product website and download centre. No npm build step,
tracking, external font service or mandatory JavaScript dependency.

## Files
- `index.html`: product page, four platform download cards, all seven release
  assets, installation guidance and FAQ.
- `style.css`: responsive dark/mint design and reduced-motion support.
- `site.js`: optional latest-stable-release discovery from GitHub.
- `logo.svg`: original CLIPOS brand mark.

## Preview
```sh
python -m http.server 3000 --bind 0.0.0.0 --directory docs
```

## Publish with GitHub Pages
After merging these files, open repository **Settings → Pages → Deploy from a
branch → main → /docs → Save**. The expected URL after successful publication is
`https://analoggeek.github.io/AiFreeClipping/`. A custom domain can be configured
in the same settings. Files can also be hosted by any static host.

## Download behaviour
All seven fallback URLs were verified against the published **v1.1.0** release:
Windows EXE, Apple Silicon DMG, Intel DMG, Linux DEB, both macOS app archives and
Linux portable ZIP. They work without JavaScript and remain available when the
GitHub API is rate-limited or offline (the download itself requires internet).
The optional API check has an eight-second timeout and switches links only when
a complete newer stable release has compatible assets. It does not infer Mac
architecture from a browser or redirect users to an arbitrary installer.

The studio illustration is labelled as illustrative, not a real processing demo.
The website does not guarantee views or claim physical-device certification.
