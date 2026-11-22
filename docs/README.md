# CLIPOS public download page

Original static website by Analoggeek. No build tools, tracking, external fonts or mandatory analytics.

Preview: `python -m http.server 3000 --bind 0.0.0.0 --directory docs`.
Publish: GitHub repository → Settings → Pages → Deploy from branch → `main`, `/docs`.
It will be available at `https://analoggeek.github.io/AiFreeClipping/` after publication.

Download buttons fetch real published assets from GitHub's latest stable release API.
Network/API failures show a release-page fallback rather than invented download URLs.
Older releases may not contain the changes on this branch; Intel compatibility remains
pending native CI validation. The page warns users accordingly. Interface illustration
is labelled and is not a fabricated processing result.
