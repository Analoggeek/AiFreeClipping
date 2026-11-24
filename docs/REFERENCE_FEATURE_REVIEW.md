# DigiRG Cloud reference review

Reviewed: https://github.com/DIGIRGCLOUD/DIGIRGCLIPPINGFREE
Pinned revision: `0987925fa4e99c5d90c68239dc8071421c56d121`.
License: MIT; original attribution and permission notice retained in
`THIRD_PARTY_NOTICES.md` and included by the native freezer.

## Imported and integrated

`layouts.py` geometry and FFmpeg graph builder adapted in
`clipos/video/layouts.py`: 11 composition choices, adjustable camera proportion,
blurred background fill, corner overlays, circular mask and side-by-side columns.
Normalized CLIPOS crop adapter, missing-camera fallback, native Qt selection/icons,
shared render settings, timeline label namespacing and regression tests are local
integration work. Original stacked composition remains the default. No existing
CLIPOS feature removed.

## Already available — not replaced

One-click import/edit, local transcription, word-timed styled captions, highlight
selection, manual source regions/ranges, rendering, timeline editing, CPU/native
encoder fallback and grouped batch delivery already exist in CLIPOS. Their
implementations remain intact rather than importing a second conflicting pipeline.

## Reviewed but not imported in this change

Opening-hook UI/ASS treatments, branding packages, Hinglish transliteration,
transcript re-editing, live stream/chat monitoring, creator recording, and phone
remote require their own integration/privacy/dependency review. They are not
claimed implemented. In particular, no web server, channel watcher, live recorder,
account/publishing code, installer scripts or upstream branding/donation UI is
silently added to the offline native app.

## Validation scope

Every layout has a real FFmpeg render test; representative new layouts also have
multi-segment timeline/caption render tests. Hardware OS performance/driver and
physical installer testing cannot be inferred from Linux tests.
