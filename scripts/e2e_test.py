#!/usr/bin/env python3
"""End-to-end integration test for the CLIPOS pipeline.

Runs the complete workflow against a real generated video:

    import -> analyse -> detect clips -> metadata -> captions -> render -> export

Everything is real: real FFmpeg calls, real face detection, real rendering.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clipos.core.config import PATHS  # noqa: E402
from clipos.core.ffmpeg import probe  # noqa: E402
from clipos.db.database import Database  # noqa: E402
from clipos.video.importer import import_local  # noqa: E402
from clipos.video.pipeline import ClipOSPipeline, run_full_analysis  # noqa: E402
from clipos.video.renderer import RenderSettings  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    return condition


def main() -> int:
    work = Path("/tmp/clipos_e2e")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ setup
    print("\n=== 1. Test media ===")
    from scripts.make_face_video import build as build_faces

    video = build_faces(work / "source.mp4", seconds=16)
    check("generated a real test video", video.exists() and video.stat().st_size > 10_000,
          f"{video.stat().st_size // 1024} KB")

    info = probe(video)
    check("probed the video", info.duration > 10 and info.has_video,
          f"{info.duration:.1f}s {info.resolution} {info.fps_label}")
    check("video has an audio track", info.has_audio)

    # ------------------------------------------------------------------ import
    print("\n=== 2. Import ===")
    result = import_local(video, copy_to_media=False)
    check("imported the video", Path(result.path).exists(),
          f"{result.width}x{result.height} {result.duration:.1f}s")
    check("extracted a thumbnail", bool(result.thumbnail) and Path(result.thumbnail).exists())

    db = Database(work / "clipos.db")
    pid = db.create_project(
        name="E2E Test",
        source_path=result.path,
        duration=result.duration, width=result.width, height=result.height,
        fps=result.fps, has_audio=int(result.has_audio),
        size_bytes=result.size_bytes, thumbnail=result.thumbnail,
        aspect_ratio="9:16", clip_count=6, duration_range="15-30",
    )
    check("created a project in SQLite", pid > 0, f"project #{pid}")

    # ------------------------------------------------------------------ analysis
    print("\n=== 3. Analysis + clip detection ===")
    t0 = time.time()
    analysis = run_full_analysis(
        db, pid, clip_count=6, duration_range="15-30", aspect="9:16",
        stt_model="base",
    )
    elapsed = time.time() - t0
    check("analysis completed", elapsed > 0, f"{elapsed:.1f}s")

    clips = db.list_clips(pid)
    check("generated clips", len(clips) > 0, f"{len(clips)} clips")
    if clips:
        check("clips have real durations",
              all(c["duration"] > 5 for c in clips),
              f"{[round(c['duration']) for c in clips]}")

        scores = [c["virality_score"] for c in clips]
        check("virality scores are in range", all(0 <= s <= 100 for s in scores),
              f"min {min(scores):.0f} max {max(scores):.0f}")
        # A 16-second fixture cannot honestly supply six distinct 15-second
        # clips. Strict automatic selection must not pad with overlapping copies
        # or invent different scores merely to satisfy the requested count.
        selection=json.loads((PATHS.projects/str(pid)/"analysis"/"selection.json").read_text())
        check("short source yields one distinct clip with an explicit shortfall",
              len(clips)==1 and selection["selected_count"]==1 and
              selection["requested"]==6 and bool(selection["warnings"]),
              f"{len(clips)} genuine clip; no duplicate-count padding")

        eng = [c["engagement_score"] for c in clips]
        check("engagement scores are in range", all(0 <= e <= 100 for e in eng),
              f"min {min(eng):.0f} max {max(eng):.0f}")

        check("every clip has a reason",
              all(bool((c["reason"] or "").strip()) for c in clips))
        check("every clip has hook suggestions",
              all(json.loads(c["hook_suggestions"] or "[]") for c in clips))
        check("every clip has 5 titles",
              all(len(json.loads(c["titles"] or "[]")) >= 3 for c in clips))
        check("every clip has hashtags",
              all(json.loads(c["hashtags"] or "[]") for c in clips))

    # transcript
    tr = db.get_transcript(pid)
    if tr:
        check("transcript stored", bool(tr["full_text"]), f"{len(tr['full_text'])} chars")
    else:
        print(f"  [INFO] no transcript (no STT model installed) — {analysis.transcription_error[:70]}")

    # ------------------------------------------------------------------ captions
    print("\n=== 4. Captions ===")
    from clipos.ai.transcription import Segment, Transcript, Word
    from clipos.captions.caption_engine import (
        build_cues_for_clip, get_style, list_styles, write_ass,
    )

    # Use the real transcript when speech-to-text is available; otherwise fall
    # back to a synthetic word-timed transcript so the caption path is still
    # exercised end-to-end.
    tr_obj = analysis.transcript
    if tr_obj is None:
        print("  [INFO] no STT model available — using a synthetic word-timed transcript")
        words = [
            ("This", 0.0, 0.2), ("is", 0.2, 0.35), ("the", 0.35, 0.5),
            ("secret", 0.5, 0.9), ("that", 0.9, 1.1), ("nobody", 1.1, 1.5),
            ("tells", 1.5, 1.8), ("you", 1.8, 2.0), ("about", 2.0, 2.3),
            ("video", 2.3, 2.6), ("editing", 2.6, 3.2), ("Why", 3.2, 3.5),
            ("does", 3.5, 3.7), ("every", 3.7, 4.0), ("single", 4.0, 4.3),
            ("short", 4.3, 4.6), ("fail", 4.6, 4.9), ("in", 4.9, 5.0),
            ("the", 5.0, 5.1), ("first", 5.1, 5.4), ("three", 5.4, 5.7),
            ("seconds", 5.7, 6.0),
        ]
        seg = Segment(0.0, 6.0, " ".join(w for w, _, _ in words),
                      [Word(w, s, e, 1.0) for w, s, e in words])
        tr_obj = Transcript(language="en", duration=6.0, text=seg.text,
                            segments=[seg], model="synthetic")

    if clips:
        c = clips[0]
        cues = build_cues_for_clip(tr_obj, c["transcript_text"],
                                   c["start_time"], c["end_time"])
        check("built caption cues", len(cues) > 0, f"{len(cues)} cues")
        if cues:
            ass = write_ass(work / "test.ass", cues, get_style("bold_viral"), 1080, 1920)
            content = ass.read_text()
            check("wrote a valid ASS file", "Dialogue:" in content and "[V4+ Styles]" in content)
            check("ASS contains one dialogue per cue",
                  content.count("Dialogue:") == len(cues))
            check("caption cues carry word timings",
                  all(len(cue.words) > 0 for cue in cues))
        styles = list_styles()
        legacy = {"mrbeast", "minimal_white", "neon_gaming", "modern_podcast",
                  "bold_viral", "cinematic", "karaoke", "clean_professional"}
        check("legacy and animated caption styles are registered",
              legacy <= {style["key"] for style in styles}
              and sum(style["animation"] != "none" for style in styles) >= 30,
              f"{len(styles)} styles")

    # ------------------------------------------------------------------ render
    print("\n=== 5. Render ===")
    out_dir = work / "exports"
    out_dir.mkdir(exist_ok=True)
    settings = RenderSettings.for_aspect("9:16")
    settings.caption_style = "bold_viral"
    settings.smart_reframe = True
    settings.remove_silence = True

    pipe = ClipOSPipeline(db, pid)
    if clips:
        target = out_dir / "clip_001.mp4"
        t0 = time.time()
        res = pipe.render_clip(clips[0]["id"], target, settings, analysis)
        render_time = time.time() - t0
        check("rendered a real video", Path(res["output_path"]).exists(),
              f"{res['width']}x{res['height']} {res['duration']:.1f}s "
              f"{res['size_bytes'] // 1024} KB in {render_time:.1f}s")

        out_info = probe(res["output_path"])
        check("output is vertical 1080x1920",
              out_info.video.width == 1080 and out_info.video.height == 1920,
              f"{out_info.resolution}")
        check("output has an audio track", out_info.has_audio)
        check("output duration is sensible",
              5 < out_info.duration < 60, f"{out_info.duration:.1f}s")
        check("render produced thumbnails", len(res.get("thumbnails") or []) > 0,
              f"{len(res.get('thumbnails') or [])} thumbnails")

    # ------------------------------------------------------------------ export
    print("\n=== 6. Batch export ===")
    if clips:
        batch_dir = work / "batch"
        # NOTE: do not reuse the name `results` here — it shadows the
        # module-level list of check results and breaks the final summary.
        export_results = pipe.export_clips(
            [c["id"] for c in clips], batch_dir, settings, analysis,
        )
        check("batch export produced a result per clip",
              len(export_results) == len(clips), f"{len(export_results)} results")
        check("batch export rendered real files",
              all(Path(r.get("output_path", "")).exists() for r in export_results),
              f"{sum(1 for r in export_results if Path(r.get('output_path','')).exists())} files")
        check("batch export recorded no errors",
              all(not r.get("error") for r in export_results))
        # Re-read the clips: the export writes the thumbnail paths, and the
        # list captured earlier still holds the pre-export values.
        clips = db.list_clips(pid)
        check("every exported clip got a thumbnail",
              all(Path(c["thumbnail_path"] or "").exists() for c in clips),
              f"{sum(1 for c in clips if Path(c['thumbnail_path'] or '').exists())} thumbs")
        thumb_paths = [c["thumbnail_path"] for c in clips]
        check("thumbnails are unique per clip",
              len(set(thumb_paths)) == len(thumb_paths),
              f"{len(set(thumb_paths))}/{len(thumb_paths)} unique")

    print("\n=== 7. Export history ===")
    exports = db.list_exports(pid)
    check("exports recorded in the database", len(exports) > 0, f"{len(exports)} rows")
    if exports:
        check("export status is done", all(e["status"] == "done" for e in exports),
              f"{exports[0]['status']}")
        check("export records the file size",
              all(e["size_bytes"] > 0 for e in exports))

    # ------------------------------------------------------------------ zip
    print("\n=== 8. Batch packaging ===")
    import zipfile

    zip_path = out_dir / "clips.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in out_dir.glob("*.mp4"):
            zf.write(f, f.name)
    check("packaged clips into a ZIP", zip_path.exists() and zip_path.stat().st_size > 0,
          f"{zip_path.stat().st_size // 1024} KB")

    # ------------------------------------------------------------------ summary
    print("\n" + "=" * 62)
    passed = sum(1 for r in results if r[0] == PASS)
    failed = sum(1 for r in results if r[0] == FAIL)
    print(f"  {passed} passed, {failed} failed, {len(results)} total")
    print("=" * 62)
    if failed:
        print("\nFailures:")
        for s, name, detail in results:
            if s == FAIL:
                print(f"  - {name}: {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
