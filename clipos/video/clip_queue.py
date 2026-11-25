"""Persistent generated-clip ordering and groups; never mutates media files."""

import json


class ClipQueue:
    KEY = "studio_queue_v1"

    def __init__(self, db):
        self.db = db

    def entries(self):
        clips = {c["id"]: dict(c) for c in self.db.list_clips() if c["output_path"]}
        raw = self.db.get_setting(self.KEY, "")
        try:
            state = json.loads(raw) if raw else {}
        except (ValueError, TypeError):
            state = {}
        if not isinstance(state, dict):
            state = {}
        order = state.get("order", [])
        ids = list(dict.fromkeys([i for i in order if i in clips] + list(clips)))
        groups = state.get("groups", {})
        return [{**clips[i], "queue_group": groups.get(str(i), "")} for i in ids]

    def _save(self, order, groups):
        self.db.set_setting(self.KEY, json.dumps({"order": order, "groups": groups}))

    def move(self, ids, delta):
        if delta not in (-1, 1):
            raise ValueError("Move must be one position")
        entries = self.entries()
        order = [c["id"] for c in entries]
        chosen = set(ids)
        indices = range(len(order)) if delta == -1 else range(len(order) - 1, -1, -1)
        for index in indices:
            other = index + delta
            if (
                order[index] in chosen
                and 0 <= other < len(order)
                and order[other] not in chosen
            ):
                order[index], order[other] = order[other], order[index]
        self._save(order, {str(c["id"]): c["queue_group"] for c in entries})

    def group(self, ids, name):
        if not isinstance(name, str) or len(name) > 100:
            raise ValueError("Group name must be at most 100 characters")
        entries = self.entries()
        groups = {str(c["id"]): c["queue_group"] for c in entries}
        valid = {c["id"] for c in entries}
        for clip_id in ids:
            if clip_id not in valid:
                raise ValueError("Unknown queue clip")
            groups[str(clip_id)] = name.strip()
        self._save([c["id"] for c in entries], groups)

    def rename(self, clip_id, title):
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError("Clip name must contain 1–200 characters")
        self.db.update_clip(clip_id, title=title.strip())

    def duplicate(self, clip_id):
        clip = self.db.get_clip(clip_id)
        if clip is None:
            raise ValueError("Unknown queue clip")
        values = dict(clip)
        values.pop("id", None)
        values["title"] = (values["title"] or "Clip") + " (copy)"
        return self.db.create_clip(**values)
