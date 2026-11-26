from app.services.tracking import ByteTrackLite
from app.services.utils import iou


def test_iou_bounds():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0


def test_track_keeps_identity_through_motion():
    tracker = ByteTrackLite(match_threshold=0.2)
    ids = set()
    for frame in range(8):
        x = frame * 4
        tracks = tracker.update([([x, 10, x + 30, 80], 0.9)])
        if tracks:
            ids.add(tracks[0].track_id)
    assert len(ids) == 1
