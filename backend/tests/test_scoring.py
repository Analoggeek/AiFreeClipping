from app.services.scoring import build_features, make_title, propose, window_score


def test_features_aligned_and_hook_boost():
    transcript = {
        "segments": [
            {
                "text": "Wait, you won't believe this",
                "words": [
                    {"word": "Wait,", "start": 1.0, "end": 1.4, "probability": 0.9},
                    {"word": "crazy", "start": 1.5, "end": 2.0, "probability": 0.9},
                ],
            }
        ]
    }
    vision = {"timeline": [{"t": 1.5, "activity": 0.8}, {"t": 10, "activity": 0.1}]}
    speech, keywords, visual = build_features(transcript, vision, 20)
    assert len(speech) == len(keywords) == len(visual) == 41
    assert sum(keywords) > 0
    assert visual[3] == 0.8
    score, reasons = window_score(speech, keywords, visual, 2, 8)
    assert 0 <= score <= 100
    assert reasons


def test_propose_returns_non_overlapping_windows():
    media = [{"id": "m1", "title": "Match", "duration": 120}]
    transcript = {
        "segments": [
            {"start": i * 8, "end": i * 8 + 5, "text": f"crazy moment {i}", "words": [
                {"word": "crazy", "start": i * 8, "end": i * 8 + 0.5, "probability": 0.9}
            ]}
            for i in range(12)
        ]
    }
    vision = {"timeline": [{"t": i * 8, "activity": 0.9 if i % 3 == 0 else 0.1} for i in range(15)]}
    candidates = propose(media, {"m1": transcript}, {"m1": vision}, count=3, min_duration=15, max_duration=40)
    assert candidates
    assert all(c.media_id == "m1" for c in candidates)
    assert all(c.end > c.start for c in candidates)
    assert len(candidates) <= 3
    assert all("#Shorts" in c.title for c in candidates)


def test_make_title_fallback():
    title, hook = make_title("", "shorts", "Epic finish")
    assert "Epic finish" in title
    assert hook == ""
