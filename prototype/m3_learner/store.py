"""学习者模型的本地 JSON 存储。单学习者、单文件、原子写入、可导出可删除。

设置了 HEARSAY_R2_* 环境变量时，同一份文件还会镜像到 Cloudflare R2，
见 m3_learner/r2sync.py。没设置时行为与纯本地存储完全一致。
"""

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from m3_learner import r2sync
from m3_learner.fsrs import Card

SCHEMA_VERSION = 1

# 同一进程里多个切片线程会各自持有 LearnerStore 并保存同一个文件；
# 用一把锁保证"写本地 + 上传"成对完成，避免上传顺序与写入顺序错开。
_SAVE_LOCK = threading.Lock()


def utcnow():
    return datetime.now(timezone.utc)


class LearnerStore:
    def __init__(self, path, remote="env"):
        self.path = Path(path)
        # remote：
        #   "env"（默认）按环境变量决定是否启用 R2；None 关闭；也可传入 R2Client（测试用）
        self.remote = r2sync.client_from_env() if remote == "env" else remote
        if not self.path.exists() and self.remote is not None:
            self._pull()
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
        else:
            self.data = dict(schema_version=SCHEMA_VERSION,
                             learner=dict(learner_id="local", speaking_level="A2",
                                          created_at=utcnow().isoformat()),
                             error_instances=[], error_patterns={}, cards=[],
                             sessions_ingested=[])

    def _pull(self):
        """新容器启动时本地没有文件：从 R2 拉取持久副本。失败只告警，按空数据启动。"""
        try:
            blob = self.remote.get()
        except r2sync.R2Error as e:
            r2sync.warn(f"拉取学习者数据失败，按空数据启动：{e}")
            return
        if blob is None:
            return
        try:
            json.loads(blob)
        except ValueError:
            r2sync.warn("R2 上的学习者数据不是合法 JSON，忽略")
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".m3-", suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
        os.replace(tmp, self.path)

    def save(self):
        blob = json.dumps(self.data, ensure_ascii=False, indent=1).encode("utf-8")
        with _SAVE_LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".m3-", suffix=".tmp")
            with os.fdopen(fd, "wb") as f:
                f.write(blob)
            os.replace(tmp, self.path)
            if self.remote is not None:
                try:
                    self.remote.put(blob)
                except r2sync.R2Error as e:
                    # 本地已写成功，不打断练习；但容器休眠前若一直失败，数据会丢
                    r2sync.warn(f"上传学习者数据失败（本地已保存）：{e}")

    def export(self):
        return json.dumps(self.data, ensure_ascii=False, indent=1)

    def delete(self):
        self.path.unlink(missing_ok=True)
        if self.remote is not None:
            try:
                self.remote.delete()
            except r2sync.R2Error as e:
                r2sync.warn(f"删除 R2 上的学习者数据失败：{e}")
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
