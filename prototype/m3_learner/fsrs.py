"""FSRS-4.5 核心调度（新卡 + 复习态），标准库实现，无第三方依赖。

口径：评分 1=again / 2=hard / 3=good / 4=easy；stability 单位为天，
到期按 90% 可提取率计算（此时 interval == stability）。
不含短期学习态（learning steps）与自定义参数；参数为 FSRS-4.5 默认 19 权重。
只负责调度，不知道错误清单和学习者模型的存在。
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

W = [0.40255, 1.18385, 3.173, 15.69105, 7.1949, 0.5345, 1.4604, 0.0046,
     1.54575, 0.1192, 1.01925, 1.9395, 0.11, 0.29605, 2.2698, 0.2315,
     2.9898, 0.51655, 0.6621]
DECAY = -0.5
FACTOR = 19 / 81
TARGET_RETENTION = 0.9


def retrievability(elapsed_days, stability):
    if stability <= 0:
        return 0.0
    return (1 + FACTOR * max(0.0, elapsed_days) / stability) ** DECAY


def interval_for_retention(stability, retention=TARGET_RETENTION):
    return stability * (retention ** (1 / DECAY) - 1) / FACTOR


def _initial_difficulty(rating):
    return min(10.0, max(1.0, W[4] - math.exp(W[5] * (rating - 1)) + 1))


def _next_difficulty(difficulty, rating):
    d = difficulty - W[6] * (rating - 3)
    d = W[7] * _initial_difficulty(4) + (1 - W[7]) * d
    return min(10.0, max(1.0, d))


def _next_stability(card, rating, elapsed_days):
    r = retrievability(elapsed_days, card.stability)
    d, s = card.difficulty, card.stability
    if rating == 1:
        return (W[11] * d ** (-W[12]) * ((s + 1) ** W[13] - 1)
                * math.exp(W[14] * (1 - r)))
    term = (math.exp(W[8]) * (11 - d) * s ** (-W[9]) * (math.exp(W[10] * (1 - r)) - 1))
    if rating == 2:
        term *= W[15]
    elif rating == 4:
        term *= W[16]
    return s * (1 + term)


@dataclass
class Card:
    item_id: str            # 如 error:G04 或 word:have been to
    kind: str = "error"     # error / word
    state: str = "new"      # new / review
    stability: float = 0.0
    difficulty: float = 0.0
    due: str = ""           # ISO 时间；新卡创建即到期
    reps: int = 0
    lapses: int = 0
    last_review: str | None = None

    @classmethod
    def new(cls, item_id, kind="error", now=None):
        now = now or datetime.now(timezone.utc)
        return cls(item_id=item_id, kind=kind, due=now.isoformat())

    def review(self, rating, now=None):
        """按评分推进卡片，返回（到期间隔天数, 当前可提取率）。"""
        if rating not in (1, 2, 3, 4):
            raise ValueError("rating 必须是 1/2/3/4（again/hard/good/easy）")
        now = now or datetime.now(timezone.utc)
        if self.state == "new":
            self.stability = W[rating - 1]
            self.difficulty = _initial_difficulty(rating)
            elapsed = 0.0
            r = 1.0
        else:
            last = datetime.fromisoformat(self.last_review)
            elapsed = max(0.0, (now - last).total_seconds() / 86400)
            r = retrievability(elapsed, self.stability)
            self.stability = _next_stability(self, rating, elapsed)
            self.difficulty = _next_difficulty(self.difficulty, rating)
            if rating == 1:
                self.lapses += 1
        self.state = "review"
        self.reps += 1
        self.last_review = now.isoformat()
        days = interval_for_retention(self.stability)
        self.due = (now + timedelta(days=days)).isoformat()
        return days, r


def due_cards(cards, now=None):
    now = now or datetime.now(timezone.utc)
    return sorted((c for c in cards if datetime.fromisoformat(c.due) <= now),
                  key=lambda c: c.due)
