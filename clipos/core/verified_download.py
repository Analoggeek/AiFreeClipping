"""Resumable, bounded, checksum-gated downloads from a fixed official manifest."""

import hashlib
import os
from pathlib import Path
import shutil
import urllib.request


class DownloadCancelled(RuntimeError):
    pass


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def download(url, destination, expected_sha256, size, *, progress=None, cancelled=None):
    if not url.startswith("https://github.com/"):
        raise ValueError(
            "Only manifest-pinned official GitHub HTTPS assets are allowed"
        )
    if len(expected_sha256) != 64 or any(
        c not in "0123456789abcdef" for c in expected_sha256
    ):
        raise ValueError("Missing verified SHA256")
    if type(size) is not int or size <= 0:
        raise ValueError("Missing expected asset size")
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    if (
        target.is_file()
        and target.stat().st_size == size
        and sha256(target) == expected_sha256
    ):
        return target
    partial = target.with_suffix(target.suffix + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > size:
        partial.unlink()
        offset = 0
    if shutil.disk_usage(target.parent).free < max(0, size - offset) + 256 * 1024**2:
        raise RuntimeError("Insufficient free disk space for download")
    if offset < size:
        headers = {"User-Agent": "Ai-clipping-PRO-model-manager"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.getcode()
            if offset and status != 206:
                offset = 0
            if status == 206 and not response.headers.get(
                "Content-Range", ""
            ).startswith(f"bytes {offset}-"):
                raise RuntimeError(
                    "Server returned an incompatible resume range; retry after clearing the partial file"
                )
            mode = "ab" if offset else "wb"
            with partial.open(mode) as stream:
                while True:
                    if cancelled and cancelled():
                        raise DownloadCancelled(
                            "Download cancelled; verified-prefix partial file retained for retry"
                        )
                    block = response.read(1024 * 512)
                    if not block:
                        break
                    if offset + len(block) > size:
                        raise RuntimeError("Download exceeds official asset size")
                    stream.write(block)
                    offset += len(block)
                    if progress:
                        progress(
                            offset * 100 / size,
                            f"Downloaded {offset:,} / {size:,} bytes",
                        )
                stream.flush()
                os.fsync(stream.fileno())
    if partial.stat().st_size != size:
        raise RuntimeError("Incomplete asset; retry resumes the partial download")
    if sha256(partial) != expected_sha256:
        partial.unlink()
        raise RuntimeError(
            "SHA256 mismatch; untrusted download deleted. Retry from the official source."
        )
    os.replace(partial, target)
    return target
