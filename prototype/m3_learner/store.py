"""学习者模型的本地 JSON 存储。单学习者、单文件、原子写入、可导出可删除。"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from m3_learner.fsrs import Card

SCHEMA_VERSION = 1


def utcnow():
    return datetime.now(timezone.utc)


class LearnerStore:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
        else:
            self.data = dict(schema_version=SCHEMA_VERSION,
                             learner=dict(learner_id="local", speaking_level="A2",
                                          created_at=utcnow().isoformat()),
                             error_instances=[], error_patterns={}, cards=[],
                             sessions_ingested=[])

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".m3-", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def export(self):
        return json.dumps(self.data, ensure_ascii=False, indent=1)

    def delete(self):
        self.path.unlink(missing_ok=True)
        self.data["error_instances"] = []
        self.data["error_patterns"] = {}
        self.data["cards"] = []
        self.data["sessions_ingested"] = []

    # ---- cards ----
    def cards(self):
        return [Card(**c) for c in self.data["cards"]]

    def put_card(self, card):
        for i, c in enumerate(self.data["cards"]):
            if c["item_id"] == card.item_id:
                self.data["cards"][i] = card.__dict__
                return
        self.data["cards"].append(card.__dict__)

    def has_card(self, item_id):
        return any(c["item_id"] == item_id for c in self.data["cards"])
