# CLIPOS 2.0.0 — Gaming Studio

## One-click workflow

1. Open **Gaming Studio 2.0** (the default landing page).
2. Paste an authorised public YouTube URL or select a local recording.
3. Click **One-click · Find moments, edit & render**. The first run downloads the
   selected speech model if needed. A failed download is reported, not faked.
4. Review actual rendered MP4s in the embedded player, with play/pause and seek.
   If your platform's Qt multimedia backend is unavailable, use **Open in player**.
5. Review/edit the title, description and keywords for each clip. Check only the
   clips you want to send. Choose audience and visibility; private is the default.
6. Connect your account once, confirm reuse rights, then click **Upload checked
   clips** and approve the final visibility/count confirmation.

Download/edit never starts an upload. This is finished-video playback, not a
zero-latency, real-time effects compositor while FFmpeg is still rendering.
Longer native renders must complete before those clips can be reviewed.

## Automatic player framing

YuNet (or Haar fallback) examines up to 24 downscaled frames for each clip.
Small, stationary faces repeatedly detected near a frame edge are facecam
candidates. A stable inferred region includes hair and shoulders and is cropped
into the lower third. The largest available region excluding that rectangle is
cropped to fill the upper gameplay panel. No arbitrary centre strip is duplicated.

This is **not** a trained semantic human-vs-game-character segmentation model.
Stationary HUD portraits, animated avatars, multiple players, unusual overlays,
scene changes and low-resolution cameras may cause misses/false positives.
Inspect every result. If confidence is insufficient, the output is gameplay-only
and the UI reports a warning. Advanced manual facecam rectangles remain in
Export Center; disable automatic framing there to override a mistaken detection.
Full-width UI/HUD can be lost in a crop-filled portrait composition; review it.

Clean Professional captions sit just above the panel split. Optional clarity
adds restrained SDR contrast, saturation and sharpening. It is **not HDR**, game
recognition, invented highlights or a guarantee of professional editorial taste.
Highlight ranking is based on available audio/visual/speech signals; missing
speech, poor source audio and scarce meaningful moments reduce output quality.

## YouTube setup (one time, per installation)

1. In your own Google Cloud project enable **YouTube Data API v3**.
2. Configure the OAuth consent screen. While in testing mode, add your channel's
   Google account as an allowed test user.
3. Create an OAuth client of type **Desktop app**, download the original client
   JSON, and choose it with **Connect YouTube account**. Do not use a web client.
4. Complete the Google consent flow in your browser. CLIPOS requests only the
   `youtube.upload` scope and stores tokens in the OS secure keychain (macOS
   Keychain, Windows Credential Manager, or supported Linux Secret Service/KWallet).
   No plaintext-token fallback is provided. Enable a supported keychain on Linux.
5. On disconnect the local token is removed. To revoke Google's grant too, use
   your Google account's third-party access settings.

Do not paste credentials or refresh tokens into chat/source control. No shared
OAuth secret, uploaded media or account token is bundled with CLIPOS.
Google API app verification/audits, test-user restrictions, account eligibility,
quota and upload limits apply. Unverified API projects may have uploads restricted
to private even when another visibility is requested. Only an actual successful
API response produces an upload URL; errors are shown without a fake success.

Generated metadata is editable, limited to YouTube API sizes, and includes
AI-assisted-editing disclosure plus source attribution when a supported source
URL is available. The user must declare audience and realistic synthetic content
where applicable. Attribution/disclaimers do not establish fair use or grant
permission. No title, tag, thumbnail or software guarantees views/virality.
Identical file uploads are recorded by SHA-256 and not uploaded again automatically.
After interruptions, check YouTube Studio before retrying: a network failure at
commit time may leave a video online without a locally recorded video ID.

## Hardware and visual design

Global sampling is bounded to 180 frames at up to 768-pixel width, rather than
retaining every full-resolution frame of a multi-hour recording. Full-source scene
and audio analysis can still take time. Decoder/filter/encoder threads are bounded
by detected capacity or your requested thread budget; encoding uses supported
hardware with CPU recovery. Faster-Whisper uses CTranslate2 CUDA when available,
otherwise CPU int8 (not unsupported PyTorch MPS). Actual performance depends on
codec, driver, model, disk and device resources; no dedicated GPU is assumed.

The native UI uses layered glass-style gradients, highlight borders and transparent
labels across pages. This is a portable Qt visual treatment, **not native OS
background blur or an ultra-realistic simulation**. Project/media storage remains
on-device except for explicitly initiated source downloads, model downloads,
account authorization and uploads.

## Validation boundaries

Automated tests use real YuNet face detection and FFmpeg rendering on a clearly
labelled synthetic gameplay/NASA-photo fixture, alongside unit-tested consent,
metadata, model discovery, memory bounds and mocked resumable API responses.
A real account upload, all gameplay genres, physical Intel/Apple Silicon/Windows
hardware and native installer update/migration paths still require validation.
