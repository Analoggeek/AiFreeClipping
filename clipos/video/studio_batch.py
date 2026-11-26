"""Isolated timeline-window batch rendering with persistent truthful job states."""

from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
import re
import tempfile

from ..core.ffmpeg import FFmpegCancelled
from .multitrack_render import export_project
from .timeline import Timeline


@dataclass
class BatchJob:
    clip_id: int
    title: str
    start: float
    duration: float
    output: str
    status: str = "pending"
    error: str = ""
    encoder: str = ""


def plan_batch(project, clip_ids, output_dir, name="Project"):
    project.validate()
    ids = set(clip_ids)
    if not ids:
        raise ValueError("Select queue clips to render")
    name = re.sub(r"[^\w-]+", "_", name, flags=re.UNICODE).strip("_")[:80] or "Project"
    directory = Path(output_dir).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError("Choose an existing output directory")
    jobs = []
    found = set()
    reserved = {Path(m.path).resolve() for m in project.media}
    sources = {m.id: m for m in project.media}
    for lane in project.lanes:
        if lane.kind != "video" or not lane.enabled:
            continue
        for item in lane.items:
            source = sources[item.media_id]
            if source.queue_clip_id not in ids:
                continue
            found.add(source.queue_clip_id)
            output = directory / f"{name}_Clip_{len(jobs) + 1:03d}.mp4"
            if output.exists() or output.resolve() in reserved:
                raise ValueError(
                    "Output already exists; choose a new project name or folder: "
                    + str(output)
                )
            jobs.append(
                BatchJob(
                    source.queue_clip_id,
                    Path(source.path).stem,
                    item.at,
                    item.duration,
                    str(output),
                )
            )
    if found != ids:
        raise ValueError(
            "Some selected queue clips have no enabled video item on this timeline"
        )
    return jobs


def run_batch(
    project,
    jobs,
    *,
    encoder="auto",
    notify=None,
    cancelled=None,
    retry=False,
    manifest=None,
):
    """Each timeline video item is an output; split items become separate outputs.

    Preserves simultaneous overlays/audio using the same full-timeline graph,
    cropped at the selected item's output interval. Non-contributing missing
    sources are not opened. Existing output files are never replaced.
    """
    project.validate()

    def emit(index, pct=0, message=""):
        if manifest:
            Timeline._atomic_write(
                Path(manifest),
                json.dumps(
                    {
                        "schema": "clipos.batch.v1",
                        "jobs": [asdict(job) for job in jobs],
                    },
                    indent=2,
                ).encode(),
            )
        if notify:
            notify(index, pct, message)

    for index, job in enumerate(jobs):
        if job.status == "completed" or (
            retry and job.status not in ("failed", "cancelled")
        ):
            continue
        if cancelled and cancelled():
            for remaining in jobs[index:]:
                if remaining.status != "completed":
                    remaining.status = "cancelled"
            emit(index, 0, "Batch cancelled")
            break
        job.status = "processing"
        job.error = ""
        emit(index, 0, "Validating timeline interval")
        try:
            if Path(job.output).exists():
                raise FileExistsError(
                    "Refusing to overwrite existing output: " + job.output
                )
            with tempfile.TemporaryDirectory(
                prefix=".clipos-batch-", dir=Path(job.output).parent
            ) as work:
                result = export_project(
                    project,
                    str(Path(work) / "encoded.mp4"),
                    work,
                    encoder=encoder,
                    window=(job.start, job.duration),
                    cancel_cb=cancelled,
                    progress_cb=lambda pct, message: emit(index, pct, message),
                )
                # Atomic no-clobber publish, including another process creating
                # the requested output after our preflight check.
                os.link(result.output_path, job.output)
            job.status = "completed"
            job.encoder = result.encoder
        except FFmpegCancelled:
            job.status = "cancelled"
            job.error = "Cancelled; no successful result claimed"
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
        emit(index, 100 if job.status == "completed" else 0, job.status)
    return jobs
