# Release notes

## v5.2.5 — verified installers for every platform

### Download the installers

- **Windows x64:** [AI-Clipper-Pro-5.2.5-Windows-x64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.5/AI-Clipper-Pro-5.2.5-Windows-x64.exe)
- **Windows ARM64:** [AI-Clipper-Pro-5.2.5-Windows-arm64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.5/AI-Clipper-Pro-5.2.5-Windows-arm64.exe)
- **macOS Intel:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.5/AI-Clipper-Pro-5.2.5-macOS-x64.dmg) · [ZIP fallback](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.5/AI-Clipper-Pro-5.2.5-macOS-x64.zip)
- **macOS Apple Silicon:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.5/AI-Clipper-Pro-5.2.5-macOS-arm64.dmg) · [ZIP fallback](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.5/AI-Clipper-Pro-5.2.5-macOS-arm64.zip)
- **Linux AppImage:** [AI-Clipper-Pro-5.2.5-Linux-x86_64.AppImage](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.5/AI-Clipper-Pro-5.2.5-Linux-x86_64.AppImage)
- **Linux Debian/Ubuntu:** [AI-Clipper-Pro-5.2.5-Linux-amd64.deb](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.5/AI-Clipper-Pro-5.2.5-Linux-amd64.deb)
- **Checksums:** [SHA256SUMS.txt](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.5/SHA256SUMS.txt) · **Manifest:** [manifest.json](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.5/manifest.json)

### Changes

- Rebuild every supported Windows, macOS, and Linux installer from the same v5.2.5 source, with one CPU architecture per Windows/macOS matrix job so each package contains the matching local engine.
- Verify Windows PE headers and Linux AppImage/DEB structure; for both macOS architectures, mount/copy the DMG and extract the ZIP, then confirm the app's Electron Framework binary is present, linked by the app executable, and matches the target CPU.
- Download every published installer and compare it against its SHA-256 manifest before the release workflow succeeds.
- Keep both macOS architecture ZIPs as first-class alternatives if a local DMG download is damaged or will not mount. For v5.2.4 installations reporting a missing Electron Framework, remove the old app and replace it with the matching v5.2.5 ZIP.

## v5.2.4 — macOS disk-image reliability hotfix

### Download the installers

- **Windows x64:** [AI-Clipper-Pro-5.2.4-Windows-x64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/AI-Clipper-Pro-5.2.4-Windows-x64.exe)
- **Windows ARM64:** [AI-Clipper-Pro-5.2.4-Windows-arm64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/AI-Clipper-Pro-5.2.4-Windows-arm64.exe)
- **macOS Intel:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/AI-Clipper-Pro-5.2.4-macOS-x64.dmg) · [ZIP fallback](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/AI-Clipper-Pro-5.2.4-macOS-x64.zip)
- **macOS Apple Silicon:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/AI-Clipper-Pro-5.2.4-macOS-arm64.dmg) · [ZIP fallback](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/AI-Clipper-Pro-5.2.4-macOS-arm64.zip)
- **Linux AppImage:** [AI-Clipper-Pro-5.2.4-Linux-x86_64.AppImage](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/AI-Clipper-Pro-5.2.4-Linux-x86_64.AppImage)
- **Linux Debian/Ubuntu:** [AI-Clipper-Pro-5.2.4-Linux-amd64.deb](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/AI-Clipper-Pro-5.2.4-Linux-amd64.deb)
- **Checksums:** [SHA256SUMS.txt](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/SHA256SUMS.txt) · **Manifest:** [manifest.json](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.4/manifest.json)

### Changes

- Rebuild macOS disk images as **read-only, uncompressed UDRO** images, removing the compression layer and adding stricter mount-time verification for the reported unreadable-disk issue.
- Keep the signed-off install path explicit: CI checks the DMG format, verifies and mounts the image, copies the `.app`, and validates the matching ZIP for both Intel and Apple Silicon builds.
- Publish both macOS ZIPs as first-class alternatives, with direct links and checksum guidance. If a DMG still fails to mount, verify the downloaded SHA-256 and use the matching ZIP.

## v5.2.3 — composition controls, editable captions and hardware-matched models

### Download the installers

- **Windows x64:** [AI-Clipper-Pro-5.2.3-Windows-x64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.3/AI-Clipper-Pro-5.2.3-Windows-x64.exe)
- **Windows ARM64:** [AI-Clipper-Pro-5.2.3-Windows-arm64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.3/AI-Clipper-Pro-5.2.3-Windows-arm64.exe)
- **macOS Intel:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.3/AI-Clipper-Pro-5.2.3-macOS-x64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.3/AI-Clipper-Pro-5.2.3-macOS-x64.zip)
- **macOS Apple Silicon:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.3/AI-Clipper-Pro-5.2.3-macOS-arm64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.3/AI-Clipper-Pro-5.2.3-macOS-arm64.zip)
- **Linux AppImage:** [AI-Clipper-Pro-5.2.3-Linux-x86_64.AppImage](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.3/AI-Clipper-Pro-5.2.3-Linux-x86_64.AppImage)
- **Linux Debian/Ubuntu:** [AI-Clipper-Pro-5.2.3-Linux-amd64.deb](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.3/AI-Clipper-Pro-5.2.3-Linux-amd64.deb)
- **Checksums:** [SHA256SUMS.txt](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.3/SHA256SUMS.txt) · **Manifest:** [manifest.json](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.3/manifest.json)

### Changes

- **Adjustable compositions:** resize player/gameplay split panels and choose no, clean, neon or double outlines; the Clipper, Editor, individual renders, batch exports and timeline renderer share the same settings.
- **Better clip copy:** transcripts seed concise social captions; an optional local Gemma pass refines titles and captions without changing source timing. Edit and save the hook/title and social caption on each result.
- **Selectable burned-in captions:** choose hype, karaoke, minimal or premium styles. The selected style, color look and audio settings carry into individual and batch exports.
- **Day/night theme:** toggle between dark and light appearance; the choice persists between launches.
- **Editor timecode:** the playhead and total duration now sit inside the video frame, above transport controls.
- **Front-screen branding and motion:** the overview uses the app icon, and the interface receives smoother theme and control transitions.
- **Hardware-aware model setup:** recommends Whisper Small/Medium and Gemma 3 4B, Gemma 2 7B or Gemma 3 12B based on RAM and detected GPU memory; YOLOX Nano remains part of the compact local set, while SDXL stays optional.

## v5.2.2 — streamlined Editor and local media imports

### Download the installers

- **Windows x64:** [AI-Clipper-Pro-5.2.2-Windows-x64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.2/AI-Clipper-Pro-5.2.2-Windows-x64.exe)
- **Windows ARM64:** [AI-Clipper-Pro-5.2.2-Windows-arm64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.2/AI-Clipper-Pro-5.2.2-Windows-arm64.exe)
- **macOS Intel:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.2/AI-Clipper-Pro-5.2.2-macOS-x64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.2/AI-Clipper-Pro-5.2.2-macOS-x64.zip)
- **macOS Apple Silicon:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.2/AI-Clipper-Pro-5.2.2-macOS-arm64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.2/AI-Clipper-Pro-5.2.2-macOS-arm64.zip)
- **Linux AppImage:** [AI-Clipper-Pro-5.2.2-Linux-x86_64.AppImage](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.2/AI-Clipper-Pro-5.2.2-Linux-x86_64.AppImage)
- **Linux Debian/Ubuntu:** [AI-Clipper-Pro-5.2.2-Linux-amd64.deb](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.2/AI-Clipper-Pro-5.2.2-Linux-amd64.deb)
- **Checksums:** [SHA256SUMS.txt](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.2/SHA256SUMS.txt) · **Manifest:** [manifest.json](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.2/manifest.json)

### Changes

- **Simplified Editor:** the asset panel now contains only **Clips** and **Media**; Stock, AI Art, and SFX tabs and shortcuts have been removed.
- **Clip preview and replacement:** selecting an AI clip immediately focuses it in the preview and replaces the previous video selection on the timeline instead of appending another clip. Auto Edit layers linked to the replaced clip are cleaned up.
- **Local media imports:** import supported video files directly from the Editor's Media panel, then add imported videos to the editable timeline.
- **Cleaner handoff:** opening a clip from Clipper no longer creates a duplicate project before the Editor loads it.

## v5.2.1 — stale-media recovery during clip discovery

### Download the installers

- **Windows x64:** [AI-Clipper-Pro-5.2.1-Windows-x64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.1/AI-Clipper-Pro-5.2.1-Windows-x64.exe)
- **Windows ARM64:** [AI-Clipper-Pro-5.2.1-Windows-arm64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.1/AI-Clipper-Pro-5.2.1-Windows-arm64.exe)
- **macOS Intel:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.1/AI-Clipper-Pro-5.2.1-macOS-x64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.1/AI-Clipper-Pro-5.2.1-macOS-x64.zip)
- **macOS Apple Silicon:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.1/AI-Clipper-Pro-5.2.1-macOS-arm64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.1/AI-Clipper-Pro-5.2.1-macOS-arm64.zip)
- **Linux AppImage:** [AI-Clipper-Pro-5.2.1-Linux-x86_64.AppImage](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.1/AI-Clipper-Pro-5.2.1-Linux-x86_64.AppImage)
- **Linux Debian/Ubuntu:** [AI-Clipper-Pro-5.2.1-Linux-amd64.deb](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.1/AI-Clipper-Pro-5.2.1-Linux-amd64.deb)
- **Checksums:** [SHA256SUMS.txt](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.1/SHA256SUMS.txt) · **Manifest:** [manifest.json](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.1/manifest.json)

### Changes

- **Stale media selection recovery:** the Clipper refreshes its selected IDs against the current library and checks again before analysis, so removing a video no longer leaves a dead selection that fails the job.
- **Partial batch resilience:** clip discovery skips media that disappeared after selection, continues with available videos, and reports a warning. If none remain, it returns a clear refresh-and-select message instead of a raw missing-ID error.

## v5.2.0 — shot-aware subject tracking for portrait clips

### Download the installers

- **Windows x64:** [AI-Clipper-Pro-5.2.0-Windows-x64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.0/AI-Clipper-Pro-5.2.0-Windows-x64.exe)
- **Windows ARM64:** [AI-Clipper-Pro-5.2.0-Windows-arm64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.0/AI-Clipper-Pro-5.2.0-Windows-arm64.exe)
- **macOS Intel:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.0/AI-Clipper-Pro-5.2.0-macOS-x64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.0/AI-Clipper-Pro-5.2.0-macOS-x64.zip)
- **macOS Apple Silicon:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.0/AI-Clipper-Pro-5.2.0-macOS-arm64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.0/AI-Clipper-Pro-5.2.0-macOS-arm64.zip)
- **Linux AppImage:** [AI-Clipper-Pro-5.2.0-Linux-x86_64.AppImage](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.0/AI-Clipper-Pro-5.2.0-Linux-x86_64.AppImage)
- **Linux Debian/Ubuntu:** [AI-Clipper-Pro-5.2.0-Linux-amd64.deb](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.0/AI-Clipper-Pro-5.2.0-Linux-amd64.deb)
- **Checksums:** [SHA256SUMS.txt](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.0/SHA256SUMS.txt) · **Manifest:** [manifest.json](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.2.0/manifest.json)

### Changes

- **Smart portrait framing:** when a portrait clip uses the full frame and the local detector finds a subject, the crop follows one stable tracked subject, resists small detector jitter and snaps on scene cuts instead of panning across them. Manually marked regions and multi-panel layouts keep their existing crop behavior; sources without a usable track retain the existing render fallback.
- **Consistent saved crop paths:** the analyzed path is clipped to each candidate's exact source-time window and carried through individual render, Auto Edit, batch export, editor preview and timeline export.
- **Whole-video analysis sampling:** the bounded vision sample budget is distributed over long sources instead of stopping at the first 900 decoded frames.
- **No interface redesign:** the existing Clipper, region selection and Editor workflows remain in place.

## v5.1.8 — dependable editor playback, editable Auto Edit and explicit AI art

### Download the installers

- **Windows x64:** [AI-Clipper-Pro-5.1.8-Windows-x64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.8/AI-Clipper-Pro-5.1.8-Windows-x64.exe)
- **Windows ARM64:** [AI-Clipper-Pro-5.1.8-Windows-arm64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.8/AI-Clipper-Pro-5.1.8-Windows-arm64.exe)
- **macOS Intel:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.8/AI-Clipper-Pro-5.1.8-macOS-x64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.8/AI-Clipper-Pro-5.1.8-macOS-x64.zip)
- **macOS Apple Silicon:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.8/AI-Clipper-Pro-5.1.8-macOS-arm64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.8/AI-Clipper-Pro-5.1.8-macOS-arm64.zip)
- **Linux AppImage:** [AI-Clipper-Pro-5.1.8-Linux-x86_64.AppImage](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.8/AI-Clipper-Pro-5.1.8-Linux-x86_64.AppImage)
- **Linux Debian/Ubuntu:** [AI-Clipper-Pro-5.1.8-Linux-amd64.deb](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.8/AI-Clipper-Pro-5.1.8-Linux-amd64.deb)
- **Checksums:** [SHA256SUMS.txt](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.8/SHA256SUMS.txt) · **Manifest:** [manifest.json](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.8/manifest.json)

### Changes

- **Single Auto Edit action:** the Editor has one Auto Edit button beside Export; its style, format, resolution, music, captions, SFX, stickers and blur-fill preferences now live in Settings.
- **Real editable output:** Auto Edit applies speed/color treatment and returns its source cut, selected crops/layout, timed captions, music, sound effects and stickers as editable tracks in a saved project, alongside its rendered MP4s.
- **Reliable preview playback:** the canvas preview seeks and plays at each clip's actual speed, changes between timeline clips, and renders the same color treatment and selected composition as export.
- **Media cleanup:** remove items directly from the Editor's media library; successful deletion immediately removes the row and clears its selection.
- **Honest AI Art:** request up to three alternatives, choose one to add, and see partial-provider failures. If no image model is available, generation reports that instead of silently substituting decorative fallback art.
- **Player/gameplay composition parity:** the chosen top/bottom or side-by-side region order is retained on discovered clips and shared across preview, Auto Edit and timeline export.
- **UI cleanup:** removed the “Saved locally,” “Clip edit,” and “Timeline editor” labels.

## v5.1.7 — source-quality exports, composition parity and resilient Auto Edit

### Download the installers

- **Windows x64:** [AI-Clipper-Pro-5.1.7-Windows-x64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.7/AI-Clipper-Pro-5.1.7-Windows-x64.exe)
- **Windows ARM64:** [AI-Clipper-Pro-5.1.7-Windows-arm64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.7/AI-Clipper-Pro-5.1.7-Windows-arm64.exe)
- **macOS Intel:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.7/AI-Clipper-Pro-5.1.7-macOS-x64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.7/AI-Clipper-Pro-5.1.7-macOS-x64.zip)
- **macOS Apple Silicon:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.7/AI-Clipper-Pro-5.1.7-macOS-arm64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.7/AI-Clipper-Pro-5.1.7-macOS-arm64.zip)
- **Linux AppImage:** [AI-Clipper-Pro-5.1.7-Linux-x86_64.AppImage](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.7/AI-Clipper-Pro-5.1.7-Linux-x86_64.AppImage)
- **Linux Debian/Ubuntu:** [AI-Clipper-Pro-5.1.7-Linux-amd64.deb](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.7/AI-Clipper-Pro-5.1.7-Linux-amd64.deb)
- **Checksums:** [SHA256SUMS.txt](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.7/SHA256SUMS.txt) · **Manifest:** [manifest.json](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.7/manifest.json)

### Changes

- **Composition parity:** Clipper and Editor previews now share crop/region composition rules with FFmpeg exports, including stacked player/gameplay layouts and picture-in-picture.
- **Quality and folders:** source quality is the default; selected resolution and aspect carry through clip, batch, Auto Edit and project exports. New exports are grouped into date-named folders under the configured export folder.
- **Resilient Auto Edit:** missing sources are skipped with warnings, transcription failures fall back to the saved candidate transcript or a title card, and titles/captions/crops/effects persist for later batch exports.
- **Persisted local models:** saved Whisper, Ollama, Vision and Piper selections and local weights are reused after restarting the app.
- **Polish:** the splash screen uses the packaged brand mark, and finished operations auto-dismiss after five seconds.
- **Branding remains opt-in:** exports have no app watermark by default; only a user-configured channel logo is applied.

## v5.1.6 — QuickTime-ready exports, custom branding and creator workflow

### Download the installers

Download the installer for your platform from the links below:

- **Windows x64:** [AI-Clipper-Pro-5.1.6-Windows-x64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.6/AI-Clipper-Pro-5.1.6-Windows-x64.exe)
- **Windows ARM64:** [AI-Clipper-Pro-5.1.6-Windows-arm64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.6/AI-Clipper-Pro-5.1.6-Windows-arm64.exe)
- **macOS Intel:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.6/AI-Clipper-Pro-5.1.6-macOS-x64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.6/AI-Clipper-Pro-5.1.6-macOS-x64.zip)
- **macOS Apple Silicon:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.6/AI-Clipper-Pro-5.1.6-macOS-arm64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.6/AI-Clipper-Pro-5.1.6-macOS-arm64.zip)
- **Linux AppImage:** [AI-Clipper-Pro-5.1.6-Linux-x86_64.AppImage](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.6/AI-Clipper-Pro-5.1.6-Linux-x86_64.AppImage)
- **Linux Debian/Ubuntu:** [AI-Clipper-Pro-5.1.6-Linux-amd64.deb](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.6/AI-Clipper-Pro-5.1.6-Linux-amd64.deb)
- **Checksums:** [SHA256SUMS.txt](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.6/SHA256SUMS.txt) · **Manifest:** [manifest.json](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.6/manifest.json)

### Changes

- **Region selection is real:** custom focus regions are drawn against the source video's contained frame, shown in a live side crop preview, carried with each generated clip, and applied to both clip and timeline MP4 renders.
- **Editor clip workflow:** the Editor now lists generated AI clips in its Clips tab; click one to add its source cut and saved focus region straight to the timeline.
- **Library cleanup:** remove downloaded videos with an explicit confirmation. Imported originals are kept, and downloaded source files are retained when another library item or saved project still references them.
- **SDXL checkpoint selection:** choose a `.safetensors` or `.ckpt` file already on disk, or point the app at a ComfyUI checkpoints folder, without redownloading large model weights.
- **QuickTime color fix:** FFmpeg's neutral contrast is now `1.0` (not `0`), and exports declare Rec.709 color with limited-range `yuv420p`; old saved contrast values are normalized so existing clips do not export flat/washed out.
- **Optional channel watermark:** app branding is no longer burned into exports. Clip, batch, auto-edit and timeline exports stay unbranded unless you select a PNG/JPG/WEBP logo in Settings; remove it any time.
- **Reliable MP4 downloads:** exports are H.264 High Profile, Rec.709 `yuv420p`, AAC and fast-start MP4s; download responses carry an explicit `.mp4` filename so macOS browsers do not save them as `file.txt`.
- **Safer clip management:** Publish supports Select all, rendered-only selection, bulk export and bulk deletion. Shared outputs are kept until the last clip/project reference is removed, and new render names include unique clip/project IDs.
- **Operations widget:** shows the full recent operation list without a border; close completed operations or cancel live ones. Cancellation now stops FFmpeg and removes partial output files.

## v5.1.4 — crash-proof settings, user folders and automatic editing

### Download the installers

GitHub keeps binaries in the collapsible **Assets** section at the bottom of this release. These links go straight to the files:

- **Windows x64:** [AI-Clipper-Pro-5.1.4-Windows-x64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/AI-Clipper-Pro-5.1.4-Windows-x64.exe)
- **Windows ARM64:** [AI-Clipper-Pro-5.1.4-Windows-arm64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/AI-Clipper-Pro-5.1.4-Windows-arm64.exe)
- **macOS Intel:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/AI-Clipper-Pro-5.1.4-macOS-x64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/AI-Clipper-Pro-5.1.4-macOS-x64.zip)
- **macOS Apple Silicon:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/AI-Clipper-Pro-5.1.4-macOS-arm64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/AI-Clipper-Pro-5.1.4-macOS-arm64.zip)
- **Linux AppImage:** [AI-Clipper-Pro-5.1.4-Linux-x86_64.AppImage](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/AI-Clipper-Pro-5.1.4-Linux-x86_64.AppImage)
- **Linux Debian/Ubuntu:** [AI-Clipper-Pro-5.1.4-Linux-amd64.deb](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/AI-Clipper-Pro-5.1.4-Linux-amd64.deb)
- **Checksums:** [SHA256SUMS.txt](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/SHA256SUMS.txt) · **Manifest:** [manifest.json](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.4/manifest.json)

### Changes

- **No more Settings crash:** folder/settings responses are normalized before rendering, so a missing or null value can never break the view.
- **No more SSL download failures:** every in-app HTTPS request now uses the bundled `certifi` CA store with a standard-library fallback, so model and media downloads work behind custom certificate chains.
- **Choose your folders:** Models, Downloads and Rendered clips can each be pointed at any folder you own with a native folder picker; model weights and runtimes honor the chosen location.
- **Hardware-aware auto setup:** on first launch the app detects RAM/GPU and downloads, activates and saves the best offline model pack automatically, with one visible progress line per action.
- **Exact clip counts:** the AI scorer keeps searching non-overlapping windows and enforces the requested number of clips across all selected videos.
- **Automatic edit section:** cut clips appear immediately in the editor, where you can auto-edit all of them (images, captions, motion, SFX, crop focus) or render any single clip directly.
- **True timeline sync:** a fixed track-label gutter and zero-based ruler make the playhead, scrubbing and the starting line agree at every zoom level; the mouse can scrub anywhere along the timeline.
- **Storage HUD:** app-folder usage appears beside the hardware meters, and live operation progress appears directly under the navigation.

## v5.1.3 — automatic models, faster startup, pro timeline and multi-region AI

### Download the installers

GitHub keeps binaries in the collapsible **Assets** section at the bottom of this release. These links go straight to the files:

- **Windows x64:** [AI-Clipper-Pro-5.1.3-Windows-x64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/AI-Clipper-Pro-5.1.3-Windows-x64.exe)
- **Windows ARM64:** [AI-Clipper-Pro-5.1.3-Windows-arm64.exe](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/AI-Clipper-Pro-5.1.3-Windows-arm64.exe)
- **macOS Intel:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/AI-Clipper-Pro-5.1.3-macOS-x64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/AI-Clipper-Pro-5.1.3-macOS-x64.zip)
- **macOS Apple Silicon:** [DMG](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/AI-Clipper-Pro-5.1.3-macOS-arm64.dmg) · [ZIP](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/AI-Clipper-Pro-5.1.3-macOS-arm64.zip)
- **Linux AppImage:** [AI-Clipper-Pro-5.1.3-Linux-x86_64.AppImage](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/AI-Clipper-Pro-5.1.3-Linux-x86_64.AppImage)
- **Linux Debian/Ubuntu:** [AI-Clipper-Pro-5.1.3-Linux-amd64.deb](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/AI-Clipper-Pro-5.1.3-Linux-amd64.deb)
- **Checksums:** [SHA256SUMS.txt](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/SHA256SUMS.txt) · **Manifest:** [manifest.json](https://github.com/Analoggeek/AiFreeClipping/releases/download/v5.1.3/manifest.json)

### Changes

- **Instant startup:** the desktop app now shows an animated splash immediately and loads the React workspace in lazy route chunks while the local engine boots in the background.
- **Fully automatic models:** one click now downloads, installs, activates and saves the model. Ollama itself is downloaded and started automatically for Gemma; Whisper, YOLOX, Piper and SDXL save into `~/.AiFreeClipping` and become the active model in Settings. A **Set up all recommended** button does the whole pipeline in one job.
- **Multi-region AI clipping:** mark several focus areas in the same video — gameplay above/player below, player above/gameplay below, square player over full gameplay, or side-by-side. Video is decoded once, all selected regions are scored, and the AI picks moments using the fused activity.
- **Professional editor:** all editing actions are icon-only in the timeline toolbar; play/pause and 5-second jump controls sit directly below the preview; the playhead scrubs in sync with the ruler and tracks and auto-scrolls with zoom.
- **macOS reliability:** DMGs and ZIPs are built without signing, stripped of AppleDouble/extended-attribute metadata, and verified in CI by mounting and copying the bundle.

## v5.1.2 — stable downloads, compact HUD and root-level site

- **Downloader fixed:** `JobManager.update()` now accepts positional progress/message arguments, so any legacy progress callback works. Download jobs no longer fail mid-run.
- **Model downloads fixed:** the primary card button now downloads **and** installs directly in the app; external links use Electron's proper `openExternal` handler. API-key status reflects keys saved in Settings.
- **Blank-screen guard:** React error boundary plus Electron renderer recovery reloads a crashed view instead of leaving an empty window.
- **Correct version:** the sidebar and health endpoint now show the real app version (from `package.json` / Electron), not `1.0.0`.
- **Cleaner layout:** live hardware usage moved into a compact sidebar panel below Settings and above the version line; duplicate center panels removed. App logo is now a small refined 3D mark.
- **Website at repository root:** the animated marketing site is now `index.html`, `site.css`, `site.js` and `assets/` at the repo root; the React app entry is `app.html`. Site rebuilt with clearer sections and direct installer links.
- **README rewritten:** quick start, model table, hardware tips, structure and troubleshooting in one place.

## v5.1.1 — reliable startup & redesigned site

- **Startup fixed:** added a browser studio launcher (`npm start`) that works without Electron; `npm run dev:app` now falls back to it automatically when the Electron binary is unavailable. Vite accepts proxied preview hosts.
- **Packaged app fix:** the Windows/macOS/Linux engine binary is now matched by both platform **and** architecture, so x64 and ARM64 installers no longer pick the wrong bundled runtime.
- **Website redesigned:** a new immersive static site with an animated hero, bento feature grid, interactive screenshot tabs, tech marquee, hardware section, model/API links and direct installer downloads.
- **Clearer docs:** README and installation guide now lead with the one-command browser start.

## v5.1.0 — 3D studio, one-click model setup & hardware awareness

- **One-click model setup:** every local model card now has a real download URL and a one-click installer that saves weights into `~/.AiFreeClipping/cache`. Cloud models show a direct **Get API key** button (Gemini/Nano Banana, YouTube, Pexels, Pixabay).
- **YOLOX without Torch:** the packaged app downloads the 4 MB YOLOX Nano ONNX model and runs it with OpenCV DNN + the built-in ByteTrack-style tracker. Gemma/Whisper/YOLOX all work offline after the first download.
- **Hardware HUD:** the dashboard and Models page show live CPU, RAM, disk, GPU/encoder and parallel-worker counts. Per-clip render results record the exact hardware used and can be copied with one click.
- **Copy effects to all:** tune one clip, then press **Copy effects to all** to apply the same captions, SFX, speed, color, aspect and reframing settings to every candidate in one request.
- **Fully optimized exports:** batch renders now run in parallel (configurable with `RENDER_WORKERS`), ffmpeg uses all available threads, and NVENC / VideoToolbox is selected automatically when available.
- **New 3D identity:** redesigned neon 3D clapperboard logo across the desktop app, packaging icons and website.
- **Animated responsive website:** a fully static, animated marketing site with live release download links, model/API links and interface screenshots.
- **App polish:** motion, 3D hover depth, focus states, model cards and mobile/desktop responsive layouts throughout.

## v5.0.0 — complete local AI studio

The first full release of **AI Clipper Pro — made by analoggeek**.

### Highlights

- **Downloader:** highest-quality single downloads and full playlists with item selection, subtitles, custom folders and a persistent local media library.
- **AI discovery:** faster-whisper word timings, YOLOX/YOLO11 + ByteTrack activity tracking and Gemma 2 7B reranking combine into ranked viral clip candidates. Player/gameplay region selection is supported.
- **Enhancements:** auto captions with four presets, procedural royalty-free sound effects, stickers, music beds, 9:16 blurred-background reframing, speed/color controls and branding.
- **Editor:** CapCut-style multi-track timeline with split/trim/inspector, local imports, copyright-friendly stock search (Pexels/Pixabay/Openverse), Nano Banana or local ComfyUI SDXL image generation and keyboard shortcuts.
- **Publishing:** one-click 1080p batch export with `+faststart`, downloadable MP4s and optional resumable YouTube uploads through the user's own OAuth app.
- **Release automation:** one-command installer builds for Windows x64/ARM64, macOS Intel/Apple Silicon and Linux x64 via `scripts/release-all.sh` and the GitHub Actions matrix, with SHA256 checksums.

### Offline behavior

The engine binds to `127.0.0.1` with a per-launch token. Model weights download once, then inference, clipping, editing and rendering work offline. Cloud features are opt-in and use user-supplied keys.

### Installers

| Platform | Artifact |
|---|---|
| Windows x64 / ARM64 | `AI-Clipper-Pro-5.0.0-Windows-x64.exe`, `...-arm64.exe` |
| macOS Intel | `AI-Clipper-Pro-5.0.0-macOS-x64.dmg` |
| macOS Apple Silicon | `AI-Clipper-Pro-5.0.0-macOS-arm64.dmg` |
| Linux x64 | `AI-Clipper-Pro-5.0.0-Linux-x64.AppImage`, `...-x64.deb` |

Installers include the Electron UI, a slim PyInstaller Python runtime, FFmpeg and platform icons. Speech and Gemma model packs are installed from the app's **Local Models** page; Torch-based YOLO vision is available in source installs via `backend/requirements-vision.txt`, while packaged builds use the built-in local motion detector until a vision model is supplied.
