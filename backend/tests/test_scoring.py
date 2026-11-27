import asyncio

from app.main import _caption_words_in_window
from app.services.scoring import (
    Candidate, RerankResult, Suggestion, build_features, make_caption, make_title,
    propose, refine_with_llm, window_score,
)


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


def test_make_caption_cleans_and_limits_transcript_copy():
    caption = make_caption("  That was incredible .\nThe team made a smart comeback! A third sentence.")
    assert caption == "That was incredible. The team made a smart comeback!"
    assert make_caption("", "Epic finish #Shorts") == "Epic finish."
    assert len(make_caption("word " * 200)) <= 240


def test_caption_window_uses_word_timing_or_segment_fallback():
    analysis = {"segments": [
        {"start": 0, "end": 2, "text": "hello there", "words": [
            {"word": " hello", "start": 0.2, "end": 0.6},
            {"word": " there", "start": 0.8, "end": 1.2},
        ]},
        {"start": 2, "end": 4, "text": "a segment without aligned words", "words": []},
        {"start": 5, "end": 7, "text": "outside", "words": []},
    ]}
    captions = _caption_words_in_window(analysis, 1, 3)
    assert [item["word"] for item in captions[:1]] == [" there"]
    assert captions[1] == {"text": "a segment without aligned words", "start": 2, "end": 3}


def test_llm_caption_refinement_preserves_clip_timing():
    candidate = Candidate(
        media_id="m1", start=12.5, end=24.0, score=61,
        title="Old hook", transcript="The last-second finish changed the whole match.",
    )

    async def fake_llm(prompt, schema, **kwargs):
        assert "preserve the transcript's language" in prompt
        assert kwargs["temperature"] == 0.15
        return RerankResult(suggestions=[Suggestion(
            index=0, score=88, title="A last-second finish!", reason="Clear payoff",
            caption="The match turned on one final play.",
        )])

    result = asyncio.run(refine_with_llm([candidate], fake_llm, platform="reels"))
    assert result[0].start == 12.5 and result[0].end == 24.0
    assert result[0].title == "A last-second finish!"
    assert result[0].caption == "The match turned on one final play."
    assert result[0].score == 74.5
