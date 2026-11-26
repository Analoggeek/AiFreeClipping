"""Offline caption generation for actual trimmed/speed-adjusted timeline media."""

from pathlib import Path
import tempfile

from .multitrack import MultitrackProject, Lane, Item, uid
from ..core.ffmpeg import FFmpegRunner, FFmpegCancelled
from ..ai.transcription import local_model_path, transcribe
from ..captions.caption_engine import CAPTION_STYLES, build_cues


def generate_timeline_captions(
    project,
    media_ids,
    *,
    model_size="base",
    language=None,
    style="bold_viral",
    progress=None,
    cancelled=None,
):
    """Return new caption lane data, without changing the live project.

    Transcribes each trimmed video item, using its source audio even if the
    independent timeline audio is muted. No model download or diarization.
    Appends captions; caller explicitly chooses whether to replace existing ones.
    """
    project.validate()
    if style not in CAPTION_STYLES:
        raise ValueError("Unknown caption style")
    if local_model_path(model_size) is None:
        raise RuntimeError(
            "Install and verify the selected Whisper model in AI Models first"
        )
    media = {m.id: m for m in project.media}
    selected = set(media_ids)
    if not selected or not selected <= media.keys():
        raise ValueError("Select existing timeline media")
    targets = [
        item
        for lane in project.lanes
        if lane.kind == "video" and lane.enabled
        for item in lane.items
        if item.media_id in selected
    ]
    if not targets:
        raise ValueError("No enabled video items selected")
    if any(not media[item.media_id].has_audio for item in targets):
        raise ValueError(
            "A selected clip has no source audio; exclude it before caption generation"
        )
    lane = Lane(uid(), "Generated speech captions", "caption")
    languages = []
    with tempfile.TemporaryDirectory(prefix="clipos-studio-stt-") as directory:
        for index, item in enumerate(targets):
            if cancelled and cancelled():
                raise FFmpegCancelled()
            audio = Path(directory) / "speech.wav"
            FFmpegRunner(total_duration=item.length, cancel_cb=cancelled).run(
                [
                    "-hide_banner",
                    "-nostdin",
                    "-y",
                    "-ss",
                    str(item.source_in),
                    "-t",
                    str(item.length),
                    "-i",
                    media[item.media_id].path,
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "pcm_s16le",
                    str(audio),
                ]
            )
            transcript = transcribe(
                audio,
                model_size=model_size,
                language=language,
                device="cpu",
                progress_cb=(
                    lambda pct, message: progress(
                        (index + pct / 100) / len(targets) * 100, message
                    )
                )
                if progress
                else None,
                cancel_cb=cancelled,
            )
            languages.append(transcript.language)
            for cue in build_cues(transcript, 0, item.length):
                start = max(0.0, cue.start)
                end = min(item.length, cue.end)
                if end <= start or not cue.text.strip():
                    continue
                words = []
                for word in cue.words:
                    s = max(start, word["s"])
                    e = min(end, word["e"])
                    if e > s:
                        words.append(
                            {
                                "w": word["w"],
                                "s": (s - start) / item.speed,
                                "e": (e - start) / item.speed,
                            }
                        )
                lane.items.append(
                    Item(
                        uid(),
                        "",
                        item.at + start / item.speed,
                        0.0,
                        (end - start) / item.speed,
                        text=cue.text,
                        caption_style=style,
                        caption_words=words,
                    )
                )
    if cancelled and cancelled():
        raise FFmpegCancelled()
    if not lane.items:
        raise ValueError("No speech detected; no captions were added")
    draft = MultitrackProject.from_dict(project.to_dict())
    draft.lanes.append(lane)
    draft.validate()
    return {"lane": lane, "languages": languages, "count": len(lane.items)}


def append_generated_captions(project, result):
    """One undoable validated commit. Never partially adds a failed batch."""
    from copy import deepcopy

    lane = deepcopy(result["lane"])
    project.edit(lambda draft: draft.lanes.append(lane))
