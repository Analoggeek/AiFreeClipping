"""Native batch export dashboard backed by isolated real FFmpeg jobs."""

from dataclasses import asdict
import json
from pathlib import Path
import time
import uuid

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QProgressBar,
)
from ...video.multitrack import MultitrackProject
from ...video.studio_batch import plan_batch, run_batch


class BatchPanel(QWidget):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.jobs = []
        self.snapshot = None
        self.manifest = None
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("Batch export · enabled timeline video items · MP4 / H.264 / AAC")
        )
        self.name = QLineEdit("Project")
        self.name.setPlaceholderText("Output naming prefix")
        layout.addWidget(self.name)
        self.folder = QLineEdit(studio.db.get_setting("output_dir", ""))
        layout.addWidget(self.folder)
        self.encoder = QComboBox()
        self.encoder.addItem("Automatic hardware with CPU fallback", "auto")
        self.encoder.addItem("CPU", "cpu")
        layout.addWidget(self.encoder)
        self.summary = QLabel(
            "No batch started. Split timeline video items export as separate clips."
        )
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Clip", "State", "Output", "Error / encoder"]
        )
        layout.addWidget(self.table)
        for title, fn in [
            ("Choose output folder…", self.choose),
            ("Render selected queue clips", lambda: self.start(False)),
            ("Render all queue clips", lambda: self.start(True)),
            ("Retry failed / cancelled (same snapshot)", self.retry),
            ("Cancel batch", studio.cancel_work),
        ]:
            button = QPushButton(title)
            button.clicked.connect(
                lambda checked=False, action=fn: (
                    studio.editing.run(action)
                    if action != studio.cancel_work
                    else action()
                )
            )
            layout.addWidget(button)

    def choose(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Batch output folder", self.folder.text()
        )
        if folder:
            self.folder.setText(folder)

    def start(self, all_clips):
        entries = (
            self.studio.queue_manager.entries()
            if all_clips
            else self.studio.selected_clips()
        )
        snapshot = self.studio.project.to_dict()
        project = MultitrackProject.from_dict(snapshot)
        jobs = plan_batch(
            project, [c["id"] for c in entries], self.folder.text(), self.name.text()
        )
        self.snapshot = snapshot
        self.jobs = jobs
        self.manifest = Path(self.folder.text()) / (
            "batch-" + uuid.uuid4().hex + ".json"
        )
        self.studio.db.set_setting(
            "output_dir", str(Path(self.folder.text()).resolve())
        )
        self.launch(False)

    def retry(self):
        if not self.jobs or not self.snapshot:
            raise ValueError("No previous batch to retry")
        if not any(job.status in ("failed", "cancelled") for job in self.jobs):
            raise ValueError("No failed or cancelled jobs")
        self.launch(True)

    def launch(self, retry):
        project = MultitrackProject.from_dict(self.snapshot)
        jobs = self.jobs
        encoder = self.encoder.currentData()
        manifest = self.manifest
        self.started = time.monotonic()

        def job(worker):
            def notify(index, pct, message):
                worker.progress.emit(
                    pct,
                    json.dumps(
                        {
                            "index": index,
                            "pct": pct,
                            "message": message,
                            "jobs": [asdict(j) for j in jobs],
                        }
                    ),
                )

            return run_batch(
                project,
                jobs,
                encoder=encoder,
                retry=retry,
                manifest=manifest,
                cancelled=worker.cancelled.is_set,
                notify=notify,
            )

        def done(result):
            self.jobs = result
            self.paint_jobs([asdict(job) for job in result], 0, 0, "Batch finished")
            self.studio.status.setText(
                "Batch finished. Check per-clip status and errors; manifest: "
                + str(manifest)
            )

        self.studio._background(
            job, done, "Rendering batch snapshot…", on_progress=self.update_progress
        )

    def update_progress(self, pct, message):
        data = json.loads(message)
        self.paint_jobs(data["jobs"], data["index"], data["pct"], data["message"])

    def paint_jobs(self, jobs, index, pct, message):
        self.table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            for col, value in enumerate(
                (
                    job["title"],
                    job["status"],
                    job["output"],
                    job["error"] or job["encoder"],
                )
            ):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))
        completed = sum(job["status"] == "completed" for job in jobs)
        failed = sum(job["status"] == "failed" for job in jobs)
        cancelled = sum(job["status"] == "cancelled" for job in jobs)
        processing = sum(job["status"] == "processing" for job in jobs)
        remaining = len(jobs) - completed - failed - cancelled - processing
        self.progress.setValue(
            round(
                100
                * (completed + failed + cancelled + (pct / 100 if processing else 0))
                / max(1, len(jobs))
            )
        )
        elapsed = time.monotonic() - self.started
        eta = (
            f"{elapsed / completed * (remaining + processing):.0f}s"
            if completed and processing + remaining
            else ("0s" if not processing + remaining else "estimating")
        )
        current = jobs[index]["title"] if jobs and processing else "—"
        self.summary.setText(
            f"Total {len(jobs)} · Completed {completed} · Failed {failed} · Cancelled {cancelled} · Processing {processing} · Remaining {remaining}\nCurrent: {current} · Estimated remaining: {eta}\n{message}"
        )
