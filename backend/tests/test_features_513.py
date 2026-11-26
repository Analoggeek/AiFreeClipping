"""v5.1.3: automatic model activation and multi-region clip scoring."""
from __future__ import annotations

from backend.app.schemas import RegionSelection
from backend.app.services import models, scoring


def test_region_selection_accepts_multiple_boxes():
    selection = RegionSelection(
        media_id="m1",
        kind="custom",
        boxes=[{"x": 0, "y": 0, "w": 1, "h": 0.58}, {"x": 0, "y": 0.58, "w": 1, "h": 0.42}],
        layout="top-game-bottom-player",
    )
    assert len(selection.boxes) == 2
    assert selection.layout == "top-game-bottom-player"


def test_propose_keeps_every_region_and_focus_reason():
    clips = scoring.propose(
        [{"id": "m1", "title": "Gameplay", "duration": 20}],
        {"m1": {"segments": [{"text": "wait watch this", "start": 1, "end": 6, "words": []}]}},
        {"m1": {"timeline": [{"t": 2, "activity": 0.9}]}},
        count=1,
        min_duration=5,
        max_duration=10,
        regions={"m1": [{"x": 0, "y": 0, "w": 1, "h": 0.58}, {"x": 0, "y": 0.58, "w": 1, "h": 0.42}]},
        layouts={"m1": "top-game-bottom-player"},
    )
    assert clips
    assert len(clips[0].regions) == 2
    assert clips[0].region_layout == "top-game-bottom-player"
    assert any("regions" in reason for reason in clips[0].reasons)


def test_activation_persists_and_selects_model(monkeypatch):
    class FakeDB:
        settings: dict[str, str] = {}

        def get_setting(self, key, default=""):
            return self.settings.get(key, default)

        def set_setting(self, key, value):
            self.settings[key] = value

    fake = FakeDB()
    monkeypatch.setattr(models, "db", fake)
    model = next(item for item in models.CATALOG if item["id"] == "gemma2:7b")
    models._activate(model)
    assert "gemma2:7b" in fake.settings["installed_models"]
    assert fake.settings["active_llm"] == "gemma2:7b"
    assert fake.settings["OLLAMA_MODEL"] == "gemma2:7b"
