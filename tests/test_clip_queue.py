"""Persistent queue operations do not delete, rename or overwrite media."""

from clipos.db.database import Database
from clipos.video.clip_queue import ClipQueue


def test_queue_groups_order_duplicate_rename_and_restart(tmp_path):
    path = tmp_path / "queue.db"
    db = Database(path)
    source = tmp_path / "media.mp4"
    source.write_bytes(b"unchanged source bytes")
    pid = db.create_project(name="Queue", source_path=str(source))
    ids = [
        db.create_clip(
            project_id=pid, title=f"clip {i}", output_path=str(source), duration=1
        )
        for i in range(3)
    ]
    queue = ClipQueue(db)
    ordered = [c["id"] for c in queue.entries()]
    queue.move([ordered[-1]], -1)
    expected = [ordered[0], ordered[2], ordered[1]]
    assert [c["id"] for c in queue.entries()] == expected
    queue.group(ids[:2], "Interview")
    queue.rename(ids[0], "New name")
    duplicate = queue.duplicate(ids[0])
    assert db.get_clip(duplicate)["output_path"] == str(source)
    db.close()
    db = Database(path)
    queue = ClipQueue(db)
    assert [c["id"] for c in queue.entries()][:3] == expected
    assert {c["queue_group"] for c in queue.entries() if c["id"] in ids[:2]} == {
        "Interview"
    }
    db.delete_clip(duplicate)
    assert source.read_bytes() == b"unchanged source bytes"
    db.close()
